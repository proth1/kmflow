# B3: API Compliance Audit Findings (Re-Audit — 2026-03-19)

**Agent**: B3 (API Compliance Auditor)
**Date**: 2026-03-19
**Scope**: REST standards, response format consistency, pagination, error handling, rate limiting, API versioning
**Supersedes**: Previous B3 audit dated 2026-02-26 (26 files, ~210 handlers)

---

## Summary

- **Total Route Files Audited**: 76 files in `src/api/routes/`
- **Total Endpoint Handlers**: ~456 route handlers
- **Critical Issues**: 1
- **High Issues**: 3
- **Medium Issues**: 5
- **Low Issues**: 4

### Resolved Since Prior Audit

The following HIGH findings from the prior audit were confirmed **resolved**:

| Prior Finding | Resolution |
|---|---|
| In-memory rate limiter bypassed in multi-worker deployments | Fixed: `RateLimitMiddleware` now uses Redis Lua `INCR + EXPIRE` (atomic, multi-worker safe) |
| `list_engagement_members` had no pagination | Fixed: `limit`/`offset` added; returns `{items, total}` with `MemberListResponse` |
| `cost_modeling.py` role rates and forecasts had unbounded queries | Fixed: pagination bounds and separate `COUNT(*)` query added to both routes |
| `gap_probes.py` TODO comment documenting incomplete stub | Fixed: TODO removed; docstring explicitly states ephemeral behavior; `probes` array now returned in response body |

---

## Critical Issues

### [CRITICAL] RATE LIMITING: Auth Endpoint Rate Limiter Not Account-Level

**File**: `src/api/routes/auth.py:46`, `src/api/routes/auth.py:116`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def get_token(request: Request, payload: TokenRequest, ...) -> dict[str, Any]:
```
**Description**: The `slowapi` limiter on `/token`, `/login`, and `/refresh/cookie` limits by remote IP address (`get_remote_address`) only. There is no per-account (per-email) failed-attempt counter. A distributed credential stuffing attack from multiple IPs is not rate limited at all. While the `RateLimitMiddleware` is now correctly Redis-backed (resolving the prior CRITICAL), `slowapi` itself is per-process and uses `get_remote_address` only — it does not share counters across uvicorn workers.

**Risk**: Distributed credential stuffing via multiple source IPs evades all current per-IP controls. An attacker cycling source IPs can attempt unlimited logins. Combined with the `slowapi` per-process limitation (no Redis backing), multi-worker deployments multiply the per-IP window by worker count.

**Recommendation**: (1) Back the `slowapi` limiter with Redis using `slowapi`'s `storage_uri` parameter. (2) Add per-email lockout in Redis: after N consecutive failed login attempts for the same email, block attempts for a configurable window regardless of source IP.

---

## High Issues

### [HIGH] UNBOUNDED QUERY: `graph_analytics.py` Fetches All Evidence Items Without Limit

**File**: `src/api/routes/graph_analytics.py:137`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
evidence_result = await session.execute(
    select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
)
evidence_items = list(evidence_result.scalars().all())
```
**Description**: `get_triangulation_results` fetches the complete set of `EvidenceItem` rows for an engagement with no `.limit()` clause. For each evidence item, it then calls `extract_entities(str(content))` in a Python loop — this is an O(N) async call loop. Engagements with thousands of evidence items will cause memory spikes and long request latency. The endpoint has no pagination — it returns all triangulation results for all activities at once.

**Risk**: Memory exhaustion and request timeout on large engagements; denial-of-service vector for any authenticated user with a large engagement; no upper bound on processing time.

**Recommendation**: Add a `limit` parameter with a sensible cap (e.g., `le=500`) and apply `.limit(limit).offset(offset)` to the evidence item query. For very large engagements, consider moving this computation to a background task.

---

### [HIGH] UNBOUNDED QUERY: `correlation.py` Fetches All Events for Correlation Run

**File**: `src/api/routes/correlation.py:63`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
events_result = await session.execute(
    select(CanonicalActivityEvent).where(CanonicalActivityEvent.engagement_id == engagement_id)
)
all_events = list(events_result.scalars().all())
```
**Description**: `run_correlation` fetches all `CanonicalActivityEvent` rows for an engagement unboundedly. Task mining deployments can generate thousands to hundreds of thousands of events over time. All fetched events are held in memory and iterated multiple times (deterministic pass, then assisted pass on unlinked subset). The deterministic linker and assisted linker process the full set synchronously.

**Risk**: Memory exhaustion proportional to event volume; request timeout on large datasets; no indication to the caller of partial processing.

**Recommendation**: Process correlation in batches or as a background task. If synchronous execution is maintained, add a hard limit with a documented maximum (e.g., `max_events=10000`) and return a warning in the response when truncated. A background task pattern (returning a job ID for polling) would match the pattern already used in `pov.py`.

---

### [HIGH] RESPONSE CONTRACT: ~35 Endpoints Return `-> Any` Without `response_model`

**File**: Multiple — representative examples: `src/api/routes/governance.py:330`, `src/api/routes/data_classification.py:97`, `src/api/routes/consent.py:76`, `src/api/routes/camunda.py:53`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# governance.py:330 — no response_model, no type annotation
@router.get("/policies")
async def list_policies(user: ...) -> dict[str, Any]:
    return {"policy_file": str(engine.policy_file), "policies": engine.policies}

# data_classification.py:97 — no response_model
@router.post("/retention/{engagement_id}/enforce")
async def enforce_retention(...) -> dict[str, Any]:

# consent.py:76 — no response_model on withdraw action
@router.post("/{consent_id}/withdraw")
async def withdraw_consent(...) -> dict[str, Any]:
```
**Description**: Approximately 35 route handlers have no `response_model` on the decorator. A subset of these also use `-> Any` as the return type annotation. Routes missing `response_model` do not produce OpenAPI response schemas, are not validated at serialization time, and can silently drift from their documented contract. Particularly notable: `governance.py /policies` returns `policy_file` — a server-side filesystem path — with no response model to constrain or sanitize the output.

**Risk**: No OpenAPI documentation for ~8% of endpoints; response structure changes are undetected until runtime; server filesystem path exposed in `governance.py /policies` response; `-> Any` defeats mypy static analysis.

**Recommendation**: Define Pydantic `response_model` types for all 35 endpoints. Remove `policy_file` from the `list_policies` response or replace with a sanitized version identifier. Replace `-> Any` return annotations with `dict[str, Any]` at minimum, or the specific Pydantic model.

---

## Medium Issues

### [MEDIUM] HTTP SEMANTICS: `PATCH /api/v1/engagements/{id}/archive` Uses PATCH Without Request Body

**File**: `src/api/routes/engagements.py:271`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.patch("/{engagement_id}/archive", response_model=EngagementResponse)
async def archive_engagement(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:delete")),
    ...
) -> Engagement:
    engagement.status = EngagementStatus.ARCHIVED
```
**Description**: `PATCH` is used for a state transition action with no request body — the action is fully encoded in the URL path segment `/archive`. HTTP spec requires PATCH to include a body describing the change. Compare with `monitoring.py` which correctly uses `POST /jobs/{id}/activate` for state transition actions.

**Risk**: HTTP spec violation; minor inconsistency with the action-endpoint pattern used elsewhere in the codebase.

**Recommendation**: Change to `POST /{engagement_id}/archive` to match the action endpoint pattern used in `monitoring.py` (`POST /jobs/{id}/activate`, `POST /jobs/{id}/pause`, `POST /jobs/{id}/stop`).

---

### [MEDIUM] HTTP SEMANTICS: `DELETE /api/v1/seed-lists` Returns HTTP 200 With Body

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
    return result
```
**Description**: The seed term "delete" is a soft delete (deprecation) that returns a body describing the updated state. All other 13 `DELETE` endpoints in the codebase use `HTTP_204_NO_CONTENT`. This is the sole exception. While 200 with body is technically valid for a soft delete, the inconsistency misleads consumers who expect `DELETE` to always return 204.

**Risk**: Inconsistency with platform DELETE convention; API consumers may mishandle responses if they assume 204 for all DELETEs.

**Recommendation**: Rename to `PATCH .../deprecate` which semantically describes a state transition that returns the modified resource, making HTTP 200 with body the natural choice.

---

### [MEDIUM] PAGINATION: Inconsistent `limit` Ceiling Across the API

**File**: Multiple — representative: `src/api/routes/event_spine.py`, `src/api/routes/correlation.py`, `src/api/routes/engagements.py`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# event_spine.py — limit ceiling 10x the standard
limit: int = Query(200, ge=1, le=2000, ...)

# governance.py — 2.5x standard
limit: int = Query(50, ge=1, le=500, ...)

# correlation.py — 5x standard
limit: int = Query(100, ge=1, le=1000, ...)

# engagements.py — platform standard
limit: int = Query(default=20, ge=1, le=100)
```
**Description**: The maximum `limit` ceiling (`le=`) varies from 100 to 2000 across list endpoints with no documented rationale. The project coding standards specify `le=200` as the default, but multiple files exceed this without explanation.

**Risk**: Higher ceilings allow larger result sets than intended; potential memory pressure at `le=2000`; inconsistent client experience across the API.

**Recommendation**: Establish a platform-wide default maximum of `le=200`. Routes needing higher limits (e.g., `event_spine`) should include an inline comment justifying the exception.

---

### [MEDIUM] RESPONSE FORMAT: Rate Limit Error Bodies Are Inconsistent Between Two Middleware Paths

**File**: `src/api/middleware/security.py:148`, `src/api/main.py:275`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# RateLimitMiddleware (security.py:148) — uses "detail", no request_id
return Response(
    content='{"detail":"Rate limit exceeded"}',
    status_code=429,
    headers={"Retry-After": str(ttl)},
)

# slowapi handler (main.py:275) — produces {"error": "Rate limit exceeded"}
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```
**Description**: Rate limit exceeded responses come from two code paths and produce different JSON shapes. `RateLimitMiddleware` produces `{"detail": "..."}` with no `request_id`. The `slowapi` handler (used for per-route `@limiter.limit()` decorators on auth endpoints) produces `{"error": "..."}` using slowapi's default format. Clients cannot distinguish between rate limit sources.

**Risk**: Clients parsing rate limit errors must handle two different response schemas; `request_id` absent from middleware 429s makes distributed tracing harder; inconsistent with the platform's `{"detail": ..., "request_id": ...}` error envelope.

**Recommendation**: Override slowapi's default exception handler to emit `{"detail": "Rate limit exceeded", "request_id": request.state.request_id}`. The `app.add_exception_handler` in `main.py:275` should use a custom handler instead of `_rate_limit_exceeded_handler`.

---

### [MEDIUM] INFORMATION DISCLOSURE: `GET /api/v1/governance/policies` Returns Filesystem Path

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
**Description**: The `policy_file` key returns the full server-side filesystem path of the YAML policy file (e.g., `/app/src/core/policies/governance.yaml`). This reveals deployment directory structure to any user with `governance:read` permission. No `response_model` is declared, so this leakage is not constrained by serialization.

**Risk**: Server filesystem path disclosure to authenticated users; no OpenAPI schema generated for this endpoint; policy structure changes silently break clients.

**Recommendation**: Remove `policy_file` from the response or replace it with a sanitized name/version string (e.g., `"policy_version": "1.0"`). Define a `GovernancePoliciesResponse` Pydantic model.

---

## Low Issues

### [LOW] VERSIONING: `users.py`, `gdpr.py`, `health.py` Hardcode Full Paths in Route Decorators

**File**: `src/api/routes/users.py:31`, `src/api/routes/health.py:20`, `src/api/routes/gdpr.py:47`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# users.py:31
router = APIRouter(tags=["users"])  # No prefix

# users.py:98 — path hardcoded in decorator
@router.post("/api/v1/users", response_model=UserResponse, ...)

# health.py:24 — same pattern
@router.get("/api/v1/health")
```
**Description**: Three of 76 route files create routers without a `prefix` and hardcode `/api/v1/...` into every individual route decorator. The other 73 files use `APIRouter(prefix="/api/v1/...", tags=[...])`. This divergence makes API version bumps require individual path updates in these files rather than a single prefix change.

**Risk**: Harder to maintain; diverges from the established pattern; error-prone when paths need updating.

**Recommendation**: Refactor to `APIRouter(prefix="/api/v1/users", tags=["users"])` etc. and simplify all path strings to relative paths.

---

### [LOW] HTTP SEMANTICS: `top_k` in `GET /api/v1/graph/search` Uses Manual Validation Instead of `Query` Bounds

**File**: `src/api/routes/graph.py:217`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
async def semantic_search(
    query: str,
    top_k: int = 10,          # No Query bounds declared
    ...
) -> list[dict[str, Any]]:
    if top_k < 1 or top_k > 100:  # Manual validation
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_k must be between 1 and 100",
        )
```
**Description**: `top_k` is a plain `int = 10` with no `Query(ge=1, le=100)` bounds, then manually validated in the handler body. FastAPI will not document the bounds in the OpenAPI spec. The same issue exists for `depth` in `traverse_graph` at line 183.

**Risk**: OpenAPI docs do not show valid bounds; manual validation duplicates what `Query` handles automatically; misses FastAPI's standard 422 validation error format.

**Recommendation**: Change to `top_k: int = Query(default=10, ge=1, le=100)` and remove the manual `if` check. Apply the same fix to `depth: int = Query(default=2, ge=1, le=5)` in `traverse_graph`.

---

### [LOW] HTTP SEMANTICS: `DELETE /orchestration/instances/{id}` Lacks Explicit `status_code`

**File**: `src/api/routes/orchestration.py:202`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.delete("/instances/{instance_id}")
async def cancel_process_instance(instance_id: str, ...) -> dict[str, Any]:
    await client.delete_process_instance(instance_id)
    return {"instance_id": instance_id, "status": "cancelled"}
```
**Description**: The DELETE route has no explicit `status_code` (defaults to 200). It returns a body. Compare with all other DELETE routes that use `HTTP_204_NO_CONTENT`. Since this DELETE returns a body the 200 is semantically reasonable, but the lack of explicit declaration is inconsistent. Additionally, all Camunda/orchestration routes use bare integer `502` instead of `status.HTTP_502_BAD_GATEWAY` for error responses — 10 occurrences across `camunda.py` and `orchestration.py`.

**Risk**: Style inconsistency; `status_code` not documented in OpenAPI; bare integers harder to audit than named constants.

**Recommendation**: Add `status_code=status.HTTP_200_OK` to the route decorator. Replace all bare `502` integers with `status.HTTP_502_BAD_GATEWAY`.

---

### [LOW] IDEMPOTENCY: `POST /api/v1/tom/seed` Creates Duplicates on Repeated Calls

**File**: `src/api/routes/tom.py:739`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.post("/seed", response_model=SeedResponse, status_code=status.HTTP_201_CREATED)
async def seed_best_practices_and_benchmarks(...) -> dict[str, Any]:
    bp_seeds = get_best_practice_seeds()
    for bp_data in bp_seeds:
        bp = BestPractice(**bp_data)
        session.add(bp)   # No existence check before insert
```
**Description**: The TOM seed endpoint unconditionally inserts all seed records without checking for prior existence. Repeated calls create duplicate best practice and benchmark records. The `metrics.py` seed endpoint at line 328 correctly checks for existence before inserting. The inconsistency creates data integrity risk.

**Risk**: Duplicate best practice and benchmark records on repeated calls; data integrity violation; inconsistent with `metrics.py` seed pattern.

**Recommendation**: Add per-record existence checks before inserting, consistent with the `metrics.py` implementation. Alternatively, use `INSERT ... ON CONFLICT DO NOTHING` at the database level.

---

## Pagination Bounds Verification

| Route File | Endpoint | Limit Bounds | Offset Bounds | Status |
|---|---|---|---|---|
| `engagements.py` | `list_engagements` | `ge=1, le=100` | `ge=0` | Confirmed |
| `engagements.py` | `get_audit_logs` | `ge=1, le=100` | `ge=0` | Confirmed |
| `evidence.py` | `list_evidence` | `ge=1, le=200` | `ge=0` | Confirmed |
| `evidence.py` | `catalog_evidence` | `ge=1, le=200` | `ge=0` | Confirmed |
| `evidence.py` | `get_fragments` | `ge=1, le=1000` | `ge=0` | Confirmed |
| `users.py` | `list_users` | `ge=1, le=200` | `ge=0` | Confirmed |
| `users.py` | `list_engagement_members` | `ge=1, le=200` | `ge=0` | Confirmed (resolved) |
| `pov.py` | `get_process_elements` | `ge=1, le=200` | `ge=0` | Confirmed |
| `monitoring.py` | All list endpoints | `ge=1, le=200` | `ge=0` | Confirmed |
| `tom.py` | `list_toms`, `list_gaps` | `ge=1, le=200` | `ge=0` | Confirmed |
| `regulatory.py` | All list endpoints | `ge=1, le=200` | `ge=0` | Confirmed |
| `patterns.py` | `list_patterns` | `ge=1, le=200` | `ge=0` | Confirmed |
| `cost_modeling.py` | `list_role_rates` | `ge=1, le=200` | `ge=0` | Confirmed (resolved) |
| `cost_modeling.py` | `list_volume_forecasts` | `ge=1, le=200` | `ge=0` | Confirmed (resolved) |
| `correlation.py` | All list endpoints | `ge=1, le=1000` | `ge=0` | High ceiling — see MEDIUM |
| `event_spine.py` | `get_event_spine` | `ge=1, le=2000` | `ge=0` | High ceiling — see MEDIUM |
| `graph_analytics.py` | `get_triangulation_results` | None | None | MISSING — see HIGH |
| `correlation.py` | `run_correlation` | None | None | MISSING — see HIGH |
| `incidents.py` | `list_incidents` | `ge=1, le=100` | `ge=0` | Confirmed |
| `micro_surveys.py` | `list_micro_surveys` | `ge=1, le=100` | `ge=0` | Confirmed |
| `transfer_controls.py` | `list_transfer_logs` | `ge=1, le=100` | `ge=0` | Confirmed |

**Pagination bounds are confirmed across the majority of endpoints. 2 functional gaps remain (triangulation results, correlation run).**

---

## Response Format Consistency Analysis

The platform uses a consistent paginated list structure:

```json
{"items": [...], "total": N}
```

This is correctly implemented across ~95% of endpoints. The following deviate:

| Endpoint | Deviation |
|---|---|
| `GET /api/v1/governance/policies` | Returns raw policy YAML dict with no `response_model`; includes `policy_file` (filesystem path) |
| `GET /api/v1/governance/export/{id}` | Binary ZIP — no `responses={}` documenting content type in OpenAPI |
| Multiple Camunda routes | Return bare `list[dict]` / `dict` with no `response_model` |
| ~35 endpoints total | Missing `response_model` — no OpenAPI response schema |
| `consent.py /withdraw` | No `response_model` on state-change action |
| `data_classification.py /retention/enforce` | No `response_model` |

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

The health endpoint is appropriately unauthenticated. All other routes enforce authentication through `Depends()` injection. No unauthenticated route was found that should require authentication.

---

## Error Handling Assessment

**Positive findings:**
- Global `ValueError` handler in `main.py:460` returns consistent `{"detail": ..., "request_id": ...}`
- Global `Exception` handler at `main.py:469` prevents stack trace leakage in production
- Route-level 404/403/409/422 errors use FastAPI `HTTPException` with the standard `{"detail": "..."}` format
- `request_id` propagated through `RequestIDMiddleware` to all error responses (except rate limit 429s from middleware)
- Camunda/external service failures use explicit 502 Bad Gateway (correct semantics)
- `RateLimitMiddleware` now correctly returns `Retry-After` header on 429 responses

**Inconsistencies found:**
- Rate limit 429 from `RateLimitMiddleware` produces `{"detail": "..."}` without `request_id`
- Rate limit 429 from `slowapi` produces `{"error": "..."}` (different key name, no `request_id`)
- `governance.py` overlay and gap detection endpoints have no try/except around Neo4j calls — inconsistent with `graph.py` which explicitly handles `ValueError` and `RuntimeError`

---

## HTTP Method Semantics Assessment

| Method | Usage | Status |
|---|---|---|
| `GET` | Read-only retrieval | Correct throughout |
| `POST` | Resource creation and action triggers | Correct; creation uses 201; async triggers use 202 |
| `PATCH` | Partial field update | Correct; `archive` route is exception (no body — see MEDIUM finding) |
| `PUT` | Full replacement | Used correctly in `integrations.py` for field mapping |
| `DELETE` | Resource deletion | 204 used on 12 of 13 `DELETE` routes; `seed_lists.py` uses 200 (soft delete — see MEDIUM) |

---

## Code Quality Score

**Score: 7.5/10**

**Justification:**
- (+) Redis-backed `RateLimitMiddleware` — correct multi-worker rate limiting (prior CRITICAL resolved)
- (+) Pagination bounds present across ~93% of list endpoints
- (+) Global error handlers prevent stack trace leakage
- (+) HTTP status codes correct on ~98% of endpoints (201 creation, 204 deletion, 202 async)
- (+) Response format `{items, total}` consistent across ~95% of list endpoints
- (+) 456 endpoints across 76 files with high structural consistency
- (+) `list_engagement_members` pagination resolved from prior audit
- (+) `cost_modeling.py` pagination and COUNT fixes resolved from prior audit
- (-) `slowapi` limiter not Redis-backed; no per-account brute-force protection (remaining CRITICAL)
- (-) 2 list endpoints still issue unbounded queries (triangulation, correlation run)
- (-) ~35 route handlers missing `response_model`
- (-) Information disclosure in `governance.py /policies` (filesystem path)

---

## Checkbox Verification Results

- [x] **Response format consistency** — Verified: ~95% of list endpoints use `{items, total}`. 7 endpoints deviate (documented above).
- [x] **Pagination bounds** — Verified: ~93% of paginated endpoints have bounds. 2 functional gaps remain (triangulation, correlation run). Prior gaps in cost_modeling and members resolved.
- [ ] **Rate limiting applied to all endpoints** — Not fully verified: `RateLimitMiddleware` is now Redis-backed (prior CRITICAL resolved). `slowapi` on auth endpoints is still per-process and IP-only; no per-account brute-force protection.
- [x] **HTTP method usage** — Verified: Correct GET/POST/PUT/PATCH/DELETE semantics on ~98% of endpoints.
- [x] **Error handling consistency** — Verified: Global handlers present; route-level errors consistent. Minor inconsistency in rate limit 429 response body shape between two code paths.
- [x] **API versioning** — Verified: All routes use `/api/v1/` prefix (via router prefix or inline path). `X-API-Version` header set on all responses via middleware.
- [ ] **Response models on all routes** — Not fully verified: ~35 endpoints lack `response_model`. Several governance, consent, data_classification, and camunda endpoints missing.
- [x] **NO TODO COMMENTS** — Verified: Prior TODO in `gap_probes.py` resolved. No TODO comments found in any route file.
