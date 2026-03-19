# C3: Performance Audit Findings

**Auditor**: C3 (Performance Auditor)
**Date**: 2026-03-19
**Scope**: N+1 queries, async anti-patterns, memory leaks, connection pooling, caching strategy
**Files examined**: `src/api/routes/copilot.py`, `src/api/routes/evidence.py`, `src/api/routes/engagements.py`, `src/api/middleware/security.py`, `src/evidence/pipeline.py`, `src/evidence/chunking.py`, `src/semantic/graph.py`, `src/semantic/embeddings.py`, `src/semantic/bridges/process_evidence.py`, `src/semantic/bridges/evidence_policy.py`, `src/semantic/bridges/process_tom.py`, `src/semantic/bridges/communication_deviation.py`, `src/rag/retrieval.py`, `src/monitoring/alerting/engine.py`, `src/core/database.py`, `src/core/config.py`, `src/api/main.py`

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 4     |
| MEDIUM   | 4     |
| LOW      | 3     |
| **Total** | **12** |

---

## Findings

### [CRITICAL] N+1 WRITE: `generate_fragment_embeddings` issues one SQL UPDATE per fragment inside a sequential loop

**File**: `src/evidence/pipeline.py:539`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
stored = 0
for frag, embedding in zip(valid_fragments, embeddings, strict=True):
    try:
        await semantic_service.store_embedding(session, str(frag.id), embedding)
        stored += 1
    except (ValueError, ConnectionError, RuntimeError) as e:
        logger.warning("Failed to store embedding for fragment %s: %s", frag.id, e)
```
**Description**: `generate_fragment_embeddings` in `pipeline.py` calls `semantic_service.store_embedding()` once per fragment inside a sequential loop. Each `store_embedding` call executes a raw `UPDATE evidence_fragments SET embedding = :embedding WHERE id = :fragment_id` statement — a separate database round-trip. For a document that produces 50 fragments, this generates 50 sequential UPDATE queries, all holding the SQLAlchemy session open for the duration of the upload request. Ironically, `EmbeddingService.store_embeddings_batch()` already exists (at `src/semantic/embeddings.py:131`) and performs the same operation as a single `executemany` round-trip — it is simply not called here.

**Risk**: On a document upload producing 100 fragments, this path executes 100 sequential UPDATE statements after the batch embedding generation completes. Combined with the synchronous execution within the upload request handler, this adds measurable latency to every file upload. The `store_embeddings_batch` method exists specifically to fix this and is documented with a reference to this finding class (comment: `C3-H2`), but `generate_fragment_embeddings` was not updated to use it.
**Recommendation**: Replace the per-fragment loop with a single call to `semantic_service.store_embeddings_batch(session, [(str(frag.id), embedding) for frag, embedding in zip(valid_fragments, embeddings)])`. This collapses N database round-trips to 1.

---

### [HIGH] N+1 GRAPH WRITE: CO_OCCURS_WITH relationships created one-at-a-time inside a nested loop in `build_fragment_graph`

**File**: `src/evidence/pipeline.py:466`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for ev_id, entity_ids in evidence_to_entities.items():
    entity_list = sorted(entity_ids)
    for i, eid_a in enumerate(entity_list):
        for eid_b in entity_list[i + 1:]:
            ...
            await graph_service.create_relationship(
                from_id=node_a, to_id=node_b,
                relationship_type="CO_OCCURS_WITH",
                properties={"evidence_id": ev_id},
            )
```
**Description**: The CO_OCCURS_WITH relationship creation loop is O(N²) in the number of co-occurring entities per evidence item. Each `create_relationship` call opens a new `async with self._driver.session()` context in `graph.py:182` and issues a single `MATCH ... CREATE` Cypher statement. For an evidence item with 20 co-occurring entities, this generates up to 190 sequential Neo4j sessions and queries. `KnowledgeGraphService.batch_create_relationships()` (at `src/semantic/graph.py:387`) already implements the correct `UNWIND`-based batch path but is not used here.

**Risk**: A moderately complex document producing 30 entities and 30 evidence nodes generates up to 435 sequential Neo4j round-trips for relationships alone, each with its own session open/close overhead (~2-5ms). This accumulates to 1-2 seconds of Neo4j overhead per document, executed synchronously inside the upload request.
**Recommendation**: Collect all (from_id, to_id, properties) tuples for CO_OCCURS_WITH relationships into a list, then call `graph_service.batch_create_relationships("CO_OCCURS_WITH", rels)` once. This reduces N² sessions to a single `UNWIND`-based transaction.

---

### [HIGH] N+1 GRAPH WRITE: All four semantic bridges call `create_relationship` per matching node pair inside nested loops

**File**: `src/semantic/bridges/process_evidence.py:110`, `src/semantic/bridges/evidence_policy.py:86`, `src/semantic/bridges/process_tom.py:65`, `src/semantic/bridges/communication_deviation.py:76`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
# process_evidence.py — O(P * E) Neo4j calls
for p_idx, proc in enumerate(all_process_nodes):
    for e_idx, ev in enumerate(evidence_nodes):
        if is_match:
            await self._graph.create_relationship(
                from_id=proc.id, to_id=ev.id,
                relationship_type="SUPPORTED_BY",
                properties={"source": "process_evidence_bridge", "confidence": confidence},
            )
```
**Description**: All four semantic bridges (`ProcessEvidenceBridge`, `EvidencePolicyBridge`, `ProcessTOMBridge`, `CommunicationDeviationBridge`) share the same anti-pattern: nested loops over node pairs with an individual `create_relationship` call inside the innermost loop body. `ProcessTOMBridge.run()` is O(nodes × dimensions × tom_nodes) — three nested loops. Each `create_relationship` call spawns a new Neo4j write transaction. `batch_create_relationships` in `KnowledgeGraphService` exists precisely for this use case.

**Risk**: For an engagement with 50 process nodes and 100 evidence nodes, `ProcessEvidenceBridge` can issue up to 5,000 individual Neo4j write transactions. These bridges run serially within `run_semantic_bridges`, which is called synchronously inside the upload pipeline. Total bridge latency can reach tens of seconds on non-trivial engagements.
**Recommendation**: In each bridge's `run()` method, accumulate matching pairs into a `rels: list[dict]` and call `graph_service.batch_create_relationships(relationship_type, rels)` once after the matching loop completes. This pattern collapses all Neo4j round-trips per bridge into one.

---

### [HIGH] MEMORY LEAK: `AlertEngine` accumulates all alerts and all notification log entries in unbounded in-memory lists

**File**: `src/monitoring/alerting/engine.py:448`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
class AlertEngine:
    def __init__(self, ...):
        self.alerts: list[Alert] = []
        self._notification_log: list[dict[str, Any]] = []

    def process_event(self, event: AlertEvent) -> list[Alert]:
        ...
        self.alerts.append(deduped)
        self._notification_log.append({...})
```
**Description**: `AlertEngine` stores every generated alert and every notification dispatch event in plain Python lists (`self.alerts`, `self._notification_log`) with no eviction, TTL, or size cap. The `query_alerts` method filters `self.alerts` entirely in Python, iterating the full list on every query call. Since `AlertEngine` is presumably instantiated as a long-lived singleton or per-monitoring-worker, these lists grow indefinitely for the lifetime of the process. The `_open_alerts` dict in `AlertDeduplicator` has a `clear_expired()` method but no automatic scheduling — it is never called by the engine itself.

**Risk**: In a high-alert environment processing hundreds of events per hour, `self.alerts` accumulates without bound. After days of operation, a query that applies 6 Python-level filters against a 100,000-element list executes a full linear scan on every API call to `/api/v1/monitoring/alerts`. `_notification_log` has no cap at all and accumulates the full payload of every alert dispatched.
**Recommendation**: Persist alerts to the database (the `MonitoringAlert` model already exists) rather than keeping them in memory. The in-memory store is appropriate only for a write-through cache with a size cap. Call `deduplicator.clear_expired()` periodically (e.g., every N events). Cap `_notification_log` at a fixed maximum (e.g., last 1,000 entries) using `collections.deque(maxlen=1000)`.

---

### [HIGH] ASYNC ANTI-PATTERN: `SecurityHeadersMiddleware` calls `get_settings()` on every HTTP request

**File**: `src/api/middleware/security.py:57`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        response = await call_next(request)
        ...
        if not getattr(settings, "debug", False):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```
**Description**: `SecurityHeadersMiddleware.dispatch` calls `get_settings()` on every HTTP request solely to check the `debug` flag. While `get_settings()` is cached via `@functools.lru_cache` (making the call cheap), this pattern runs on every request including health checks, WebSocket frames, and high-frequency API calls. The `debug` flag cannot change at runtime. All header values are static strings that are re-assigned to every response individually.

**Risk**: MEDIUM individually. At 1,000 requests/second across all workers, this is 1,000 unnecessary function call dispatches per second. The deeper issue is the pattern: settings are static config resolved at startup and should never be re-fetched in hot paths.
**Recommendation**: Resolve `settings.debug` once in `__init__` as `self._debug: bool`. Pre-build the full static header dict at construction time (`self._static_headers: dict[str, str]`). In `dispatch`, call `response.headers.update(self._static_headers)` in a single operation instead of 8 individual assignments.

---

### [MEDIUM] UNBOUNDED GRAPH QUERY: `get_stats` relationship query does not scope target node by engagement_id

**File**: `src/semantic/graph.py:777`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
rel_query = """
MATCH (a {engagement_id: $engagement_id})-[r]->(b)
RETURN type(r) AS rel_type, count(r) AS count
"""
rel_records = await self._run_query(rel_query, {"engagement_id": engagement_id})
```
**Description**: The relationship count query in `get_stats` matches all outgoing relationships from nodes in the engagement but does not filter the target node `(b)` by `engagement_id`. This means it counts relationships that cross engagement boundaries — including any cross-engagement links created by bugs or data migration errors. More critically, it does not include a `LIMIT` clause, so the aggregation must scan every relationship attached to every engagement node. On large graphs this is a full graph traversal.

**Risk**: For an engagement with 1,000 nodes each with 10 outgoing relationships, Neo4j must evaluate 10,000 relationship traversals to compute the `count(r) GROUP BY type(r)`. Without a label constraint on `(a)` or `(b)`, Neo4j cannot use label-scoped indexes and must fall back to a property scan.
**Recommendation**: Add `AND b.engagement_id = $engagement_id` to the relationship query. Add label constraints to both `(a)` and `(b)` or use a pattern like `MATCH (a)-[r]->(b) WHERE a.engagement_id = $engagement_id AND b.engagement_id = $engagement_id`. Consider caching the stats result with a Redis TTL since graph stats do not change on every API call.

---

### [MEDIUM] MEMORY: Full file content read into memory on every upload before any validation

**File**: `src/api/routes/evidence.py:179`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
@router.post("/upload", ...)
async def upload_evidence(...):
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    ...
    evidence_item, fragments, duplicate_of_id = await ingest_evidence(
        session=session, file_content=file_content, ...
    )
```
**Description**: The upload handler reads the entire file into memory (`await file.read()`) before any validation or size check. The size check (`MAX_UPLOAD_SIZE = 100 MB`) occurs later inside `ingest_evidence`. A client can send a 100 MB file and have all 100 MB buffered in the Python process before the size validation rejects it. With concurrent uploads, the server can buffer `concurrent_uploads * 100 MB` before any are rejected. The SHA-256 hash computation and MIME detection only need partial data (MIME needs 8KB; hash needs streaming) but receive the full buffer.

**Risk**: 10 concurrent 100 MB uploads hold 1 GB of file bytes in process memory simultaneously. On a 2 GB container, this alone can exhaust memory before any processing begins.
**Recommendation**: Move the size check to the upload handler before reading, using `file.size` if available or reading in chunks. Stream the file directly to object storage. Compute SHA-256 incrementally using `hashlib.sha256().update(chunk)`. Read only the first 8 KB for MIME detection. This requires refactoring `ingest_evidence` to accept an async stream rather than raw bytes.

---

### [MEDIUM] OVER-FETCH: Graph expansion in `HybridRetriever` fetches `top_k * 10` nodes per query with full in-Python scoring

**File**: `src/rag/retrieval.py:355`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
result = await neo4j_session.run(
    """
    MATCH (n)-[r]-(m)
    WHERE n.engagement_id = $engagement_id
      AND m.engagement_id = $engagement_id
      AND n.name IS NOT NULL
    WITH DISTINCT n, labels(n)[0] as label, elementId(n) as node_id
    RETURN n.name as name, n.description as description, label, node_id
    LIMIT $fetch_limit
    """,
    engagement_id=engagement_id,
    fetch_limit=top_k * 10,  # Over-fetch for scoring
)
records = [record async for record in result]
```
**Description**: The graph expansion path in `_graph_expand` fetches `top_k * 10` graph nodes (default: 50 nodes when `top_k=5`) from Neo4j, transfers all node data to the Python process, then scores each node with a Python-level string-matching loop. The Cypher query joins every node to its neighbors (`MATCH (n)-[r]-(m)`) which forces a relationship traversal scan before the `DISTINCT` de-duplication. The scoring and filtering that reduce 50 results to 5 happen entirely in Python rather than at the database layer.

**Risk**: The `MATCH (n)-[r]-(m)` pattern scans all relationships to filter by node property, which is expensive on large graphs. Fetching 50 nodes when only 5 are needed transfers up to 10x more data than necessary over the Neo4j driver connection.
**Recommendation**: Push term matching into the Cypher query using `WHERE any(term IN $terms WHERE toLower(n.name) CONTAINS term)`. Reduce `fetch_limit` to `top_k * 2` since server-side filtering eliminates most nodes before transfer. Use `apoc.text.levenshteinSimilarity` or Neo4j full-text search indexes for name matching at the database layer.

---

### [LOW] SERIALIZATION: Embedding vectors formatted as ASCII strings rather than native pgvector type

**File**: `src/semantic/embeddings.py:124`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def store_embedding(self, session, fragment_id, embedding):
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    query = text("UPDATE evidence_fragments SET embedding = :embedding WHERE id = :fragment_id")
    await session.execute(query, {"embedding": vector_str, "fragment_id": fragment_id})
```
**Description**: The 768-dimensional embedding vector is converted to an ASCII string representation before being sent to PostgreSQL via raw SQL. Each 768-float vector produces approximately 6-10 KB of text. PostgreSQL must parse this string into a native `vector` type on every write and every similarity query. This same pattern is used in `search_similar`, `store_embeddings_batch`, and `src/rag/retrieval.py`. The `pgvector` Python package provides a SQLAlchemy type that handles efficient binary wire encoding automatically.

**Risk**: LOW per individual operation. At scale the cumulative ASCII parse overhead on the PostgreSQL server is measurable. The raw SQL also bypasses SQLAlchemy's ORM type safety.
**Recommendation**: Use `pgvector.sqlalchemy.Vector` as the column type on `EvidenceFragment.embedding` and pass embedding values as Python lists or numpy arrays directly through the ORM. This removes the manual string formatting from all call sites.

---

### [LOW] CONNECTION POOL: Default pool settings unsafe for multi-worker deployments

**File**: `src/core/database.py:39`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
engine = create_async_engine(
    settings.database_url or "",
    pool_size=settings.db_pool_size,      # default: 20
    max_overflow=settings.db_max_overflow, # default: 10
    pool_pre_ping=True,
    pool_recycle=300,
)
```
**Description**: With `pool_size=20` and `max_overflow=10`, each uvicorn worker can hold up to 30 PostgreSQL connections. The default uvicorn deployment uses 4 workers, producing up to 120 connections. PostgreSQL's default `max_connections=100` is less than this — a standard 4-worker deployment exhausts the connection limit under full load before overflow connections are counted. The `db_pool_size` and `db_max_overflow` config values are documented but carry no warning about the per-worker multiplication effect.

**Risk**: In multi-worker deployments without PgBouncer, connection exhaustion produces `asyncpg.exceptions.TooManyConnectionsError` under load. The defaults are appropriate for single-worker dev mode but dangerous for production deployments.
**Recommendation**: Reduce defaults to `pool_size=5, max_overflow=5`. Add a docstring comment: `# This is per-worker. Total connections = pool_size * num_workers. Ensure total < postgres max_connections.` Use PgBouncer in transaction pooling mode for production deployments to decouple application pool size from PostgreSQL connection limits.

---

### [LOW] RATE LIMITER: In-process RateLimitMiddleware state is not shared across workers

**File**: `src/api/middleware/security.py:95`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP rate limiter.

    Note: This is per-process only. In multi-worker deployments the
    effective limit is ``workers * max_requests``. For production
    multi-worker deployments, replace with Redis-backed rate limiting.
    """
    def __init__(self, app, max_requests=100, window_seconds=60):
        self._clients: dict[str, _RateLimitEntry] = defaultdict(_RateLimitEntry)
```
**Description**: The `RateLimitMiddleware` docstring correctly documents this limitation but the code remains in production use. In a 4-worker deployment, each worker allows 100 requests/minute per IP, making the effective limit 400 requests/minute. A determined client can trivially bypass the rate limit by cycling connections across workers. The `_prune_stale` method runs a full linear scan of `self._clients` on every 1,000th request or when the dict exceeds 50,000 entries — both conditions represent O(N) scans in the hot path.

**Risk**: The rate limit is functionally ineffective in multi-worker deployments. The per-IP limit multiplies by worker count, making it suitable only for single-worker or development deployments.
**Recommendation**: The comment acknowledges the correct fix: Redis-backed rate limiting. Use `slowapi` with a Redis backend (the `limiter` from `src/api/routes/auth.py` already uses `slowapi` — extend it to cover all routes). Remove `RateLimitMiddleware` once `slowapi` covers the same routes.

---

## Performance Risk Score

**Overall Risk: HIGH**

The async foundation is sound — routes use `async def`, SQLAlchemy sessions are properly managed, database engine uses `asyncpg`, and the embedding generation path already performs batch operations correctly. The primary risks concentrate in three areas:

1. **N+1 write patterns in the intelligence pipeline** (CRITICAL + HIGH): `generate_fragment_embeddings` uses a per-row UPDATE loop despite a batch method existing in the same service class. The CO_OCCURS_WITH relationship loop and all four semantic bridges issue one Neo4j write transaction per matching pair. The batch infrastructure (`batch_create_relationships`, `store_embeddings_batch`) is already implemented and just needs to be wired in.

2. **Unbounded in-memory state** (HIGH): `AlertEngine` accumulates every alert and notification log entry without eviction. For long-running monitoring workers this is a slow memory leak that degrades query performance over time as the Python-level list filters grow.

3. **Infrastructure defaults that do not scale** (HIGH + LOW): The PostgreSQL connection pool defaults exceed PostgreSQL's default `max_connections` in a 4-worker deployment. The in-process rate limiter is documented as ineffective in multi-worker deployments but remains the primary rate limiting mechanism for non-auth routes.

No blocking `time.sleep()` calls were found in async handlers. The chunking pipeline, dashboard routes, and copilot history endpoint all use correct pagination with LIMIT/OFFSET. The `get_settings()` call in SecurityHeadersMiddleware is cheap due to `lru_cache` but represents an avoidable hot-path call that should be resolved at construction time.
