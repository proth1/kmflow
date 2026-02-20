# B3: API Compliance Audit Findings

**Agent**: B3 (API Compliance Auditor)
**Date**: 2026-02-20
**Scope**: REST standards, response format consistency, pagination, error handling, rate limiting, API versioning

## Summary

- **Total Endpoints Audited**: ~188 route handlers across 26 route files
- **Critical Issues**: 1
- **High Issues**: 6
- **Medium Issues**: 5
- **Low Issues**: 3

### Endpoint Count by HTTP Method (approximate from grep count)
- GET: ~85
- POST: ~65
- PATCH: ~20
- DELETE: ~12
- PUT: ~6
- Total: ~188

### Authentication Status
- All non-health endpoints use `require_permission()` or `get_current_user()` dependency injection
- `/health` endpoint is unauthenticated (intentional — public health check)
- Auth endpoints (`/api/v1/auth/token`, `/api/v1/auth/refresh`) are partially rate-limited via `slowapi` limiter, but this limiter is NOT integrated with the app-level `RateLimitMiddleware`

---

## Findings

### [CRITICAL] RATE LIMITING: Dual Rate Limiter Conflict — `slowapi` Limiter Not Registered

**File**: `src/api/routes/auth.py:40-41`, `src/api/main.py:172-176`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# auth.py:40-41
limiter = Limiter(key_func=get_remote_address)

@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def get_token(request: Request, ...):
```
```python
# main.py:172-176
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
```
**Description**: The `auth.py` module creates a `slowapi.Limiter` instance and decorates `get_token` and `refresh_token` with per-endpoint rate limits (`5/minute`, `10/minute`). However, the `slowapi` state object is **never added to the FastAPI app** (`app.state.limiter = limiter` is absent), and no `SlowAPIMiddleware` or `slowapi` exception handler is registered in `main.py`. The `@limiter.limit()` decorators will silently fail — they will not raise 429 responses. Authentication endpoints are therefore rate-limited only by the generic IP-based `RateLimitMiddleware` (default: `rate_limit_requests` per window), not by the intended 5/minute brute-force protection.
**Risk**: Authentication endpoints lack their intended rate limiting, enabling brute-force credential attacks at the full global rate limit instead of the intended 5 requests/minute.
**Recommendation**: Either (a) register the `slowapi` state and middleware in `main.py`:
```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
```
Or (b) remove the non-functional `slowapi` decorators and implement auth-specific rate limiting inside the route handlers using Redis.

---

### [HIGH] PAGINATION: Multiple List Endpoints Missing Upper Bound on `limit` Parameter

**File**: Multiple route files
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# monitoring.py:251-256 — no upper bound on limit
async def list_monitoring_jobs(
    engagement_id: UUID | None = None,
    status_filter: MonitoringStatus | None = None,
    ...
) -> dict[str, Any]:
    # No limit/offset parameter at all — unbounded query!
    result = await session.execute(query)
    items = [_job_to_response(j) for j in result.scalars().all()]
    return {"items": items, "total": len(items)}

# simulations.py:289-303 — no limit, no pagination
async def list_scenarios(...) -> dict[str, Any]:
    result = await session.execute(query)
    items = [_scenario_to_response(s) for s in result.scalars().all()]
    return {"items": items, "total": len(items)}
```
**Description**: The following list endpoints accept pagination parameters but impose no upper bound on the `limit` value, or have no pagination at all:
- `GET /api/v1/monitoring/jobs` — no limit/offset parameters, unbounded `scalars().all()`
- `GET /api/v1/monitoring/baselines` — no limit/offset, unbounded query
- `GET /api/v1/simulations/scenarios` — no limit/offset, unbounded query
- `GET /api/v1/simulations/results` — no limit/offset, unbounded query
- `GET /api/v1/simulations/scenarios/{id}/modifications` — no limit/offset
- `GET /api/v1/simulations/scenarios/{id}/suggestions` — no limit/offset
- `GET /api/v1/simulations/scenarios/{id}/financial-assumptions` — no limit/offset
- `GET /api/v1/integrations/connections` — no limit/offset, unbounded query
- `GET /api/v1/conformance/reference-models` — no limit/offset, unbounded query
- `GET /api/v1/conformance/results` — no limit/offset, unbounded query
- `GET /api/v1/engagements/{id}/audit-logs` — no limit/offset, unbounded query
- `GET /api/v1/evidence/{id}/fragments` — no limit/offset, unbounded query

Additionally, those endpoints that do have a `limit` parameter (e.g., governance catalog `limit=100`, metrics readings `limit=100`) impose no upper ceiling — a caller can pass `limit=1000000`.
**Risk**: An authenticated user can trigger full-table scans returning all records, causing memory exhaustion and denial-of-service for other users.
**Recommendation**: Add `Query(default=20, ge=1, le=100)` (or `le=200` for high-volume endpoints) to all list endpoints. Use `FastAPI.Query` constraints rather than bare `int` parameters.

---

### [HIGH] PAGINATION: `list_patterns` and `search_patterns` Report Incorrect `total` Count

**File**: `src/api/routes/patterns.py:146-165`, `src/api/routes/patterns.py:224-240`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# patterns.py:159-165
query = query.offset(offset).limit(limit)
result = await session.execute(query)
items = [_pattern_to_response(p) for p in result.scalars().all()]
return {"items": items, "total": len(items)}  # BUG: total = page size, not dataset size

# patterns.py:237-240
result = await session.execute(query)
items = [_pattern_to_response(p) for p in result.scalars().all()]
return {"items": items, "total": len(items)}  # BUG: same issue
```
**Description**: `list_patterns` applies `offset(offset).limit(limit)` to the query, then returns `"total": len(items)` — which is the count of the current page (at most `limit` items), not the actual total record count. This makes pagination impossible for clients: they cannot determine how many pages exist. The same bug is present in `search_patterns`. At least 8 other list endpoints across `monitoring.py` and `simulations.py` share this bug (those without separate count queries).
**Risk**: API clients cannot implement correct pagination. They will either under-paginate (missing records) or enter infinite polling loops.
**Recommendation**: Add a separate count query before applying pagination, following the pattern already used in `engagements.py:188-209`:
```python
count_result = await session.execute(select(func.count()).select_from(PatternLibraryEntry))
total = count_result.scalar() or 0
```

---

### [HIGH] HTTP SEMANTICS: DELETE Endpoints Return Incorrect Status Codes or Response Bodies

**File**: `src/api/routes/engagements.py:265-284`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# engagements.py:265
@router.delete("/{engagement_id}", response_model=EngagementResponse)
async def archive_engagement(
    engagement_id: UUID,
    ...
) -> Engagement:
    """Soft-delete an engagement by setting its status to ARCHIVED."""
    engagement.status = EngagementStatus.ARCHIVED
    ...
    return engagement  # Returns 200 with body, not 204
```
**Description**: The `DELETE /api/v1/engagements/{id}` endpoint performs a soft-delete (status change to ARCHIVED) but returns the full engagement object with HTTP 200, not HTTP 204 No Content. While soft-delete may justify returning a body, the semantics are confusing: a `DELETE` endpoint that returns the archived resource body is non-standard. Additionally, the operation is not idempotent as specified by REST — calling DELETE twice on an already-archived engagement silently re-archives it. Other DELETEs correctly use 204 (`patterns.py:209`, `users.py:272`, `integrations.py:215`).
**Risk**: API clients expecting standard REST DELETE semantics (204 No Content) will be confused. The non-idempotent soft-delete may cause duplicate audit log entries.
**Recommendation**: Either (a) change the endpoint to `PATCH /{id}/archive` with a 200 response, or (b) keep DELETE but use 204 and skip the response body, adding idempotency checks.

---

### [HIGH] API VERSIONING: `health` Endpoint Not Versioned Under `/api/v1/`

**File**: `src/api/routes/health.py:18`, `src/api/main.py:179`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# health.py:18
@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
```
```python
# health.py:14
router = APIRouter()  # No prefix!
```
**Description**: The health endpoint is served at `/health` (no `APIRouter` prefix), while all other endpoints are versioned under `/api/v1/`. This inconsistency means the health endpoint is outside the versioned namespace. If a future v2 API is deployed behind a different path, the health check will not be automatically co-versioned. Additionally, the response body contains `"version": "0.1.0"` hardcoded as a string literal rather than referencing the `API_VERSION` constant.
**Risk**: Low operational risk currently, but creates a versioning inconsistency that complicates future API versioning strategy. The hardcoded version string in the response will drift from the actual `API_VERSION`.
**Recommendation**: Move health endpoint to `/api/v1/health` by adding `prefix="/api/v1"` to the health router, and replace `"version": "0.1.0"` with `API_VERSION` from `src.api.version`.

---

### [HIGH] TOM ROUTES: Write Operations Use Insufficient Permission (`engagement:read`)

**File**: `src/api/routes/tom.py:192-211`, `src/api/routes/tom.py:276-304`, `src/api/routes/tom.py:355-373`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# tom.py:192-197
@router.post("/models", response_model=TOMResponse, status_code=status.HTTP_201_CREATED)
async def create_tom(
    payload: TOMCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),  # Should be engagement:update or tom:create
) -> TargetOperatingModel:
```
**Description**: All TOM, gap, best practice, benchmark, and roadmap write endpoints (POST/PATCH) use `require_permission("engagement:read")` — a read-only permission — as their access control gate. This includes data-mutating operations: creating TOMs, creating gap analysis results, updating regulations, seeding best practices/benchmarks, running alignment analysis, generating roadmaps, and creating metrics/readings. The same issue appears in `metrics.py`, `annotations.py`, `regulatory.py`, and `conformance.py` for their write operations.
**Risk**: Any user with `engagement:read` permission can mutate TOM data, gap analysis results, metrics, and regulatory controls. This bypasses the RBAC permission model.
**Recommendation**: Replace `require_permission("engagement:read")` with appropriate write permissions (`engagement:update`, `tom:write`, `gap:write`, etc.) on all mutating endpoints.

---

### [HIGH] RESPONSE FORMAT: `governance.py` `/catalog` List Missing `total` Wrapper

**File**: `src/api/routes/governance.py:146-164`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# governance.py:146-164
@router.get("/catalog", response_model=list[CatalogEntryResponse])  # Returns raw list, not paginated wrapper
async def list_catalog_entries(...) -> list[DataCatalogEntry]:
    svc = DataCatalogService(session)
    return await svc.list_entries(limit=limit, offset=offset)
    # Returns: [entry1, entry2, ...]
    # Other endpoints return: {"items": [...], "total": N}
```
**Description**: The `GET /api/v1/governance/catalog` endpoint returns a raw `list[DataCatalogEntry]` while almost every other list endpoint in the codebase returns a wrapper object `{"items": [...], "total": N}`. This inconsistency in response format breaks the API contract: clients cannot determine total count or implement proper pagination for catalog entries. The endpoint accepts `limit` and `offset` parameters but the response does not expose the total count.
**Risk**: API consumers have no way to determine total catalog entry count for pagination. Inconsistent response format increases client-side complexity.
**Recommendation**: Change response model to a wrapper schema (`CatalogEntryList` with `items` and `total` fields) matching all other list endpoints.

---

### [MEDIUM] ERROR HANDLING: `graph.py` Cypher Query Endpoint Leaks Internal Error Messages

**File**: `src/api/routes/graph.py:208-215`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# graph.py:208-215
try:
    results = await graph_service._run_query(payload.query, payload.parameters)
    return results
except Exception as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Query execution failed: {e}",  # Leaks Neo4j internals
    ) from e
```
**Description**: The Cypher query endpoint (`POST /api/v1/graph/query`) catches all exceptions and includes the raw exception message in the `detail` field returned to the client. Neo4j exceptions can expose internal database structure, node labels, property names, and schema information. The same pattern exists in `graph.py:179-184` (graph build endpoint). While the error is logged correctly via `logger.exception`, the client-facing detail should be sanitized.
**Risk**: Internal Neo4j error messages, schema details, or query structure may be exposed to authenticated clients.
**Recommendation**: Log the full exception for debugging, but return a sanitized message to the client: `detail="Query execution failed. Check server logs for details."`.

---

### [MEDIUM] HTTP SEMANTICS: `POST /api/v1/graph/build` Returns 202 but Executes Synchronously

**File**: `src/api/routes/graph.py:144-145`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# graph.py:144-145
@router.post("/build", response_model=BuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def build_graph(...) -> dict[str, Any]:
    """Trigger knowledge graph construction for an engagement.
    ...
    """
    result = await builder.build_knowledge_graph(...)  # Executes synchronously, blocks response
    return {...}  # Returns result immediately with 202
```
**Description**: The `/build` endpoint returns `HTTP 202 Accepted` (the standard code for "I have received your request and will process it asynchronously"), but actually executes the graph build synchronously and blocks until complete before returning. A 202 response conventionally implies the response body will contain a job ID or polling URL for checking status. This misleads clients into thinking the operation is asynchronous when it is not. The POV generation endpoint (`pov.py:244`) handles this correctly with a job ID pattern.
**Risk**: Clients may implement polling/retry logic expecting async behavior, then time out or fail when the 202 response returns an immediate result.
**Recommendation**: Either (a) change status code to 200 if remaining synchronous, or (b) implement actual async execution with a job ID and polling endpoint, following the pattern in `pov.py`.

---

### [MEDIUM] RATE LIMITING: In-Memory Rate Limiter Not Shared Across Workers

**File**: `src/api/routes/simulations.py:49-80`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# simulations.py:49-57
# In-memory rate limiter for LLM endpoints (per-user, 5 requests/minute).
# NOTE: This is per-process only. In multi-worker deployments (uvicorn --workers N),
# the effective limit becomes N * _LLM_RATE_LIMIT. For production multi-worker
# deployments, replace with Redis-based rate limiting.
_LLM_RATE_LIMIT = 5
_LLM_RATE_WINDOW = 60  # seconds
_llm_request_log: dict[str, list[float]] = defaultdict(list)
```
**Description**: The LLM rate limiter in `simulations.py` uses a module-level `defaultdict` to track per-user request counts. This state is not shared across uvicorn workers. The code includes a comment acknowledging this limitation. The general `RateLimitMiddleware` in `security.py:95` has the same flaw — it uses `defaultdict(_RateLimitEntry)` in memory per process.
**Risk**: With multiple workers (e.g., `uvicorn --workers 4`), a user can make `4 * N` requests before hitting any rate limit. The LLM endpoints with rate limit `5/min` would effectively allow 20 requests/min in a 4-worker deployment.
**Recommendation**: Replace both in-memory rate limiters with Redis-backed rate limiting using atomic increment operations (e.g., using Redis `INCR` + `EXPIRE` pattern or the `limits` library with Redis storage).

---

### [MEDIUM] MISSING PAGINATION: `engagements/{id}/audit-logs` Returns Unbounded Results

**File**: `src/api/routes/engagements.py:332-345`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# engagements.py:332-345
@router.get("/{engagement_id}/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    engagement_id: UUID,
    ...
) -> list[AuditLog]:
    """Get audit log entries for an engagement."""
    result = await session.execute(
        select(AuditLog).where(AuditLog.engagement_id == engagement_id)
        .order_by(AuditLog.created_at.desc())
        # No .limit() or .offset() applied!
    )
    return list(result.scalars().all())
```
**Description**: The audit logs endpoint returns all audit log records for an engagement without any pagination. High-activity engagements will accumulate large audit logs over time. The response model is `list[AuditLogResponse]` (a raw list, not a paginated wrapper), making it impossible to add pagination without a breaking API change later.
**Risk**: For engagements with many operations, this can return thousands of records, causing memory pressure and slow responses.
**Recommendation**: Add `limit: int = Query(default=50, ge=1, le=500)` and `offset: int = Query(default=0, ge=0)` parameters, and update the response model to a wrapper.

---

### [LOW] NAMING CONVENTION: `status_filter` Parameter Inconsistently Named Across Routes

**File**: `src/api/routes/engagements.py:172`, `src/api/routes/monitoring.py:252`, `src/api/routes/monitoring.py:480`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# engagements.py:172
async def list_engagements(
    status_filter: EngagementStatus | None = None,  # "status_filter"

# monitoring.py:253
async def list_monitoring_jobs(
    status_filter: MonitoringStatus | None = None,  # "status_filter"

# evidence.py:251
async def list_evidence(
    validation_status: ValidationStatus | None = None,  # just "validation_status"
```
**Description**: Filter parameters for status fields are inconsistently named: some use `status_filter` (engagements, monitoring jobs) while others use the plain field name (`validation_status` in evidence, `status` in monitoring alerts). This creates an inconsistent query parameter API for clients.
**Risk**: Low — clients can discover the parameters, but inconsistency increases integration effort.
**Recommendation**: Standardize on a single naming convention. The existing `status` parameter name used in alerts is more conventional for REST APIs.

---

### [LOW] MISSING RESPONSE MODEL: Several TOM Endpoints Return Untyped `dict`

**File**: `src/api/routes/tom.py:524-553`, `src/api/routes/tom.py:556-578`, `src/api/routes/tom.py:615-643`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# tom.py:524
@router.post("/alignment/{engagement_id}/{tom_id}")  # No response_model
async def run_alignment(...) -> dict[str, Any]:

# tom.py:556
@router.get("/alignment/{engagement_id}/maturity")  # No response_model
async def get_maturity_scores(...) -> dict[str, Any]:

# tom.py:615
@router.post("/conformance/check")  # No response_model
async def check_conformance(...) -> dict[str, Any]:
```
**Description**: Multiple TOM routes (`run_alignment`, `get_maturity_scores`, `prioritize_gaps`, `check_conformance`, `get_conformance_summary`, `generate_roadmap`, `get_roadmap_summary`) and regulatory routes (`build_governance_overlay`, `get_compliance_state`, `get_ungoverned_processes`) have no `response_model` annotation. This means FastAPI cannot validate or serialize the response, OpenAPI docs will show no response schema, and clients receive undocumented JSON.
**Risk**: No server-side response validation means bugs in response serialization go undetected. OpenAPI documentation is incomplete, increasing integration friction.
**Recommendation**: Define Pydantic response models for all these endpoints and add `response_model=...` to the router decorators.

---

### [LOW] CAMUNDA ROUTES: Inconsistent with Main API Patterns

**File**: `src/api/routes/camunda.py`
**Agent**: B3 (API Compliance Auditor)
**Evidence**: Based on grep count showing 6 route handlers in `camunda.py`. Not read in detail but noted as a potential gap area — Camunda routes are Phase 3 additions that may not follow the same patterns as Phase 1-2 routes.
**Risk**: Low — requires targeted review.
**Recommendation**: Verify that Camunda routes follow the same authentication, response format, and pagination conventions established in this audit.

---

## Positive Highlights

1. **Consistent 201 for creation**: All POST endpoints creating resources correctly use `status_code=status.HTTP_201_CREATED`.
2. **Consistent 204 for deletion**: Most DELETE endpoints correctly return HTTP 204 No Content with no response body (`patterns.py`, `users.py`, `integrations.py`, `annotations.py`, `simulations.py`).
3. **Structured error responses**: `main.py` registers global error handlers for `ValueError` (422) and `Exception` (500) that include `request_id` for traceability — a good practice.
4. **Security headers**: `SecurityHeadersMiddleware` adds `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Cache-Control`, and `X-API-Version` to all responses.
5. **Rate limiting headers**: `RateLimitMiddleware` correctly returns `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `Retry-After` headers.
6. **Consistent `/api/v1/` prefix**: All routes except `/health` use the versioned prefix correctly.
7. **Request ID tracing**: `RequestIDMiddleware` propagates `X-Request-ID` through all requests for distributed tracing.
8. **Input validation**: Most endpoints use Pydantic models with `Field` constraints (`min_length`, `max_length`, `ge`, `le`) for request validation.
9. **Paginated responses**: Core CRUD endpoints (engagements, evidence, users, TOM models, regulatory) implement proper `{items, total}` pagination wrappers with separate count queries.
10. **LLM rate limiting documented**: The `simulations.py` LLM rate limiter correctly documents its multi-worker limitation in both code comments and docstrings.

