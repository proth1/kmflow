# B3: API Compliance Audit Findings (Re-Audit — 2026-03-19)

**Agent**: B3 (API Compliance Auditor)
**Date**: 2026-03-19
**Scope**: REST standards, response format consistency, pagination, error handling, rate limiting, API versioning
**Supersedes**: Previous B3 audit dated 2026-02-26 (26 files, ~210 handlers)

---

## Summary

- **Total Route Files Audited**: 76 files in `src/api/routes/`
- **Total Endpoint Handlers**: ~456 route handlers
- **Critical Issues**: 2
- **High Issues**: 5
- **Medium Issues**: 6
- **Low Issues**: 5

Previous HIGH/MEDIUM items carried forward where not yet resolved are re-listed. New items found in the expanded route surface are marked **(new)**.

---

## Critical Issues

### [CRITICAL] RATE LIMITING: In-Memory Rate Limiter Ineffective in Multi-Worker Deployments

**File**: `src/api/middleware/security.py:95`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP rate limiter.

    Note: This is per-process only.  In multi-worker deployments the
    effective limit is ``workers * max_requests``.  For production
    multi-worker deployments, replace with Redis-backed rate limiting.
    """
```
**Description**: `RateLimitMiddleware` stores all rate limit state in a Python `defaultdict` in process memory. In any multi-worker uvicorn deployment (`--workers N`), each worker maintains independent state, multiplying the effective limit by N workers. The `slowapi` limiter used on auth routes shares the same structural weakness — it is registered per-process in `auth.py` and not backed by a shared store. The `_check_llm_rate_limit` function in `simulations.py:84` also uses a module-level dict for LLM rate limiting and has the identical flaw.

**Risk**: An attacker on N uvicorn workers can send N times the advertised rate limit before any enforcement fires. For `/auth/login` at 5 requests/minute, this becomes N×5 in production. Brute-force protection and LLM cost controls are both negated in multi-worker deployments.

**Recommendation**: Replace all three in-memory rate limit stores with Redis-backed atomic counters using `INCR` + `EXPIRE` (fixed window) or a sorted-set sliding window. The `redis_client` is already available on `app.state` at startup.

---

### [CRITICAL] TODO IN ROUTE DOCSTRING: `generate_gap_probes` Documents Incomplete Persistence

**File**: `src/api/routes/gap_probes.py:82`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
    """Generate gap-targeted probes for an engagement.

    TODO: Persist generated probes to database for stable IDs and
    referenceability by survey bot. Currently recomputes on every call.
    See follow-up issue for persistence model.
    """
```
**Description**: A `TODO` comment in a route docstring documents that probe generation is a stateless recompute — no records are persisted, no stable IDs are assigned. The route returns `{"probes_generated": N, "message": "..."}` without returning any probe data. The survey bot integration the docstring references cannot function without stable IDs. This is an incomplete stub masquerading as a functional endpoint.

**Risk**: The endpoint returns HTTP 201 Created but creates nothing in the database. Callers expecting a resource with a stable ID receive none. Downstream survey bot integration is silently broken.

**Recommendation**: Either persist probes and return stable IDs before shipping this endpoint, or change the status code to 200 OK, return the generated probe objects in the response body, and document that results are ephemeral until persistence is implemented.

---

## High Issues

### [HIGH] PAGINATION: `list_engagement_members` Has No Pagination (Carried Forward)

**File**: `src/api/routes/users.py:350`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.get("/api/v1/engagements/{engagement_id}/members", response_model=list[MemberResponse])
async def list_engagement_members(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _engagement_user: User = Depends(require_engagement_access),
) -> list[EngagementMember]:
    result = await session.execute(select(EngagementMember).where(...))
    return list(result.scalars().all())
```
**Description**: This list endpoint returns all members with no `limit`, `offset`, or total count. It is the only list endpoint in 76 route files without pagination. The response wraps a plain list directly — no `{items, total}` envelope consistent with the platform standard.

**Risk**: Unbounded database query; no total count for client-side pagination; inconsistent API contract vs. all other list endpoints.

**Recommendation**: Add `limit: int = Query(default=50, ge=1, le=200)` and `offset: int = Query(default=0, ge=0)`, return `{"items": [...], "total": N}`, and change `response_model` to a `MemberListResponse` schema.

---

### [HIGH] PAGINATION: Unbounded Queries in `list_role_rates` and `list_volume_forecasts`  **(new)**

**File**: `src/api/routes/cost_modeling.py:129`, `src/api/routes/cost_modeling.py:174`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.get("/engagements/{engagement_id}/role-rates")
async def list_role_rates(engagement_id: UUID, ...) -> dict[str, Any]:
    result = await session.execute(
        select(RoleRateAssumption).where(...).order_by(RoleRateAssumption.role_name)
    )
    items = list(result.scalars().all())
    return {"items": [_rate_to_dict(r) for r in items], "total": len(items)}
```
**Description**: Both `list_role_rates` and `list_volume_forecasts` issue unbounded `SELECT *` queries with no `.limit()` clause. They also use `len(items)` as the total count (counting the already-fetched rows) instead of issuing a `COUNT(*)` query — which means the "total" returned is always equal to the page size, rendering client-side pagination impossible if bounds are later added.

**Risk**: Memory exhaustion on engagements with large numbers of role rates or volume forecasts; denial-of-service vector for authenticated users; non-functional total count if pagination is ever added.

**Recommendation**: Add `limit: int = Query(default=50, ge=1, le=200)` and `offset: int = Query(default=0, ge=0)` parameters; apply `.limit(limit).offset(offset)` in the query; issue a separate `COUNT(*)` query for `total`.

---

### [HIGH] PAGINATION: `list_engagement_members` Pattern Repeated in `list_survey_sessions` and `list_volume_forecasts` **(new)**

**File**: `src/api/routes/cost_modeling.py:174`, `src/api/routes/cost_modeling.py:129`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.get("/engagements/{engagement_id}/volume-forecasts")
async def list_volume_forecasts(...) -> dict[str, Any]:
    result = await session.execute(
        select(VolumeForecast).where(VolumeForecast.engagement_id == engagement_id).order_by(VolumeForecast.name)
    )
    items = list(result.scalars().all())
    return {"items": [_forecast_to_dict(f) for f in items], "total": len(items)}
```
**Description**: See description above in HIGH pagination finding. Included as a separate entry because the `total: len(items)` pattern is a secondary defect — it does not count all rows in the table, it counts only the rows returned in this fetch. This would produce incorrect totals if `.limit()` were added later without also adding a `COUNT(*)` query.

**Risk**: Incorrect `total` field misleads clients about dataset size; will silently break pagination if bounds are added without a corresponding count query.

**Recommendation**: Always use a separate `SELECT COUNT(*) FROM ...` query with the same WHERE clause to populate `total`, never `len(items)`.

---

### [HIGH] RESPONSE FORMAT: Multiple Camunda/Orchestration Endpoints Use Hardcoded `502` Integer **(new)**

**File**: `src/api/routes/camunda.py:50`, `src/api/routes/orchestration.py:202`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.delete("/instances/{instance_id}")
async def cancel_process_instance(instance_id: str, ...) -> dict[str, Any]:
    try:
        await client.delete_process_instance(instance_id)
        return {"instance_id": instance_id, "status": "cancelled"}
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail="Failed to communicate...") from e
```
**Description**: Ten occurrences across `camunda.py` and `orchestration.py` use bare integer `502` instead of `status.HTTP_502_BAD_GATEWAY`. This is a style inconsistency with the entire rest of the codebase which uses `status.HTTP_*` constants. Additionally, `orchestration.py:202` `cancel_process_instance` lacks `status_code` on the route decorator (defaults to 200 for a DELETE that should be 204 or 200 with body), making the semantics ambiguous.

**Risk**: Style inconsistency makes audits harder; `DELETE` without explicit status code is ambiguous — response includes a body (`{"status": "cancelled"}`), which conflicts with 204 No Content semantics.

**Recommendation**: Replace bare `502` integers with `status.HTTP_502_BAD_GATEWAY`. Decide whether `cancel_process_instance` returns 200 with body or 204 with no body and declare it explicitly.

---

### [HIGH] RESPONSE FORMAT: Route Return Type Annotation `-> Any` on 33 Endpoints **(new)**

**File**: Multiple — `transfer_controls.py:130`, `incidents.py:109`, `reports.py:310`, `pdp.py:102`, and 29 others
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# transfer_controls.py:130
async def evaluate_transfer(...) -> Any:
    service = TransferControlService(session)
    result = await service.evaluate_transfer(...)
    return result

# incidents.py:109 (has response_model but return type is Any)
async def create_incident(...) -> Any:
```
**Description**: 33 route handlers across 13 files use `-> Any` as the return type annotation. While FastAPI uses `response_model` for runtime serialization rather than the return type annotation, `-> Any` provides no static-analysis benefit, bypasses mypy checking, and signals that the response contract is undefined. Many of these endpoints do have `response_model` declared, making the `-> Any` annotation merely lazy — but files like `transfer_controls.py` have both `-> Any` return type and no `response_model` on some routes.

**Risk**: `-> Any` return type defeats mypy static analysis; combined with missing `response_model`, routes have no validated response contract at any layer.

**Recommendation**: Replace `-> Any` with the actual return type — either the Pydantic model type (for routes with `response_model`) or `dict[str, Any]` for routes that manually construct dicts. At minimum use `dict[str, Any]` rather than `Any`.

---

## Medium Issues

### [MEDIUM] RATE LIMITING: Auth Endpoints Not Account-Level Rate Limited (Carried Forward)

**File**: `src/api/routes/auth.py:116`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def get_token(request: Request, payload: TokenRequest, ...) -> dict[str, Any]:
```
**Description**: The `slowapi` limiter on `/token`, `/login`, and `/refresh/cookie` limits by remote IP address only. Distributed credential stuffing attacks from multiple IPs bypass this entirely. There is no per-account failed-attempt counter. Combined with the multi-worker rate-limit bypass (CRITICAL finding), brute-force protection is not effective in production.

**Risk**: Distributed credential stuffing via multiple source IPs evades all current rate limit controls.

**Recommendation**: Add per-account failed-attempt tracking in Redis with exponential backoff or a temporary lockout after N consecutive failures per email address.

---

### [MEDIUM] HTTP SEMANTICS: `GET /api/v1/governance/policies` Exposes Filesystem Path and Lacks Response Model (Carried Forward)

**File**: `src/api/routes/governance.py:330`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.get("/policies")
async def list_policies(user: User = Depends(require_permission("governance:read"))) -> dict[str, Any]:
    engine = PolicyEngine()
    return {
        "policy_file": str(engine.policy_file),
        "policies": engine.policies,
    }
```
**Description**: No `response_model` declared. The `policy_file` key returns the full server-side filesystem path of the YAML policy file. This is a server-side information disclosure — clients receive the absolute path (e.g., `/app/src/core/policies/governance.yaml`), which reveals deployment directory structure.

**Risk**: Information disclosure of server filesystem path; no OpenAPI schema generated; policy structure changes silently break clients.

**Recommendation**: Define a `GovernancePoliciesResponse` model. Remove `policy_file` from the response or replace it with a sanitized name/version string.

---

### [MEDIUM] RESPONSE FORMAT: Several High-Value TOM Endpoints Lack `response_model` (Carried Forward)

**File**: `src/api/routes/tom.py:533` and related
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.post("/alignment/{engagement_id}/{tom_id}")
async def run_alignment(...) -> dict[str, Any]:
    ...

@router.get("/alignment/{engagement_id}/maturity")
async def get_maturity_scores(...) -> dict[str, Any]:
```
**Description**: Five TOM endpoints — alignment, maturity scores, prioritized gaps, conformance check, and roadmap generation — return `dict[str, Any]` without `response_model` declarations. These are business-critical endpoints directly consumed by client dashboards and report generation.

**Risk**: No OpenAPI schema; response drift undetectable at startup; client contracts undocumented.

**Recommendation**: Define Pydantic response models: `AlignmentResponse`, `MaturityResponse`, `PrioritizedGapsResponse`, `RoadmapResponse`, `RoadmapSummaryResponse`.

---

### [MEDIUM] RESPONSE FORMAT: `GET /api/v1/governance/export/{engagement_id}` Has No `response_model` **(new)**

**File**: `src/api/routes/governance.py:389`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.get("/export/{engagement_id}")
async def export_governance(engagement_id: uuid.UUID, ...) -> Response:
    pkg_bytes = await export_governance_package(session, engagement_id)
    filename = f"governance_{engagement_id}.zip"
    return Response(content=pkg_bytes, media_type="application/zip", ...)
```
**Description**: The governance export endpoint returns a raw `fastapi.Response` (a binary ZIP) with no `response_model`. This is correct for binary responses — Pydantic cannot model a ZIP file. However, there is no explicit `status_code` on the route decorator, no `responses` dict documenting the content type in OpenAPI, and no error response for the case where `export_governance_package` raises an exception (no try/except).

**Risk**: OpenAPI docs show no response type for this endpoint; an exception from `export_governance_package` results in an unhandled 500 with no context; clients have no documented error response shapes.

**Recommendation**: Add `responses={200: {"content": {"application/zip": {}}, "description": "Governance package ZIP"}}` to the route decorator. Wrap the service call in try/except and raise an appropriate `HTTPException` on failure.

---

### [MEDIUM] PAGINATION: Inconsistent `limit` Ceiling Across the API **(new)**

**File**: Multiple
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# event_spine.py:101
limit: int = Query(200, ge=1, le=2000, ...)

# governance.py:880
limit: int = Query(50, ge=1, le=500, ...)

# correlation.py:135
limit: int = Query(100, ge=1, le=1000, ...)

# engagements.py:166
limit: int = Query(default=20, ge=1, le=100)
```
**Description**: Across the 76 route files, the maximum `limit` ceiling (`le=`) varies from 100 to 2000 with no documented rationale for the variation. The project standard from the coding standards guide is `le=200`, but `event_spine.py` allows `le=2000` (10x the standard), `governance.py` allows `le=500`, and `correlation.py` allows `le=1000`. There is no pagination policy document.

**Risk**: Allows much larger result sets than intended in some routes; inconsistent client experience; potential memory pressure on large limit values like `le=2000`.

**Recommendation**: Establish a platform-wide default maximum of `le=200`. Special cases (e.g., `event_spine`) should be explicitly documented with a rationale comment if they require higher limits.

---

### [MEDIUM] HTTP SEMANTICS: `seed_lists.py` DELETE Returns HTTP 200 Instead of 204 **(new)**

**File**: `src/api/routes/seed_lists.py:161`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.delete(
    "/engagements/{engagement_id}/seed-terms/{term_id}",
    status_code=status.HTTP_200_OK,
)
async def deprecate_seed_term(...) -> dict[str, Any]:
    """Deprecate a seed term (soft delete)."""
    service = SeedListService(session)
    result = await service.deprecate_term(term_id)
    ...
    return result
```
**Description**: The seed term "delete" endpoint is a soft delete (deprecation), which returns a body describing the updated state — making HTTP 200 with body technically correct for a soft delete. However, all other 13 DELETE endpoints in the codebase use `HTTP_204_NO_CONTENT`, making this the sole exception. The inconsistency is confusing to API consumers who expect DELETE to return 204.

**Risk**: Inconsistent with the platform DELETE convention used across all other 13 DELETE routes; API consumers may handle errors incorrectly if they assume 204 for all DELETEs.

**Recommendation**: Either rename the route to `PATCH .../deprecate` (which returns a modified resource at 200) or use `HTTP_204_NO_CONTENT` and return no body. A soft delete returning a body is better modeled as a state-transition PATCH.

---

## Low Issues

### [LOW] VERSIONING: `users.py`, `gdpr.py`, `health.py` Inline Full Paths (Carried Forward)

**File**: `src/api/routes/users.py:31`, `src/api/routes/health.py:20`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# users.py:31
router = APIRouter(tags=["users"])

# health.py:20
router = APIRouter(tags=["health"])

# users.py:98 (path hardcoded in decorator)
@router.post("/api/v1/users", response_model=UserResponse, ...)
```
**Description**: Three of 76 route files create routers without a `prefix` and hardcode `/api/v1/...` into every individual route decorator. The other 73 files use `router = APIRouter(prefix="/api/v1/...", tags=[...])`. This divergence makes API version bumps require individual path updates in these files rather than a single prefix change.

**Risk**: Harder to maintain; diverges from the established pattern; error-prone when paths need updating.

**Recommendation**: Refactor to use `APIRouter(prefix="/api/v1/users", tags=["users"])` etc. and simplify all path strings to relative paths.

---

### [LOW] HTTP SEMANTICS: `GET /api/v1/graph/traverse/{node_id}` Validates `depth` Manually (Carried Forward)

**File**: `src/api/routes/graph.py:180`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
async def traverse_graph(
    node_id: str,
    depth: int = 2,          # No Query bounds declared
    ...
) -> list[dict[str, Any]]:
    if depth < 1 or depth > 5:    # Manual validation duplicates what Query(ge=1, le=5) would do
        raise HTTPException(...)
```
**Description**: `depth` is declared as a plain `int = 2` with no `Query(ge=1, le=5)` bounds, then manually validated inside the handler. FastAPI will not document the bounds in OpenAPI. The same pattern exists for `top_k` in `semantic_search` at line 238.

**Risk**: OpenAPI docs do not show valid bounds; manual validation duplicates what Query validation handles automatically.

**Recommendation**: Change to `depth: int = Query(default=2, ge=1, le=5)` and remove the manual `if` check. Apply the same fix to `top_k` in `semantic_search`.

---

### [LOW] HTTP SEMANTICS: `POST /api/v1/tom/seed` Not Idempotent (Carried Forward)

**File**: `src/api/routes/tom.py:503`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_best_practices_and_benchmarks(...) -> dict[str, Any]:
    bp_seeds = get_best_practice_seeds()
    for bp_data in bp_seeds:
        bp = BestPractice(**bp_data)
        session.add(bp)   # No existence check
```
**Description**: The TOM seed endpoint unconditionally inserts all seed records without checking for existence, creating duplicates on repeated calls. The `metrics.py` seed endpoint at line 328 correctly checks for existence before inserting. The inconsistency is internally visible.

**Risk**: Duplicate best practice and benchmark records on repeated calls; data integrity violation.

**Recommendation**: Add per-record existence checks before inserting, consistent with the `metrics.py` implementation.

---

### [LOW] RESPONSE FORMAT: Rate Limit Error Bodies Are Inconsistent Between Two Middleware Paths

**File**: `src/api/middleware/security.py:155`, `src/api/main.py:275`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# RateLimitMiddleware (security.py:155) — no request_id
return Response(
    content='{"detail":"Rate limit exceeded"}',
    status_code=429,
    ...
)

# slowapi handler (main.py:275)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# slowapi handler produces: {"error": "Rate limit exceeded"}
```
**Description**: Rate limit exceeded responses come from two different code paths and produce different JSON shapes. `RateLimitMiddleware` produces `{"detail": "..."}` with no `request_id`. The slowapi handler produces `{"error": "..."}` (slowapi's default format). Clients cannot reliably detect rate limiting based on response body shape.

**Risk**: Clients parsing rate limit errors must handle two different response schemas; `request_id` absent from middleware 429s makes distributed tracing harder.

**Recommendation**: Customize the slowapi error handler to emit `{"detail": "Rate limit exceeded", "request_id": ...}` matching the platform error format. Alternatively, consolidate to a single rate limiter.

---

### [LOW] HTTP SEMANTICS: `PATCH /api/v1/engagements/{id}/archive` Uses PATCH Without Request Body (Carried Forward)

**File**: `src/api/routes/engagements.py:270`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.patch("/{engagement_id}/archive", response_model=EngagementResponse)
async def archive_engagement(
    engagement_id: UUID,
    user: User = ...,
    ...
) -> Engagement:
    engagement.status = EngagementStatus.ARCHIVED
```
**Description**: `PATCH` is used for a state transition action with no request body — the action is encoded entirely in the URL path. This violates HTTP spec (PATCH requires a body describing the change). Compare with `monitoring.py` which correctly uses `POST /jobs/{id}/activate` for state transition actions.

**Risk**: HTTP spec violation; minor inconsistency; low practical impact.

**Recommendation**: Change to `POST /{engagement_id}/archive` to match the action endpoint pattern used in `monitoring.py`.

---

## Pagination Bounds Verification

| Route File | Endpoint | Limit Bounds | Offset Bounds | Status |
|---|---|---|---|---|
| `engagements.py` | `list_engagements` | `ge=1, le=100` | `ge=0` | Confirmed |
| `engagements.py` | `get_audit_logs` | `ge=1, le=100` | `ge=0` | Confirmed |
| `evidence.py` | `list_evidence` | `ge=1, le=200` | `ge=0` | Confirmed |
| `evidence.py` | `catalog_evidence` | `ge=1, le=200` | `ge=0` | Confirmed |
| `evidence.py` | `get_fragments` | `ge=1, le=1000` | `ge=0` | Confirmed — now paginated |
| `users.py` | `list_users` | `ge=1, le=200` | `ge=0` | Confirmed |
| `users.py` | `list_engagement_members` | None | None | MISSING — see HIGH finding |
| `copilot.py` | `get_chat_history` | `le=200` (missing `ge=1`) | `ge=0` | Partial |
| `pov.py` | `get_process_elements` | `ge=1, le=200` | `ge=0` | Confirmed |
| `monitoring.py` | All list endpoints | `ge=1, le=200` | `ge=0` | Confirmed |
| `tom.py` | `list_toms`, `list_gaps` | `ge=1, le=200` | `ge=0` | Confirmed |
| `regulatory.py` | All list endpoints | `ge=1, le=200` | `ge=0` | Confirmed |
| `patterns.py` | `list_patterns` | `ge=1, le=200` | `ge=0` | Confirmed |
| `patterns.py` | `PatternSearchRequest.limit` | No `Field(ge/le)` bounds | N/A | MISSING |
| `simulations.py` | All list endpoints | `ge=1, le=100` | `ge=0` | Confirmed |
| `annotations.py` | `list_annotations` | `ge=1, le=200` | `ge=0` | Confirmed |
| `cost_modeling.py` | `list_role_rates` | No limit param | N/A | MISSING — see HIGH finding |
| `cost_modeling.py` | `list_volume_forecasts` | No limit param | N/A | MISSING — see HIGH finding |
| `event_spine.py` | `get_event_spine` | `ge=1, le=2000` | `ge=0` | High ceiling — see MEDIUM |
| `correlation.py` | List endpoints | `ge=1, le=1000` | `ge=0` | High ceiling — see MEDIUM |
| `survey_sessions.py` | `list_survey_sessions` | `ge=1, le=100` | `ge=0` | Confirmed |
| `survey_claims.py` | `list_survey_claims` | `ge=1, le=100` | `ge=0` | Confirmed |

**Pagination bounds are confirmed across the majority of endpoints. 4 gaps remain (members list, pattern search body, role rates, volume forecasts).**

---

## Response Format Consistency Analysis

The platform uses a consistent paginated list structure:

```json
{"items": [...], "total": N}
```

This is correctly implemented across ~95% of endpoints. The following deviate:

| Endpoint | Deviation |
|---|---|
| `GET /api/v1/engagements/{id}/members` | Returns `list[...]` with no wrapper or total |
| `POST /api/v1/patterns/search` | Returns `{items, total}` but `limit` is unbounded in request body |
| Multiple TOM endpoints | Return `dict[str, Any]` with no `response_model` |
| `GET /api/v1/governance/policies` | Returns raw policy YAML dict with no `response_model` |
| `GET /api/v1/governance/export/{id}` | Binary ZIP — no `responses={}` documenting content type |
| `GET /api/v1/cost-modeling/role-rates` | Has `{items, total}` envelope but `total: len(items)` is wrong |
| `GET /api/v1/cost-modeling/volume-forecasts` | Same `total: len(items)` defect |

---

## Authentication Status by Endpoint Category

| Category | Auth Required | Auth Type |
|---|---|---|
| `GET /api/v1/health` | No | Public — intentionally unauthenticated |
| Auth endpoints (`/auth/token`, `/auth/login`, `/auth/refresh`) | No (credentials in body) | Dev mode only for `/token` |
| All engagement, evidence, graph, pov, tom, regulatory routes | Yes | `require_permission(...)` via JWT |
| GDPR routes | Yes | `get_current_user` via JWT |
| Admin routes | Yes | `require_role(PLATFORM_ADMIN)` |
| Portal routes | Yes | `require_permission("portal:read")` |
| Quality/Pipeline routes | Yes | `require_engagement_access` via JWT |
| WebSocket routes | Varies | See `websocket.py` |
| MCP server | See MCP config | Mounted at `/mcp` |

The health endpoint is appropriately unauthenticated. All other routes enforce authentication through `Depends()` injection. No unauthenticated route was found that should require auth.

---

## Error Handling Assessment

**Positive findings:**
- Global `ValueError` handler in `main.py:460` returns consistent `{"detail": ..., "request_id": ...}`
- Global `Exception` handler at `main.py:469` prevents stack trace leakage in responses
- Route-level 404/403/409/422 errors use FastAPI `HTTPException` with the standard `{"detail": "..."}` format
- `request_id` is propagated through `RequestIDMiddleware` to all error responses (except rate limit 429s)
- Camunda/external service failures use explicit 502 Bad Gateway (correct semantics)

**Inconsistencies found:**
- Rate limit 429 from `RateLimitMiddleware` produces `{"detail": "..."}` without `request_id`
- Rate limit 429 from `slowapi` produces `{"error": "..."}` (different key name)
- `regulatory.py` overlay endpoints have no try/except around Neo4j calls — inconsistent with `graph.py`

---

## HTTP Method Semantics Assessment

| Method | Usage | Status |
|---|---|---|
| `GET` | Read-only retrieval | Correct throughout |
| `POST` | Resource creation and action triggers | Correct; creation uses 201; async triggers use 202 |
| `PATCH` | Partial field update | Correct; archive is an exception (no body) |
| `PUT` | Full replacement | Used correctly in `integrations.py` for field mapping |
| `DELETE` | Resource deletion | 204 used on 12 of 13 DELETE routes; `seed_lists.py` uses 200 |

---

## Code Quality Score

**Score: 7.0/10**

**Justification:**
- (+) Pagination bounds present across ~92% of list endpoints
- (+) Global error handlers prevent stack trace leakage
- (+) Rate limiting present on auth endpoints at both middleware and slowapi layers
- (+) HTTP status codes correct on ~98% of endpoints (201 creation, 204 deletion, 202 async)
- (+) Response format `{items, total}` consistent across ~95% of list endpoints
- (+) 456 endpoints across 76 files with high structural consistency is a significant engineering achievement
- (-) In-memory rate limiter is ineffective in multi-worker deployments (CRITICAL)
- (-) TODO comment in `gap_probes.py` docstring documents incomplete stub behavior (CRITICAL)
- (-) 4 list endpoints remain without pagination bounds
- (-) 33 route handlers use `-> Any` return type annotation
- (-) `total: len(items)` pattern is structurally incorrect in cost_modeling routes

---

## Checkbox Verification Results

- [x] **Response format consistency** — Verified: ~95% of list endpoints use `{items, total}`. 7 endpoints deviate (documented above).
- [x] **Pagination bounds** — Verified: ~92% of paginated endpoints have bounds. 4 gaps remain.
- [ ] **Rate limiting applied to all endpoints** — Not verified: In-memory rate limiter is ineffective in multi-worker deployments. Auth endpoints have per-IP limits only; no per-account brute-force protection.
- [x] **HTTP method usage** — Verified: Correct GET/POST/PUT/PATCH/DELETE semantics on ~98% of endpoints.
- [x] **Error handling consistency** — Verified: Global handlers present; route-level errors consistent. Minor inconsistency in rate limit 429 response body shape between two code paths.
- [x] **API versioning** — Verified: All routes use `/api/v1/` prefix (via router prefix or inline path). `X-API-Version` header set on all responses via middleware.
- [ ] **Response models on all routes** — Not fully verified: ~12 endpoints lack `response_model`. Several TOM, governance, and camunda/orchestration endpoints missing.
- [ ] **NO TODO COMMENTS** — Not verified: One TODO in `src/api/routes/gap_probes.py:82` documents incomplete feature in a production endpoint.
