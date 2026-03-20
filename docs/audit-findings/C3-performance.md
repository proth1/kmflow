# C3: Performance Audit Findings

**Auditor**: C3 (Performance Auditor)
**Date**: 2026-03-20
**Scope**: N+1 queries, async anti-patterns, memory leaks, connection pooling, caching strategy
**Files examined**: `src/api/routes/evidence.py`, `src/api/routes/engagements.py`, `src/api/routes/graph.py`, `src/api/routes/pipeline_quality.py`, `src/api/middleware/security.py`, `src/evidence/pipeline.py`, `src/semantic/graph.py`, `src/semantic/embeddings.py`, `src/semantic/builder.py`, `src/semantic/bridges/process_evidence.py`, `src/taskmining/semantic_bridge.py`, `src/rag/embeddings.py`, `src/core/regulatory.py`, `src/core/database.py`, `src/core/neo4j.py`, `src/core/config.py`, `src/evaluation/graph_health.py`, `src/monitoring/pipeline/continuous.py`, `src/api/main.py`, `src/quality/metrics_collector.py`, `src/quality/instrumentation.py`, `agent/python/kmflow_agent/buffer/manager.py`, `agent/python/kmflow_agent/ipc/socket_server.py`, `agent/python/kmflow_agent/upload/batch_uploader.py`, `agent/python/kmflow_agent/gdpr/retention.py`, `agent/python/kmflow_agent/gdpr/audit_logger.py`, `src/integrations/apex_clearing.py`, `src/integrations/charles_river.py`

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 4     |
| MEDIUM   | 6     |
| LOW      | 5     |
| **Total** | **16** |

---

## Findings

### [CRITICAL] N+1 GRAPH READ: `search_similar` in `KnowledgeGraphService` issues one `get_node()` call per pgvector result row

**File**: `src/semantic/graph.py:612`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
rows = result.fetchall()
results: list[dict[str, Any]] = []
for row in rows:
    entity_id = str(row.evidence_id)
    node = await self.get_node(entity_id)   # one Neo4j round-trip per row
```
**Description**: `KnowledgeGraphService.search_similar` executes a pgvector query that returns `top_k` rows (default 10), then enters a loop that calls `self.get_node(entity_id)` once per row. Each `get_node` call opens `async with self._driver.session()`, runs `MATCH (n {id: $node_id}) RETURN n, labels(n)`, and closes the session. For `top_k=10` this is 10 sequential Neo4j sessions opened and closed after every pgvector search. This is called from the RAG retrieval pipeline on every copilot query.

**Risk**: Each `get_node` round-trip adds approximately 2-5ms of Neo4j latency. For `top_k=10`, this adds 20-50ms to every semantic search operation. The RAG copilot and graph search endpoints call this path on every user query. Under concurrent load with 20 simultaneous copilot sessions, this generates 200 sequential Neo4j queries that could otherwise be a single `MATCH (n) WHERE n.id IN $ids` batch fetch.

**Recommendation**: Replace the per-row `get_node` loop with a single batch query: collect all `entity_id` values from the pgvector results into a list, then issue `MATCH (n) WHERE n.id IN $ids RETURN n, labels(n)` once. Build a lookup dict from the batch result and map rows to nodes without per-row round-trips.

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
**Description**: The `build_fragment_graph` function in `pipeline.py` creates CO_OCCURS_WITH relationships inside a triple-nested loop (evidence items × entity pairs). Each `create_relationship` call opens a new `async with self._driver.session()` context and issues a single `MATCH ... CREATE` Cypher statement. For an evidence item with 20 co-occurring entities this generates up to 190 sequential Neo4j sessions. `KnowledgeGraphService.batch_create_relationships()` at `src/semantic/graph.py:387` implements the correct `UNWIND`-based batch path but is not used here. The builder module (`src/semantic/builder.py`) correctly uses `batch_create_relationships` for the same operation — only this older pipeline function does not.

**Risk**: A moderately complex document producing 30 entities and 30 evidence nodes generates up to 435 sequential Neo4j round-trips for relationships alone, each with its own session open/close overhead of 2-5ms. This accumulates to approximately 1-2 seconds of Neo4j overhead per document, executed synchronously inside the upload request handler.

**Recommendation**: Collect all (from_id, to_id, properties) tuples for CO_OCCURS_WITH relationships into a list before the loop, then call `graph_service.batch_create_relationships("CO_OCCURS_WITH", rels)` once after. This reduces O(N²) sessions to a single `UNWIND`-based transaction matching the pattern already used in `builder.py`.

---

### [HIGH] N+1 GRAPH READS: `build_governance_chains` in `RegulatoryOverlayEngine` issues `get_node()` and `get_relationships()` once per process node inside a loop

**File**: `src/core/regulatory.py:171`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for proc in process_nodes:
    rels = await self._graph.get_relationships(proc.id, direction="outgoing",
                                               relationship_type="GOVERNED_BY")
    for rel in rels:
        policy_node = await self._graph.get_node(rel.to_id)
        if policy_node:
            chain.policies.append(...)
```
**Description**: `build_governance_chains` iterates over every process node and calls `get_relationships()` once per process (one Neo4j session per process node), then calls `get_node()` once per returned relationship (one more Neo4j session per related policy). Additionally, the node creation loop above this (lines 106-168) calls `get_node()` individually for each policy, control, and regulation before potentially calling `create_node()` — yielding 3 round-trips per entity for the existence check pattern (`get_node` + conditional `create_node`). For an engagement with 10 processes and 5 policies each, this generates 10 + (10*5) = 60 sequential Neo4j sessions for traversal alone.

**Risk**: `build_governance_chains` is called from the regulatory overlay route. For engagements with 50 processes and moderate policy coverage, this can generate 250+ sequential Neo4j sessions. The `get_node` existence check before `create_node` is also avoidable — Neo4j's `MERGE` operation handles upsert atomically without a prior read.

**Recommendation**: Replace the per-process `get_relationships` loop with a single Cypher query: `MATCH (p {engagement_id: $eid})-[r:GOVERNED_BY]->(pol) RETURN p.id, pol.id, pol.name`. Replace the `get_node` + `create_node` pattern with `MERGE (n:{label} {id: $id}) ON CREATE SET n = $props` to eliminate the read-before-write. Replace per-entity `get_node` existence checks with `batch_create_nodes` (which already uses `CREATE` not `MERGE` — consider adding a `batch_upsert_nodes` using `MERGE`).

---

### [HIGH] MEMORY LEAK: `AlertEngine` accumulates all alerts and notification log entries in unbounded in-memory lists

**File**: `src/monitoring/alerting/engine.py`
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
**Description**: `AlertEngine` stores every generated alert and every notification dispatch event in plain Python lists with no eviction, TTL, or size cap. The `query_alerts` method filters `self.alerts` entirely in Python, performing a full linear scan on every API call. Since `AlertEngine` is a long-lived object (monitoring worker or singleton), these lists grow for the lifetime of the process. The `_open_alerts` dict in `AlertDeduplicator` has a `clear_expired()` method but it is never called automatically by the engine.

**Risk**: In a high-alert environment processing hundreds of events per hour, `self.alerts` accumulates without bound. After days of operation, a query applying 6 Python-level filters against a 100,000-element list executes a full linear scan on every call to `/api/v1/monitoring/alerts`. `_notification_log` has no cap at all and accumulates the full payload of every alert dispatched.

**Recommendation**: Persist alerts to the database (the `MonitoringAlert` model already exists) and remove the in-memory store. If a hot-path cache is needed, cap it with `collections.deque(maxlen=1000)`. Call `deduplicator.clear_expired()` on a schedule (e.g., every 1,000 events or every 60 seconds).

---

### [HIGH] UNBOUNDED GRAPH TRAVERSAL: `_count_components` in graph health analysis fetches all edges with no LIMIT

**File**: `src/evaluation/graph_health.py:94`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
edge_result = await neo4j_session.run(
    "MATCH (a {engagement_id: $eid})--(b {engagement_id: $eid}) "
    "RETURN id(a) AS a_id, id(b) AS b_id",
    eid=engagement_id,
)
async for record in edge_result:
    uf._ensure(a_id)
    uf._ensure(b_id)
    uf.union(a_id, b_id)
```
**Description**: `_count_components` fetches every edge in the engagement's subgraph — both directions (no `LIMIT`) — and streams all records into a Python union-find structure. For a 500-node engagement with average degree 10, this transfers 5,000 edge records across the Neo4j driver connection. The union-find is computed entirely in Python rather than using a graph algorithm at the database layer. This function is called inside `analyze_graph_health` which uses a single `async with neo4j_driver.session()` for all 10 health queries sequentially, holding the Neo4j session open for the full analysis duration.

**Risk**: For large engagements (1,000+ nodes), this query transfers tens of thousands of records to Python for an algorithm that could be approximated with a much cheaper Cypher query. The graph health endpoint is not paginated and returns the full analysis in a single synchronous pass.

**Recommendation**: Add `LIMIT 10000` to the edge query to prevent runaway transfers on large graphs and log a warning when the limit is hit. Consider whether connected component count is needed at all or if a simpler approximation (orphan node count) suffices. If precision is required, run the analysis as a background job rather than in a synchronous API handler.

---

### [MEDIUM] MISSING NEO4J INDEXES: `engagement_id` property not indexed on most node labels

**File**: `src/core/neo4j.py:84`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
indexes = [
    "CREATE INDEX IF NOT EXISTS FOR (p:Process) ON (p.engagement_id)",
    "CREATE INDEX IF NOT EXISTS FOR (e:Evidence) ON (e.engagement_id, e.category)",
    "CREATE INDEX IF NOT EXISTS FOR (a:Activity) ON (a.process_id)",
    "CREATE INDEX IF NOT EXISTS FOR (g:Gap) ON (g.engagement_id, g.severity)",
]
```
**Description**: Only 4 of the 13 constrained node labels (Process, Evidence, Activity, Gap) have `engagement_id` indexes. All Cypher queries in `KnowledgeGraphService` scope by `engagement_id` — including `find_nodes`, `get_stats`, `get_engagement_subgraph`, `traverse`, and `delete_engagement_subgraph`. Labels missing `engagement_id` indexes include: Role, System, Control, Policy, Regulation, TOM, Document, Subprocess, Decision. Every query against these labels performs a full label scan filtered in Neo4j's execution engine by property comparison rather than an index seek.

**Risk**: For an engagement with 500 Role nodes across multiple engagements, `find_nodes("Role", {"engagement_id": "..."})` must scan all Role nodes across all engagements rather than seeking directly to the matching ones. This degrades linearly as the number of engagements and nodes grows.

**Recommendation**: Add `engagement_id` indexes for all node labels that are queried by engagement scope: Role, System, Control, Policy, Regulation, TOM, Document, Subprocess, Decision. Also add `UserAction` and `Application` which are used by the task mining semantic bridge. Pattern: `"CREATE INDEX IF NOT EXISTS FOR (n:{Label}) ON (n.engagement_id)"`.

---

### [MEDIUM] MEMORY: Full file content read into memory before size validation on upload

**File**: `src/api/routes/evidence.py:180`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
@router.post("/upload", ...)
async def upload_evidence(...):
    file_content = await file.read()   # reads up to 100MB into process memory
    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    ...
    # size check and MIME detection happen inside ingest_evidence()
```
**Description**: The upload handler reads the entire file into process memory before any size validation. `MAX_UPLOAD_SIZE = 100 MB` is enforced inside `ingest_evidence`, not before. A client can send a 100 MB file and have all 100 MB buffered in the Python process before rejection. With concurrent uploads, the server buffers `concurrent_uploads × 100 MB` before any are validated. MIME detection via `magic.from_buffer` only reads the first 8 KB; SHA-256 hashing supports incremental streaming — neither requires the full file in memory simultaneously.

**Risk**: 10 concurrent 100 MB uploads hold up to 1 GB of file bytes in process memory simultaneously. On a container with 2 GB memory limit, this can exhaust available memory before a single upload completes processing.

**Recommendation**: Check `Content-Length` header or read the first chunk before `await file.read()` to enforce the size limit early. For MIME detection, use only `await file.read(8192)` then seek back. Compute SHA-256 incrementally using `hashlib.sha256()` updated in chunks. Long-term, stream directly to MinIO/object storage and avoid buffering file content in the API worker process at all.

---

### [MEDIUM] PER-REQUEST INSTANTIATION: `EmbeddingService()` constructed fresh on every `semantic_search` call

**File**: `src/api/routes/graph.py:238`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
@router.get("/search", response_model=list[SearchResult])
async def semantic_search(query: str, top_k: int = 10, ...) -> list[dict[str, Any]]:
    ...
    embedding_service = EmbeddingService()   # new instance on every request
    results = await embedding_service.search_by_text(...)
```
**Description**: `semantic_search` constructs a new `EmbeddingService()` instance on every request. `EmbeddingService.__init__` calls `_get_rag_embedding_service()` which returns a singleton — so the SentenceTransformer model is not re-loaded. However, the `EmbeddingService` object itself is constructed and garbage-collected on every call. Separately, the `get_embedding_service` dependency function (line 122) is defined but not used in `semantic_search` — it constructs the service inline instead. The `src/rag/embeddings.py` module already provides a `get_embedding_service()` singleton factory for exactly this purpose.

**Risk**: LOW per individual call. The concern is the inconsistent pattern: the dependency function `get_embedding_service()` exists in the same file but is bypassed. This creates confusion about which code path actually runs, and makes it harder to swap embedding backends or inject test doubles.

**Recommendation**: Use the `get_embedding_service()` FastAPI dependency already defined in the same file: `embedding_service: EmbeddingService = Depends(get_embedding_service)`. This aligns with the dependency injection pattern used throughout other routes and makes the service substitutable in tests.

---

### [MEDIUM] O(N²) IN-PYTHON COSINE SIMILARITY: Task mining semantic bridge scores all UserAction×Activity pairs sequentially

**File**: `src/taskmining/semantic_bridge.py:122`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for i, ua_node in enumerate(user_actions):
    best_sim = 0.0
    best_act_idx = -1
    for j, _act_node in enumerate(activities):
        sim = _cosine_similarity(ua_embeddings[i], act_embeddings[j])
        if sim > best_sim:
            best_sim = sim
            best_act_idx = j
```
**Description**: `_link_actions_to_activities` and `_link_apps_to_systems` compute cosine similarity for every (UserAction, Activity) and (Application, System) pair using a Python-level nested loop. For N UserActions and M Activities, this is O(N×M) Python function calls each performing a NumPy dot product. The `_MAX_NODES = 10000` constant at the top of the file means these loops can run up to 100,000,000 iterations. Individually, each call to `_cosine_similarity` creates two NumPy arrays, computes norms, and a dot product — manageable per call but expensive in aggregate. The correct approach is to use NumPy matrix operations to compute all pairwise similarities in one vectorized call.

**Risk**: For an engagement with 500 UserActions and 200 Activities, this executes 100,000 Python function calls with NumPy array construction on each. At ~5µs per call, this takes approximately 500ms of CPU time per bridge run, executed synchronously within the request handler.

**Recommendation**: Replace the nested loop with NumPy matrix multiplication: `similarity_matrix = ua_embeddings_np @ act_embeddings_np.T` where both are pre-normalized. Then use `np.argmax(similarity_matrix, axis=1)` and `np.max(similarity_matrix, axis=1)` to find best matches in vectorized form. This reduces O(N×M) Python calls to a single BLAS matrix multiply.

---

### [LOW] SERIALIZATION: Embedding vectors serialized as ASCII strings instead of using pgvector native type

**File**: `src/semantic/embeddings.py:124`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def store_embedding(self, session, fragment_id, embedding):
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
    query = text("UPDATE evidence_fragments SET embedding = :embedding WHERE id = :fragment_id")
    await session.execute(query, {"embedding": vector_str, "fragment_id": fragment_id})
```
**Description**: The 768-dimensional embedding vector is serialized to an ASCII string (approximately 6-10 KB of text per vector) before being sent to PostgreSQL. PostgreSQL must parse this string into a native `vector` type on every write and every similarity query. This pattern is used in `store_embedding`, `store_embeddings_batch`, `search_similar`, and `src/semantic/graph.py:search_similar`. The `pgvector` Python package provides a `sqlalchemy.Vector` type that handles binary wire encoding automatically, eliminating the text serialization round-trip.

**Risk**: LOW per individual operation. At scale — storing embeddings for 10,000 fragments or running 1,000 similarity searches — the cumulative ASCII-parse overhead on the PostgreSQL server becomes measurable. The raw SQL also bypasses SQLAlchemy's ORM type system.

**Recommendation**: Declare `embedding = mapped_column(Vector(768))` on `EvidenceFragment` using `pgvector.sqlalchemy.Vector`. Pass embedding values as Python lists directly through the ORM. This removes the manual string formatting from all four call sites and uses the optimized binary protocol.

---

### [LOW] CONNECTION POOL: Default pool settings can exceed PostgreSQL `max_connections` in multi-worker deployments

**File**: `src/core/database.py:39`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
engine = create_async_engine(
    settings.database_url or "",
    pool_size=settings.db_pool_size,       # default: 20
    max_overflow=settings.db_max_overflow,  # default: 10
    pool_pre_ping=True,
    pool_recycle=300,
)
```
**Description**: With `pool_size=20` and `max_overflow=10`, each uvicorn worker can hold up to 30 PostgreSQL connections. The default uvicorn deployment uses 4 workers, producing a maximum of 120 connections. PostgreSQL's default `max_connections=100` is less than this figure — a standard 4-worker production deployment can exhaust the PostgreSQL connection limit under peak load before overflow connections are even counted. The settings are documented in `config.py` but carry no warning about the per-worker multiplication effect.

**Risk**: In multi-worker deployments without PgBouncer, connection exhaustion produces `asyncpg.exceptions.TooManyConnectionsError` under sustained load. The defaults are appropriate for single-worker development but dangerous for production with 4+ workers.

**Recommendation**: Reduce defaults to `db_pool_size=5, db_max_overflow=5` (giving 40 total connections for 4 workers). Add a startup warning if `pool_size * expected_workers > postgres_max_connections`. Document that PgBouncer in transaction pooling mode should be used for production deployments to decouple application pool size from PostgreSQL connection limits.

---

### [LOW] RATE LIMITER: `RateLimitMiddleware` operates per-worker; effective limit multiplies by worker count

**File**: `src/api/middleware/security.py:98`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed per-IP rate limiter (multi-worker safe).
    Uses an atomic Lua script (INCR + EXPIRE) for fixed-window counting.
    Each client IP gets a Redis key ``ratelimit:{ip}`` with a TTL equal
    to the window. The counter is shared across all uvicorn workers via
    the same Redis instance.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ...
        if redis_client is not None:
            result = await redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, self.window_seconds)
```
**Description**: The `RateLimitMiddleware` is correctly Redis-backed and multi-worker-safe when Redis is available. However, it explicitly fail-opens (`count = 0`) when Redis is unavailable. During a Redis outage, all rate limiting is silently disabled — there is no fallback in-process counter, no header indicating that limiting is inactive, and no alert or metric increment. The Lua script atomically handles the `INCR + EXPIRE` correctly, but the `except Exception` catch is overly broad and swallows all Redis errors including connection refused, timeout, and script errors.

**Risk**: During a Redis outage, the rate limiter provides zero protection. A client performing a brute-force attack coinciding with a Redis restart can bypass all rate limits without any indication in logs beyond a single DEBUG message.

**Recommendation**: Log at WARNING (not DEBUG) when Redis is unavailable so the failure is visible in monitoring. Consider adding a lightweight in-process fallback counter (per-IP, evicting old entries) that limits to `max_requests * 5` during Redis unavailability, providing degraded but non-zero protection. Increment a `ratelimit.redis_failures` metric counter when the exception is caught.

---

## Performance Risk Score

**Overall Risk: HIGH**

The async and database infrastructure is sound — routes use `async def`, SQLAlchemy uses asyncpg, the embedding pipeline uses batch operations for the primary path, and connection pooling is configured. The primary risks concentrate in three areas:

1. **N+1 graph operation patterns** (CRITICAL + HIGH + HIGH): `KnowledgeGraphService.search_similar` issues one Neo4j `get_node` call per pgvector result row. The `build_fragment_graph` CO_OCCURS_WITH loop calls `create_relationship` per pair rather than using the existing `batch_create_relationships`. The `RegulatoryOverlayEngine` performs `get_relationships` and `get_node` per process node. In each case, the batch infrastructure already exists in the codebase and just needs to be wired in.

2. **Unbounded in-memory state** (HIGH): `AlertEngine` accumulates every alert and notification log entry without eviction. The graph health `_count_components` fetches all engagement edges with no LIMIT clause.

3. **Computational inefficiency** (MEDIUM): The task mining semantic bridge uses a Python nested loop for O(N×M) cosine similarity when NumPy matrix multiplication can reduce this to a single BLAS operation.

Several previously-reported issues have been resolved: `generate_fragment_embeddings` now uses `store_embeddings_batch` as the primary path (N+1 is only in the error fallback). `ProcessEvidenceBridge` correctly uses `batch_create_relationships`. `SecurityHeadersMiddleware` pre-builds all static headers in `__init__` — no per-request settings access.

---

## New Findings (2026-03-20 — Batch 7 additions)

Files added in scope: `src/quality/metrics_collector.py`, `src/quality/instrumentation.py`, `src/api/routes/pipeline_quality.py`, `agent/python/kmflow_agent/buffer/manager.py`, `agent/python/kmflow_agent/buffer/encryption.py`, `agent/python/kmflow_agent/ipc/socket_server.py`, `agent/python/kmflow_agent/upload/batch_uploader.py`, `agent/python/kmflow_agent/gdpr/retention.py`, `agent/python/kmflow_agent/gdpr/purge.py`, `agent/python/kmflow_agent/gdpr/audit_logger.py`, `agent/python/kmflow_agent/pii/patterns.py`, `src/integrations/apex_clearing.py`, `src/integrations/charles_river.py`

---

### [MEDIUM] SEQUENTIAL DASHBOARD QUERIES: `get_dashboard` executes 5 independent DB queries sequentially

**File**: `src/api/routes/pipeline_quality.py:396`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
stages = await get_pipeline_stages(engagement_id, ...)
retrieval = await get_retrieval_summary(engagement_id, ...)
entities = await get_entity_summary(engagement_id, ...)
graph_health = await get_graph_health(engagement_id, ...)
satisfaction = await get_copilot_satisfaction(engagement_id, ...)
```
**Description**: The `get_dashboard` endpoint calls five separate route handler functions sequentially, each issuing one or more database queries against five different tables. Because these are independent queries (no cross-query dependencies), all five could run concurrently using `asyncio.gather`. As written, the total response time is the sum of all five query latencies rather than the maximum. At moderate data sizes, each query takes 5-20ms — the sequential sum adds 25-100ms of unnecessary latency to every dashboard load.

**Risk**: MEDIUM. Under normal load this is a latency regression, not a resource concern. The queries share a single SQLAlchemy `AsyncSession`, which does support concurrent statement execution via the asyncpg driver. However, because each handler is called directly (not as a coroutine via `gather`), they run fully sequentially. As data grows, the retrieval summary (multi-step group-by with subquery) and entity summary (cross-join with evidence_items) will be the slowest sections.

**Recommendation**: Wrap the five calls in `asyncio.gather` with `return_exceptions=True` to run them concurrently. Each sub-result should be handled individually for errors, replacing the five try/except blocks. Note: sharing a single `AsyncSession` across concurrent coroutines is safe with asyncpg but requires the session to not use the same underlying connection state simultaneously — consider whether `asyncio.gather` is appropriate here or whether separate sessions per call are safer. If session sharing is a concern, use `asyncio.TaskGroup` with explicit exception handling per task.

---

### [MEDIUM] SYNC BLOCKING IN ASYNC LOOP: `RetentionEnforcer.run` calls synchronous `enforce_now` directly in async task

**File**: `agent/python/kmflow_agent/gdpr/retention.py:84`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def run(self, shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        self.enforce_now()   # synchronous SQLite I/O in async loop
        try:
            await asyncio.wait_for(...)
```
**Description**: `RetentionEnforcer.run` is an async method that calls `self.enforce_now()` synchronously. `enforce_now` performs blocking SQLite I/O — `sqlite3.connect`, `conn.execute("DELETE FROM events WHERE ...")`, and `conn.commit()` — directly on the asyncio event loop without offloading to a thread executor. Since the SQLite `DELETE` can scan a large events table, this blocks the event loop for the full duration of the database operation. The `BufferManager` class in the same module correctly uses `asyncio.to_thread` for all its SQLite operations, making `RetentionEnforcer.run`'s inline synchronous call inconsistent with the established pattern.

**Risk**: If the local SQLite database contains tens of thousands of events (the 100 MB limit allows ~50,000-100,000 rows), a `DELETE WHERE timestamp < ?` without an index on `timestamp` may take 10-50ms. This blocks the event loop, pausing IPC message handling from the Swift capture layer. The socket server's `asyncio.sleep(0.5)` poll loop relies on a responsive event loop.

**Recommendation**: Wrap the call in `asyncio.to_thread`: `await asyncio.to_thread(self.enforce_now)`. This matches the pattern used by `BufferManager._db_write_event` and `_db_read_pending`. Alternatively, consider whether `retention.py` should add an index on `timestamp` to the SQLite schema (currently only `ix_events_uploaded` is created).

---

### [LOW] REPEATED KEYCHAIN SUBPROCESS CALL: `BufferManager._default_key` spawns subprocess on every instantiation

**File**: `agent/python/kmflow_agent/buffer/manager.py:57`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
def _default_key(self) -> bytes:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", ..., "-w"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return base64.b64decode(result.stdout.strip())[:32]
```
**Description**: Every time `BufferManager` is constructed, `_default_key` is called, which spawns a `security find-generic-password` subprocess to retrieve the AES-256-GCM key from the macOS Keychain. The subprocess fork+exec overhead for the `security` CLI is approximately 10-30ms. `BufferManager` is instantiated once at agent startup (the `SocketServer`, `BatchUploader`, and `RetentionEnforcer` all share a single instance), so this is a one-time cost — but if the `BufferManager` were ever reinstantiated (e.g., in tests or after a failure recovery), the Keychain call repeats unnecessarily.

**Risk**: LOW — single instantiation at startup. The primary concern is test isolation: test code that creates multiple `BufferManager` instances (e.g., `test_batch_uploader.py`) spawns multiple `security` subprocesses, which can slow test execution and fails in CI environments where the macOS Keychain is unavailable. The fallback to env var (`KMFLOW_BUFFER_KEY`) mitigates this for CI, but the code path is not documented for test authors.

**Recommendation**: Cache the retrieved key at the class level after first retrieval: `BufferManager._cached_key: bytes | None = None`. Add a docstring note that `KMFLOW_BUFFER_KEY` env var must be set in test environments. No structural change needed.

---

### [LOW] AUDIT LOG UNBOUNDED GROWTH: `AuditLogger` appends to a flat file with no rotation or size limit

**File**: `agent/python/kmflow_agent/gdpr/audit_logger.py:28`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
def _append(self, entry: dict[str, Any]) -> None:
    with open(self._log_path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
```
**Description**: `AuditLogger` appends to a single `audit.jsonl` file in `~/Library/Application Support/KMFlowAgent/` with no size limit, rotation, or TTL. Each open/write/close cycle incurs a system call round-trip. For high-frequency consent change events or purge cycles, this can accumulate a large file over time. The file is not compressed, and no cleanup mechanism exists alongside the `RetentionEnforcer` (which only cleans the `events` table in SQLite, not the audit log file). On a device used for months, the audit log could grow to tens of megabytes.

**Risk**: LOW — file I/O is fast for append-only writes. The main concern is unbounded disk usage and the per-call open/write/close overhead compared to buffered logging. Unlike the SQLite buffer (which has the 100 MB prune logic), the audit log has no upper bound.

**Recommendation**: Use Python's `logging.handlers.RotatingFileHandler` with `maxBytes=5MB` and `backupCount=3` to replace the manual open/write pattern. This provides automatic rotation, buffered writes, and a 15 MB total cap at zero implementation cost. The change is backward-compatible — existing `audit.jsonl` contents are preserved.

