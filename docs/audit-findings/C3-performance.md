# C3: Performance Audit Findings

**Auditor**: C3 (Performance Auditor)
**Date**: 2026-02-20
**Scope**: N+1 queries, async anti-patterns, memory leaks, connection pooling, caching strategy

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 5 |
| MEDIUM   | 5 |
| LOW      | 3 |
| **Total** | **14** |

---

## Findings

### [CRITICAL] N+1 QUERY: Batch validation executes one DB query per evidence item

**File**: `src/api/routes/evidence.py:342`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for eid in payload.evidence_ids:
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == eid))
    evidence = result.scalar_one_or_none()
    if not evidence:
        errors.append(f"Evidence item {eid} not found")
        continue
    evidence.validation_status = payload.validation_status
```
**Description**: The `batch_validate` endpoint iterates over `payload.evidence_ids` and issues a separate `SELECT` query for each ID inside the loop. If a caller submits 100 evidence IDs, this generates 100 sequential database round-trips within a single request. There is no upper bound on the list size enforced in the schema.
**Risk**: Severe latency degradation under realistic batch sizes. A batch of 500 items generates 500 sequential async DB calls; each round-trip at ~1ms produces a 500ms minimum latency before any application logic runs. Combined with the single shared connection from the session pool, this serializes work that could be batched.
**Recommendation**: Fetch all IDs in one query using `WHERE id IN (...)`, then update in a single `UPDATE ... WHERE id IN (...)` statement or use SQLAlchemy's `bulk_update_mappings`. Add a schema-level `max_items` constraint (e.g., 200) on `BatchValidationRequest.evidence_ids`.

---

### [HIGH] N+1 QUERY: Knowledge graph node creation issues one Neo4j session per node

**File**: `src/semantic/builder.py:175` and `src/evidence/pipeline.py:402`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for entity in entities:
    label = _ENTITY_TYPE_TO_LABEL.get(entity.entity_type)
    if not label:
        continue
    try:
        node = await self._graph.create_node(label, properties)
        entity_to_node[entity.id] = node.id
```
**Description**: `_create_nodes` and `build_fragment_graph` loop over all resolved entities and call `graph_service.create_node()` individually. Each `create_node` call opens a new `async with self._driver.session()` context and runs one `CREATE` Cypher statement. For an engagement with 1000 extracted entities, this generates 1000 individual Neo4j sessions and transactions.
**Risk**: Neo4j session creation overhead dominates for large engagements. The `_create_co_occurrence_relationships` loop has the same pattern, creating one session per pair — which can be O(N²) in the number of entities per document. This is a blocking bottleneck that holds the request open for the full duration of graph construction.
**Recommendation**: Use `UNWIND` in Cypher to batch-create nodes in a single transaction: `UNWIND $nodes AS props CREATE (n:Label) SET n = props`. Similarly batch relationships. Move graph construction to a background task (`fastapi.BackgroundTasks`) so the upload endpoint returns immediately.

---

### [HIGH] N+1 QUERY: Entity extraction called sequentially per fragment in builder

**File**: `src/semantic/builder.py:147`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for fragment_id, content, evidence_id in fragments:
    result = await extract_entities(content, fragment_id=fragment_id)
    for entity in result.entities:
        all_entities.append(entity)
```
**Description**: `_extract_all_entities` in `KnowledgeGraphBuilder` and `extract_fragment_entities` in `pipeline.py` both process fragments sequentially in a Python loop. Entity extraction likely involves an LLM or NLP model call that is I/O-bound. Processing N fragments sequentially when they could run concurrently wastes significant time on large evidence uploads.
**Risk**: Linear time growth with fragment count. A document with 50 fragments processed sequentially at 200ms per extraction takes 10 seconds. These operations could safely run concurrently with `asyncio.gather`.
**Recommendation**: Use `asyncio.gather(*[extract_entities(frag.content, ...) for frag in fragments])` to parallelize extraction across all fragments. Apply a semaphore to cap concurrent LLM calls if rate limiting is a concern.

---

### [HIGH] UNBOUNDED QUERY: `get_engagement_subgraph` fetches all nodes without LIMIT

**File**: `src/semantic/graph.py:429`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
node_query = """
MATCH (n {engagement_id: $engagement_id})
RETURN n, labels(n) AS labels
"""
node_records = await self._run_query(node_query, {"engagement_id": engagement_id})
```
**Description**: `get_engagement_subgraph` fetches every node and every relationship for an engagement with no `LIMIT` clause. As an engagement accumulates evidence, this query returns the entire subgraph in one result set. The `/subgraph` and `/export/cytoscape` endpoints both call this method and serialize the full result directly into the HTTP response.
**Risk**: For an engagement with 10,000 nodes and 50,000 relationships, the server allocates the entire graph in memory, serializes it to JSON (potentially megabytes), and sends it over HTTP. This causes high memory pressure, large response payloads, and long latencies. The query also performs a full label scan on Neo4j with a property filter (`engagement_id`) that may not be indexed.
**Recommendation**: Add pagination parameters (`skip`, `limit`) to both the Cypher queries and the API endpoints. Add a Neo4j index on `engagement_id` for all node labels. Cap the default response size at a reasonable limit (e.g., 500 nodes).

---

### [HIGH] UNBOUNDED QUERY: Multiple list endpoints missing pagination — load all rows

**File**: `src/api/routes/simulations.py:303`, `src/api/routes/engagements.py:344`, `src/api/routes/tom.py:591`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
# simulations.py:303 - list_scenarios
result = await session.execute(query)
items = [_scenario_to_response(s) for s in result.scalars().all()]
return {"items": items, "total": len(items)}

# engagements.py:344 - get_audit_logs
result = await session.execute(
    select(AuditLog).where(AuditLog.engagement_id == engagement_id).order_by(...)
)
return list(result.scalars().all())
```
**Description**: Several list endpoints call `.all()` with no `LIMIT` or `OFFSET`. The most impactful are: `list_scenarios` (no pagination at all), `get_audit_logs` (no pagination), `list_modifications`, `list_suggestions`, `list_financial_assumptions`, `list_results`, and multiple endpoints in `tom.py` and `regulatory.py`. These fetch every row matching the filter from PostgreSQL into application memory.
**Risk**: Audit log tables grow indefinitely. For an active engagement with 10,000 audit entries, `get_audit_logs` materializes all 10,000 rows in the Python process on every call. This is a linear memory and latency regression as engagement usage grows.
**Recommendation**: Add `limit` and `offset` query parameters to all list endpoints. Return a `total` count via a separate `COUNT(*)` subquery (as the `evidence` and `engagements` list endpoints already do correctly). Enforce a maximum `limit` (e.g., 200).

---

### [HIGH] MEMORY LEAK: Rate limiter `_llm_request_log` uses unbounded global dict

**File**: `src/api/routes/simulations.py:56`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
_LLM_MAX_TRACKED_USERS = 10_000
_llm_request_log: dict[str, list[float]] = defaultdict(list)

def _check_llm_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    window_start = now - _LLM_RATE_WINDOW
    if len(_llm_request_log) > _LLM_MAX_TRACKED_USERS:
        stale = [uid for uid, ts in _llm_request_log.items() if not ts or ts[-1] < window_start]
        for uid in stale:
            del _llm_request_log[uid]
```
**Description**: The eviction logic only runs when the dict exceeds `_LLM_MAX_TRACKED_USERS` (10,000). It evicts by scanning the entire dict linearly — an O(N) operation on every request once the threshold is exceeded. In a multi-worker deployment this state is not shared, so each worker independently accumulates up to 10,000 user entries. The eviction condition `not ts or ts[-1] < window_start` may evict too aggressively (users with recent requests that have timed out but are still active).
**Risk**: In a 4-worker deployment with 40,000 users, each worker allocates up to 10,000 user entries. The O(N) scan on every request above the threshold degrades throughput. Additionally, the comment in the code acknowledges this is broken across workers, meaning the rate limit is ineffective in production.
**Recommendation**: Replace with Redis-based rate limiting using sliding window counters (e.g., `slowapi` with Redis backend). If in-memory is required for single-process deployments, use an LRU cache with TTL (e.g., `cachetools.TTLCache`) which evicts automatically without linear scans.

---

### [MEDIUM] ASYNC ANTI-PATTERN: Embedding generation batches sequentially instead of concurrently

**File**: `src/rag/embeddings.py:99`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def generate_embeddings_async(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embeddings = await self.embed_texts_async(batch)
        all_embeddings.extend(batch_embeddings)
    return all_embeddings
```
**Description**: `generate_embeddings_async` processes batches sequentially in a loop. Each `embed_texts_async` call uses `asyncio.to_thread` to run the SentenceTransformer model in a thread pool. While this avoids blocking the event loop, the batches are still processed one at a time. For large fragment sets, the thread pool has idle capacity during the time between batch completions.
**Risk**: MEDIUM. The thread pool benefit is real, but serial batch processing is slower than it could be. With 4 CPU cores available for threading, running batches concurrently could yield 2-4x speedup for large embedding jobs.
**Recommendation**: Use `asyncio.gather` to process multiple batches concurrently: `await asyncio.gather(*[embed_texts_async(batch) for batch in batches])`. The SentenceTransformer model is thread-safe when accessed via `to_thread`.

---

### [MEDIUM] MEMORY: File content loaded entirely into memory before processing

**File**: `src/evidence/pipeline.py:696`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def ingest_evidence(
    ...
    file_content: bytes,  # entire file in memory
    ...
) -> tuple[EvidenceItem, list[EvidenceFragment], uuid.UUID | None]:
    if len(file_content) > MAX_UPLOAD_SIZE:
        raise HTTPException(...)
    content_hash = compute_content_hash(file_content)
```
**Description**: The entire file content (up to 100MB) is read into memory as `bytes` before any validation or early-rejection happens. The route handler calls `await file.read()` at `evidence.py:151` which buffers the complete file. The `compute_content_hash` function then processes the full bytes in-memory. This means every concurrent file upload holds 100MB in RAM simultaneously.
**Risk**: For 10 concurrent 100MB uploads, the application consumes 1GB+ of RAM just in upload buffers before any processing begins. This is a significant memory amplification point under load.
**Recommendation**: Stream files using `UploadFile.read(chunk_size)` in chunks. Compute the SHA-256 hash incrementally using `hashlib.sha256()` with `update()`. For file type validation, only the first 8KB is needed (`magic.from_buffer` already reads only 8KB). Write the file directly to storage while streaming. Only load into memory if a specific parser requires it.

---

### [MEDIUM] CACHING: No caching on `EmbeddingService` instantiation — new model load per request

**File**: `src/api/routes/graph.py:129`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
def get_embedding_service() -> EmbeddingService:
    """Get the embedding service."""
    return EmbeddingService()

# Called on every semantic search request:
embedding_service = get_embedding_service()
```
**Description**: `get_embedding_service()` creates a new `EmbeddingService` instance on every call. The `EmbeddingService.__init__` sets `self._model = None` with lazy loading. The first call to `embed_text` triggers `SentenceTransformer` model load from disk via `_get_model()`. While subsequent calls reuse the loaded model (stored on the instance), each new instance starts fresh with `_model = None`. In the FastAPI dependency injection context, a new instance is created per request.
**Risk**: The `SentenceTransformer` model loading from disk takes 1-5 seconds. If `_model` is per-instance and each request gets a new instance, the model is potentially reloaded on every semantic search request. This depends on whether Python process-level caching (module globals) or file system caching saves the model.
**Recommendation**: Register `EmbeddingService` as a FastAPI application-level singleton in `app.state` at startup. Inject it via `request.app.state.embedding_service` or use FastAPI's `Depends` with a module-level singleton. This ensures the model is loaded once at startup.

---

### [MEDIUM] NEO4J: One session opened per Cypher query — no session reuse

**File**: `src/semantic/graph.py:112`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def _run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with self._driver.session() as session:
        result = await session.run(query, parameters or {})
        records = await result.data()
        return records
```
**Description**: Every single Cypher query opens a new `driver.session()` context. The Neo4j async driver manages a connection pool internally, but session acquisition and release still has overhead. During graph construction, dozens to hundreds of individual queries are issued sequentially, each with its own session lifecycle. The `_create_nodes` loop calls `create_node` N times, each opening a session.
**Risk**: MEDIUM. Neo4j session creation is lightweight compared to connection creation, but the accumulated overhead of 1000 session open/close cycles during bulk graph construction is measurable. More critically, read queries that could share a session for context are forced to establish fresh sessions.
**Recommendation**: For bulk operations, pass a session explicitly and reuse it across multiple queries in the same operation. Consider using `execute_write` with a single transaction for batch node creation using `UNWIND` Cypher, which also provides ACID guarantees.

---

### [MEDIUM] CACHING: Dashboard endpoint makes 6 sequential DB queries with no caching

**File**: `src/api/routes/dashboard.py:157`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
async def get_dashboard(engagement_id: str, ...) -> dict[str, Any]:
    eng_result = await session.execute(select(Engagement)...)       # query 1
    ev_count_result = await session.execute(select(func.count())...)  # query 2
    pm_count_result = await session.execute(select(func.count())...)  # query 3
    latest_model_result = await session.execute(select(ProcessModel)...)  # query 4
    shelf_items_result = await session.execute(select(ShelfDataRequestItem...)...)  # query 5
    audit_result = await session.execute(select(AuditLog)...)        # query 6
```
**Description**: The dashboard endpoint issues 6 sequential PostgreSQL queries for each page load. Queries 2-6 are all independent and could run concurrently. Additionally, the dashboard data changes infrequently (at the cadence of evidence uploads and model runs) but is loaded on every page view. There is no caching layer.
**Risk**: At 100ms per query, the dashboard takes 600ms minimum. Under concurrent dashboard loads, this creates 6× the DB query load compared to what's needed. Dashboard data for a given engagement rarely changes more than once per minute.
**Recommendation**: Run independent queries concurrently using `asyncio.gather`. Add Redis caching with a 30-60 second TTL for dashboard responses, invalidated on evidence upload or model completion events.

---

### [LOW] SERIALIZATION: Vector embedding stored as string rather than native pgvector type

**File**: `src/semantic/embeddings.py:109`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
query = text("UPDATE evidence_fragments SET embedding = :embedding WHERE id = :fragment_id")
await session.execute(query, {"embedding": vector_str, "fragment_id": fragment_id})
```
**Description**: Embeddings are serialized to a string `"[0.1,0.2,...]"` and stored via a raw SQL string. This skips SQLAlchemy's native pgvector type adapter, requires PostgreSQL to parse the string on every write, and the same pattern is used in `search_similar` for the query vector. The 768-dimensional vector string for a single embedding is approximately 5-8KB of ASCII text.
**Risk**: LOW. The string serialization adds minor overhead per embedding write, and string-to-vector parsing happens in PostgreSQL. The primary concern is code maintainability — the raw SQL bypasses ORM type safety. The search query correctly uses `LIMIT :top_k` so this is contained.
**Recommendation**: Use the `pgvector` Python package's SQLAlchemy type integration (`from pgvector.sqlalchemy import Vector`) which handles native binary serialization. This is more efficient and type-safe.

---

### [LOW] POOL CONFIG: `pool_size=20, max_overflow=10` may be undersized for high concurrency

**File**: `src/core/database.py:39`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
engine = create_async_engine(
    settings.database_url or "",
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)
```
**Description**: The connection pool allows up to 30 simultaneous PostgreSQL connections (20 pool + 10 overflow). For a single-process deployment this is reasonable. However, each of the 6 sequential queries in the dashboard endpoint holds a connection for the duration of all 6 queries. Under 30 concurrent dashboard requests, the pool is exhausted and subsequent requests queue. With multiple workers (uvicorn `--workers N`), each worker has its own pool of 30, potentially creating 120+ connections with 4 workers.
**Risk**: LOW. The `pool_pre_ping` and `pool_recycle=300` are correctly configured. Risk materializes only at high concurrency with the unbounded queries noted above.
**Recommendation**: Reduce per-worker pool size when running multiple workers (e.g., `pool_size=5, max_overflow=5` per worker with PgBouncer in front). Alternatively, use a single shared pool via `pgbouncer` in transaction mode.

---

### [LOW] COMPUTE: `cosine_similarity` uses pure Python loops — no numpy acceleration

**File**: `src/semantic/embeddings.py:206`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
```
**Description**: The `cosine_similarity` utility function computes dot products using Python generator expressions over lists. For 768-dimensional vectors, this is ~2300 floating-point operations in pure Python. `numpy` is already a dependency (`import numpy as np` appears in `rag/embeddings.py`).
**Risk**: LOW. This function appears to be a utility and may not be on the hot path. If called frequently (e.g., in batch similarity computations), the difference between Python loops and numpy operations is 10-100x.
**Recommendation**: Replace with `np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))` using numpy arrays. Accept `list[float]` as input and convert with `np.array()`.

---

## Performance Risk Score

**Overall Risk: HIGH**

The most critical issues are:
1. The N+1 query in `batch_validate` is a correctness-class performance bug — it will cause request timeouts at realistic batch sizes.
2. The unbounded subgraph and list queries are time bombs that degrade linearly as engagement data accumulates.
3. Sequential Neo4j node creation during graph build will become the dominant bottleneck as evidence volumes grow.

The database pool configuration is sound. Async patterns in route handlers are generally correct (no `time.sleep` in async context, proper `asyncio.to_thread` for blocking calls). The main risks are query efficiency and missing caching on high-read, low-write endpoints.

