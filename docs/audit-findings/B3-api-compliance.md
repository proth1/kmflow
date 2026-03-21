# B3: API Compliance Audit Findings (Re-Audit — 2026-03-20, Cycle 7)

**Agent**: B3 (API Compliance Auditor)
**Date**: 2026-03-20
**Scope**: REST standards, response format consistency, pagination, error handling, rate limiting, response_model compliance
**Supersedes**: Previous B3 audit dated 2026-03-19 (76 files, ~456 handlers)

---

## Summary

- **Total Route Files Audited**: 77 files in `src/api/routes/`
- **Total Endpoint Handlers**: 463 route handlers
- **Critical Issues**: 0
- **High Issues**: 1
- **Medium Issues**: 4
- **Low Issues**: 4

### Resolved Since Prior Audit (2026-03-19)

| Prior Finding | Resolution |
|---|---|
| CRITICAL: Auth rate limiter not Redis-backed | Fixed: `slowapi` now uses `storage_uri=_redis_url` (Redis-backed in non-dev) |
| CRITICAL: No per-email brute-force protection | Fixed: `_check_email_lockout` / `_record_failed_login` / `_clear_login_lockout` all implemented in `auth.py` with Redis + 15-min sliding window |
| HIGH: `graph_analytics.py` unbounded EvidenceItem query | Fixed: `.limit(500)` applied with warning log when capped |
| HIGH: `correlation.py` unbounded CanonicalActivityEvent query | Fixed: COUNT(*) guard added; raises 400 if total > 10,000 events |
| MEDIUM: `governance.py /policies` returns `policy_file` filesystem path | Fixed: `policy_file` removed from response; `response_model=PolicyListResponse` now declared |
| HIGH: 176 endpoints missing `response_model` (prior cycle) | Partially resolved: 55 endpoints corrected; 121 remain (26%) |

---

## Lessons Learned Counts (This Audit Cycle)

1. **Routes missing `response_model=`**: 121 of 463 (26%)
2. **Unbounded queries (select without .limit()) in route handlers**: 9 (in `pov.py` — scoped analytics selects for single-model aggregations)
3. **Missing `status_code` on POST**: 111 of 158 POST endpoints (70%)

---

## High Issues

### [HIGH] RESPONSE CONTRACT: 121 Endpoints Missing `response_model`

**File**: Multiple — representative: `src/api/routes/governance.py`, `src/api/routes/cost_modeling.py:227`, `src/api/routes/admin.py:26`, `src/api/routes/simulations.py:278`, `src/api/routes/seed_lists.py:111`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# cost_modeling.py:227 — POST with no response_model
@router.post("/engagements/{engagement_id}/cost-modeling/staffing")
async def compute_staffing(...) -> dict[str, Any]:

# admin.py:26 — critical admin operation with no schema
@router.post("/retention-cleanup")
async def run_retention_cleanup(...) -> dict[str, Any]:

# seed_lists.py:111 — mutation without contract
@router.post("/engagements/{engagement_id}/seed-lists/refine")
async def refine_seed_list(...) -> dict[str, Any]:
```
**Description**: 121 of 463 route handlers (26%) have no `response_model` on the decorator. Routes missing `response_model` produce no OpenAPI response schema, are not validated at serialization time, and can silently drift from their documented contract. The problem is concentrated in: `pov.py` (multiple analytics endpoints), `governance.py` (export, overlay, SLA endpoints), `cost_modeling.py` (all 4 computation endpoints), `tom.py` (several action endpoints), `admin.py` (both admin operations), and `simulations.py` (several create/delete operations).

**Progress note**: Improved from 176 (38%) in the prior cycle to 121 (26%) — 55 endpoints remediated. Issue remains HIGH as 26% of the API surface still has no validated response contract.

**Risk**: 26% of the API surface has no documented or validated response contract; response structure drift is undetected until runtime; `-> Any` return types defeat mypy analysis; OpenAPI docs are materially incomplete for integration clients.

**Recommendation**: Define Pydantic `response_model` types for all 121 remaining endpoints. Prioritize: (1) all POST/PATCH/DELETE mutation endpoints first (audit trail risk), (2) admin operations, (3) analytics/computation endpoints. The `response_model=dict` annotation is insufficient — use typed Pydantic models.

---

## Medium Issues

### [MEDIUM] HTTP SEMANTICS: 111 of 158 POST Endpoints Missing Explicit `status_code`

**File**: Multiple — representative: `src/api/routes/cost_modeling.py:227`, `src/api/routes/governance.py:413`, `src/api/routes/claim_write_back.py:59`, `src/api/routes/survey_sessions.py:53`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# cost_modeling.py:227 — creates a result, should be 200 (computation) or 201 (resource)
@router.post("/engagements/{engagement_id}/cost-modeling/staffing")
async def compute_staffing(...) -> dict[str, Any]:

# claim_write_back.py:59 — creates a write-back record
@router.post(...)
async def create_claim_write_back(...) -> dict[str, Any]:

# Correctly specified example for comparison:
@router.post("/definitions", response_model=SuccessMetricResponse, status_code=status.HTTP_201_CREATED)
```
**Description**: 111 of 158 POST endpoints (70%) have no explicit `status_code`, which causes FastAPI to default to `HTTP_200_OK`. REST convention requires `201 Created` for resource creation, `202 Accepted` for async operations, and `200 OK` for action/computation endpoints. Without explicit declaration, OpenAPI documents 200 for all of these — clients cannot distinguish creation from computation from async dispatch.

Top offending files by count of POST routes missing `status_code`:
- `tom.py`: 9 routes
- `governance.py`: 7 routes
- `cost_modeling.py`: 6 routes
- `taskmining.py`: 5 routes
- `simulations.py`: 5 routes
- `semantic.py`: 4 routes
- `monitoring.py`: 4 routes
- `auth.py`: 4 routes

**Risk**: HTTP contract ambiguity for integration clients; OpenAPI docs cannot differentiate created resources from computation results; response code changes become implicit breaking changes.

**Recommendation**: Add explicit `status_code=status.HTTP_201_CREATED` to all resource-creating POST endpoints. Use `status_code=status.HTTP_202_ACCEPTED` for async operation triggers (as is done correctly in `replay.py`). Use `status_code=status.HTTP_200_OK` for computation-only endpoints. The `replay.py` file is the correct reference pattern.

---

### [MEDIUM] UNBOUNDED QUERY: `pov.py` Analytics Endpoints Load All Elements Without Limit

**File**: `src/api/routes/pov.py:689`, `pov.py:771`, `pov.py:901`, `pov.py:993`, `pov.py:1057`, `pov.py:1153`, `pov.py:1221`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# pov.py:901 — get_engagement_dashboard: all elements for brightness distribution
elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
elements = list(elements_result.scalars().all())

# pov.py:993 — get_confidence_map: all elements for heatmap
elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model.id))
elements = list(elements_result.scalars().all())

# pov.py:437 — _get_elements_for_model helper (version diff): all elements
result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == model_id))
```
**Description**: Seven analytics endpoints in `pov.py` issue `select(ProcessElement).where(model_id==X)` with no `.limit()`. These are used for: dashboard KPIs (`get_engagement_dashboard`), confidence heatmap (`get_confidence_map`), confidence summary (`get_confidence_summary`), version diff helper (`_get_elements_for_model`), BPMN+elements payload (`get_latest_model_for_engagement`), BPMN confidence overlay (`get_model_bpmn`), and dark element identification (`get_dark_elements`). Process models can grow to thousands of elements as engagements mature.

**Risk**: Memory pressure and response latency proportional to model size; no upper bound on result set for any model; the dashboard endpoint (`get_engagement_dashboard`) is likely called frequently, amplifying the impact.

**Recommendation**: For endpoints that compute aggregates (dashboard, confidence summary), push the computation into SQL `COUNT/SUM` queries or window functions instead of loading all rows into Python. For endpoints that must return all elements (BPMN viewer), document the element count limit in the API contract and add a hard cap (e.g., 10,000 elements) with a warning log. The `get_process_elements` endpoint at `pov.py:504` is the correct reference — it already uses `.offset(offset).limit(limit)`.

---

### [MEDIUM] PAGINATION: Inconsistent `limit` Ceiling Across the API

**File**: Multiple — `src/api/routes/event_spine.py:101`, `src/api/routes/pov.py:523`, `src/api/routes/consistency.py:114`, `src/api/routes/simulations.py` (7 endpoints), `src/api/routes/monitoring.py` (4 endpoints)
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# event_spine.py:101 — ceiling 10x the standard
limit: int = Query(200, ge=1, le=2000, description="Maximum events to return"),

# pov.py:523 — evidence map ceiling 5x standard
limit: int = Query(default=200, ge=1, le=1000)

# pov.py:587 — gaps ceiling 5x standard
limit: int = Query(default=100, ge=1, le=1000)

# consistency.py:114 — ceiling 5x standard
limit: int = Query(default=20, ge=1, le=1000),

# engagements.py — platform standard
limit: int = Query(default=20, ge=1, le=100)
```
**Description**: The maximum `limit` ceiling (`le=`) varies from 100 to 2000 across list endpoints with no documented rationale. Breakdown of `le=` values across limit parameters: `le=1000` appears 44 times across 27 route files; `le=200` appears 33 times; `le=500` appears 5 times; `le=100` appears 5 times; `le=2000` appears once (`event_spine.py`). None of the `le=1000` or `le=2000` instances have inline comments justifying the exception to the `le=200` standard.

**Risk**: Higher ceilings allow larger result sets than intended; potential memory pressure at `le=2000`; inconsistent client experience across the API.

**Recommendation**: Establish a platform-wide default maximum of `le=200`. Routes needing higher limits should include an inline comment justifying the exception (e.g., `# le=2000: event spine requires high-cardinality loads for process mining`). The `le=1000` ceiling in 27 files should be reviewed and reduced where not justified.

---

### [MEDIUM] RATE LIMITING: Only 5 of 77 Route Files Have Rate Limiting Applied

**File**: `src/api/routes/copilot.py:43`, `src/api/routes/simulations.py:899`, `src/api/routes/intake.py:189`, `src/api/routes/auth.py:199`, `src/api/routes/gdpr.py:203`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# copilot.py — rate limited via copilot_rate_limit dependency
user: User = Depends(copilot_rate_limit),

# simulations.py — inline Redis rate limit
await _check_llm_rate_limit(request, str(user.id))

# intake.py:189 — slowapi limit on unauthenticated intake
@limiter.limit("20/hour")
async def submit_intake_files(...):

# No rate limiting on: POST /api/v1/tom/*, POST /api/v1/reports/*, POST /api/v1/semantic/*, etc.
@router.post("/engagements/{engagement_id}/cost-modeling/staffing")
async def compute_staffing(...)  # LLM or heavy computation; no rate limit
```
**Description**: The `RateLimitMiddleware` in `main.py` applies a global rate limit by IP address. Only 5 of 77 route files (6%) have additional per-user or per-endpoint rate limits: `auth.py`, `copilot.py`, `gdpr.py`, `intake.py`, `simulations.py`. Computation-heavy endpoints in `tom.py` (alignment scoring, roadmap generation), `reports.py` (report generation), `semantic.py` (entity extraction, embedding), and `assessment_matrix.py` (matrix computation) have no per-user rate limiting beyond the global IP ceiling.

**Risk**: Authenticated users can exhaust LLM or CPU-intensive operations without per-endpoint throttling; the global IP ceiling does not prevent a single authenticated user from hammering compute-heavy endpoints; no protection against per-tenant resource exhaustion.

**Recommendation**: Apply `copilot_rate_limit`-style per-user rate limiting to all LLM-backed and computation-heavy POST endpoints. The `src/core/rate_limiter.py` pattern is reusable. Priority endpoints: `tom.py` alignment scoring, `semantic.py` extract/embed, `reports.py` report generation, `assessment_matrix.py` compute.

---

## Low Issues

### [LOW] VERSIONING: `users.py`, `gdpr.py`, `health.py` Hardcode Full Paths in Route Decorators

**File**: `src/api/routes/users.py:143`, `src/api/routes/health.py:27`, `src/api/routes/gdpr.py:47`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
# users.py — router has no prefix
router = APIRouter(tags=["users"])

# users.py:143 — full path hardcoded in each decorator
@router.get("/api/v1/users", response_model=UserListResponse)
async def list_users(...):

# health.py:27 — same pattern
@router.get("/api/v1/health")
async def health_check() -> dict[str, Any]:
```
**Description**: Three of 77 route files create routers without a `prefix` and hardcode `/api/v1/...` into every individual route decorator. The other 74 files use `APIRouter(prefix="/api/v1/...", tags=[...])`.

**Risk**: Harder to maintain; error-prone when paths need updating for API version bumps.

**Recommendation**: Refactor to `APIRouter(prefix="/api/v1/users", tags=["users"])` etc. and simplify all path strings to relative paths.

---

### [LOW] HTTP SEMANTICS: `top_k` and `depth` Use Manual Validation Instead of `Query` Bounds

**File**: `src/api/routes/graph.py:217`, `src/api/routes/graph.py:183`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
async def semantic_search(
    query: str,
    top_k: int = 10,          # No Query bounds declared
    ...
) -> list[dict[str, Any]]:
    if top_k < 1 or top_k > 100:  # Manual validation
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, ...)
```
**Description**: `top_k` and `depth` use plain `int = N` with manual range checks instead of `Query(ge=1, le=N)`. FastAPI will not document the bounds in the OpenAPI spec and will not generate standard 422 validation errors for out-of-range inputs.

**Risk**: OpenAPI docs do not show valid bounds; manual validation duplicates FastAPI validation; out-of-range values produce 400 instead of the standard 422 for validation errors.

**Recommendation**: Change to `top_k: int = Query(default=10, ge=1, le=100)` and remove the manual `if` check. Apply the same fix to `depth` in `traverse_graph`.

---

### [LOW] HTTP SEMANTICS: `PATCH /api/v1/engagements/{id}/archive` Uses PATCH Without Request Body

**File**: `src/api/routes/engagements.py:271`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
@router.patch("/{engagement_id}/archive", response_model=EngagementResponse)
async def archive_engagement(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:delete")),
) -> Engagement:
    engagement.status = EngagementStatus.ARCHIVED
```
**Description**: `PATCH` is used for a state transition action with no request body — the action is fully encoded in the URL path segment `/archive`. HTTP spec requires PATCH to include a body describing the change. `monitoring.py` correctly uses `POST /jobs/{id}/activate` for equivalent state transition actions.

**Risk**: HTTP spec violation; inconsistency with the action-endpoint pattern used elsewhere.

**Recommendation**: Change to `POST /{engagement_id}/archive` to match the action endpoint pattern used in `monitoring.py`.

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
**Description**: The TOM seed endpoint unconditionally inserts all seed records without checking for prior existence. Repeated calls create duplicate best practice and benchmark records. The `metrics.py` seed endpoint at line 328 correctly checks for existence before inserting.

**Risk**: Duplicate best practice and benchmark records on repeated calls; data integrity violation.

**Recommendation**: Add per-record existence checks before inserting, consistent with the `metrics.py` implementation.

---

## Pagination Bounds Verification

| Route File | Endpoint | Limit Bounds | Offset Bounds | Status |
|---|---|---|---|---|
| `engagements.py` | `list_engagements` | `ge=1, le=100` | `ge=0` | Confirmed |
| `evidence.py` | `list_evidence` | `ge=1, le=200` | `ge=0` | Confirmed |
| `users.py` | `list_users` | `ge=1, le=200` | `ge=0` | Confirmed |
| `pov.py` | `get_process_elements` | `ge=1, le=200` | `ge=0` | Confirmed |
| `pov.py` | `get_dark_room_backlog` | `ge=1, le=200` | `ge=0` | Confirmed |
| `tom.py` | `list_toms`, `list_gaps` | `ge=1, le=200` | `ge=0` | Confirmed |
| `cost_modeling.py` | `list_role_rates` | `ge=1, le=200` | `ge=0` | Confirmed |
| `cost_modeling.py` | `list_volume_forecasts` | `ge=1, le=200` | `ge=0` | Confirmed |
| `gap_probes.py` | `list_gap_probes` | `ge=1, le=200` | `ge=0` | Confirmed |
| `monitoring.py` | All list endpoints | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `simulations.py` | All list endpoints (7) | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `scenarios.py` | `list_scenarios` | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `pov.py` | `get_evidence_map` | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `pov.py` | `get_evidence_gaps` | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `consistency.py` | list endpoints | `ge=1, le=1000` | `ge=0` | High ceiling — MEDIUM |
| `event_spine.py` | `get_event_spine` | `ge=1, le=2000` | `ge=0` | High ceiling — MEDIUM |
| `graph_analytics.py` | `get_triangulation_results` | Hard cap at 500 | N/A | Confirmed (resolved) |
| `correlation.py` | `run_correlation` | Guard: 400 if >10,000 | N/A | Confirmed (resolved) |
| `pov.py` | Analytics endpoints (7) | None | None | Unbounded — see MEDIUM |

---

## Response Format Consistency Analysis

The platform uses a consistent paginated list structure:

```json
{"items": [...], "total": N}
```

This is correctly implemented across ~95% of paginated endpoints. The following deviate:

| Endpoint | Deviation |
|---|---|
| `GET /api/v1/governance/export/{id}` | Binary ZIP — no `responses={}` documenting content type in OpenAPI |
| `pov.py` analytics endpoints | Return `dict[str, Any]` with no `response_model`; structure not enforced |
| `cost_modeling.py` computation endpoints (4) | `response_model=dict` (untyped); response structure undocumented |
| 121 endpoints total | Missing `response_model` — see HIGH finding |

---

## Authentication Status by Endpoint Category

| Category | Auth Required | Auth Type |
|---|---|---|
| `GET /api/v1/health` | No | Public — intentionally unauthenticated |
| `GET /api/v1/intake/{token}/progress` | Token-validated | Intake token (no user JWT) |
| `POST /api/v1/intake/{token}` | Token-validated + rate limited | Intake token, 20/hour |
| Auth endpoints (`/auth/token`, `/auth/login`, `/auth/refresh`) | No (credentials in body) | Email lockout enforced |
| All engagement, evidence, graph, pov, tom, regulatory routes | Yes | `require_permission(...)` via JWT |
| GDPR routes | Yes | `get_current_user` via JWT |
| Admin routes | Yes | `require_role(PLATFORM_ADMIN)` |
| Portal routes | Yes | `require_permission("portal:read")` |

No unauthenticated route was found that should require authentication. The health endpoint is appropriately unauthenticated.

---

## Error Handling Assessment

**Positive findings:**
- Global `ValueError` handler in `main.py` returns consistent `{"detail": ..., "request_id": ...}`
- Global `Exception` handler prevents stack trace leakage
- Route-level 404/403/409/422 errors use `HTTPException` with standard `{"detail": "..."}` format
- `request_id` propagated through `RequestIDMiddleware` to all error responses
- Camunda/external service failures use explicit 502 Bad Gateway
- `RateLimitMiddleware` returns `Retry-After` header on 429 responses
- `pipeline_quality.py` dashboard uses per-sub-endpoint try/except with logging (partial failure resilience)

**Inconsistencies found:**
- `semantic.py:367`: bare `except Exception: continue` with no logging inside a per-label entity query loop — silent failure on entity labels
- `governance.py` overlay and gap detection endpoints have no try/except around Neo4j calls — inconsistent with `graph.py` which explicitly handles errors

---

## HTTP Method Semantics Assessment

| Method | Usage | Status |
|---|---|---|
| `GET` | Read-only retrieval | Correct throughout |
| `POST` | Resource creation and action triggers | Correct; async triggers use 202; creation mostly uses 201 |
| `PATCH` | Partial field update | Correct; `archive` route is exception (no body — see LOW finding) |
| `PUT` | Full replacement | Used correctly in `integrations.py` for field mapping |
| `DELETE` | Resource deletion | 204 used on 9 of 14 `DELETE` routes; 5 DELETE routes missing `status_code=204` |

---

## Code Quality Score

**Score: 7.5/10**

**Justification:**
- (+) Prior CRITICALs fully resolved: Redis-backed slowapi, per-email lockout
- (+) Prior HIGHs fully resolved: triangulation capped at 500, correlation guarded at 10k
- (+) Prior MEDIUM resolved: `governance.py /policies` no longer leaks `policy_file`
- (+) Progress on response_model coverage: 176 → 121 missing (55 endpoints remediated)
- (+) Pagination bounds present across ~93% of list endpoints
- (+) Global error handlers prevent stack trace leakage
- (+) HTTP status codes correct on most endpoints (201 creation, 204 deletion, 202 async)
- (+) Response format `{items, total}` consistent across ~95% of list endpoints
- (-) 121 of 463 endpoints (26%) still missing `response_model` — HIGH
- (-) 111 of 158 POST endpoints missing explicit `status_code` — MEDIUM
- (-) 7 pov.py analytics endpoints issue unbounded element queries — MEDIUM
- (-) Rate limiting sparse: only 5 of 77 route files (6%) have per-endpoint limits — MEDIUM

---

## Checkbox Verification Results

- [x] **Response format consistency** — Verified: ~95% of list endpoints use `{items, total}`. Deviations documented above.
- [x] **Pagination bounds (le= constraint)** — Verified: all paginated endpoints have bounds. High ceilings flagged (event_spine le=2000; 27 files with le=1000).
- [x] **Rate limiting applied to sensitive endpoints** — Partially verified: copilot, simulations, intake, auth, gdpr rate limited. Computation-heavy tom/reports/semantic endpoints lack per-user limits (MEDIUM).
- [x] **HTTP method usage** — Verified: Correct GET/POST/PUT/PATCH/DELETE semantics on ~98% of endpoints.
- [x] **Error handling consistency** — Verified: Global handlers present; route-level errors consistent. Silent failure in `semantic.py` entity loop noted.
- [x] **API versioning** — Verified: All routes use `/api/v1/` prefix via router prefix or inline path. `X-API-Version` header set on all responses via middleware.
- [ ] **Response models on all routes** — Not verified: 121 of 463 endpoints lack `response_model` (26%).
- [x] **NO TODO COMMENTS** — Verified: No TODO comments found in any route file.
- [ ] **Explicit status_code on POST endpoints** — Not verified: 111 of 158 POST endpoints (70%) missing explicit status_code.
- [ ] **DELETE routes with 204** — Not fully verified: 5 of 14 DELETE routes missing `status_code=204`.
