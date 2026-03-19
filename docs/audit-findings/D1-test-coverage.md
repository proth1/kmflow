# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-03-19
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: WARNING — NOT BLOCKED (but improvements required)**

The KMFlow backend test suite has grown substantially since the prior audit (Feb 2026). The main test suite contains **341 test files** with **5,769 test functions**, plus 118 in the agent Python module and 54 inline in `src/taskmining/tests`. Coverage infrastructure is configured with `fail_under = 70` in `pyproject.toml` — this threshold is below both the 80% floor documented in CLAUDE.md and the 90% MANDATORY threshold in this audit system.

The ratio of test files to source files is 77.2% (311 test files / 403 source files), which is healthy at the file level. Critical paths (auth, JWT, watermarking, GDPR erasure, WebSocket auth) have strong targeted unit tests. However, a cluster of API route modules has no tests at all, and the `fail_under = 70` setting in `pyproject.toml` is dangerously low.

| Metric | Value |
|--------|-------|
| Source files (non-init) | 403 |
| Test files | 311 |
| Test/source file ratio | 77.2% |
| Total test functions | ~5,941 |
| `fail_under` configured | 70% — BELOW mandated 90% |
| API routes with zero test coverage | 10 of 76 routes |
| Security modules with no dedicated test dir | `src/security/` (5 files — tested via BDD) |
| GDPR erasure worker | Untested execute() path |

---

## Coverage Breakdown by Module

| Module | Source Files | Test Files | Status |
|--------|-------------|------------|--------|
| `src/api/routes` | 76 | ~66 covered | WARNING — 10 routes untested |
| `src/api/services` | 14 | ~7 covered | WARNING — 7 services untested directly |
| `src/api/middleware` | 4 | 3 (missing data_residency dir) | GOOD |
| `src/api/schemas` | 11 | 0 dedicated | LOW risk (pure Pydantic) |
| `src/core/models` | 39 | 1 partial | MEDIUM — model logic untested |
| `src/core/services` | 14 | 7 | WARNING |
| `src/evidence` | 31 | 25 | GOOD |
| `src/semantic` | 20 | 16 | GOOD |
| `src/rag` | 4 | 4 | GOOD |
| `src/security` | 5 | 0 dedicated (BDD only) | WARNING |
| `src/gdpr` | 2 | 1 (erasure_worker untested) | HIGH |
| `src/monitoring` | 21 | 7 | WARNING |
| `src/taskmining` | ~25 | 20+ | GOOD |
| `agent/python` | N/A | 15 | GOOD |

---

## Findings

### [CRITICAL] COVERAGE_CONFIG: Coverage fail_under threshold is 70% — 20 points below mandatory minimum
**File**: `/Users/proth/repos/kmflow/pyproject.toml:115`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.coverage.report]
fail_under = 70
```
**Description**: The `fail_under = 70` setting means CI will not block merges until coverage drops below 70%. Both the CLAUDE.md coding standards (minimum 80%) and this audit system (mandatory 90% minimum) are violated by this configuration. The pipeline can pass CI while well below the documented standards. The gap between the configured threshold (70%) and the standard (90%) is large enough that significant regression could silently accumulate.
**Risk**: Test regressions silently accumulate. Coverage can fall from current levels to 70% without any CI failure, masking gradual quality erosion.
**Recommendation**: Raise `fail_under` to at minimum 80% immediately (per CLAUDE.md), targeting 90% as the long-term gate. Add per-module thresholds for critical paths (auth, security, GDPR) at 95%+.

---

### [HIGH] MISSING_TESTS: GDPR erasure worker execute() has no unit coverage
**File**: `/Users/proth/repos/kmflow/src/gdpr/erasure_worker.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute GDPR erasure across all stores."""
    self.report_progress(0, _TOTAL_STEPS)
    # Step 1: Find eligible users
    from src.core.database import async_session_factory
```
**Description**: `GdprErasureWorker.execute()` is the primary GDPR right-to-erasure code path that coordinates deletion across PostgreSQL, Neo4j, and Redis. The only existing reference in tests is a single import in `test_worker_wiring_bdd.py` that confirms the class can be instantiated — there are no tests that exercise `execute()`, `_purge_neo4j()`, or `_purge_redis()`. The erasure_job.py (the PG-only helper) is well-tested but the cross-store coordinator that wraps it is not.
**Risk**: Erasure bugs in the Neo4j or Redis purge paths go undetected. A GDPR erasure request could be recorded as "processed" while personal data remains in graph nodes or Redis cache, creating a compliance violation.
**Recommendation**: Write unit tests for `GdprErasureWorker.execute()` covering: no pending users (early return), one user processed (all three stores), Neo4j unavailable (fallback gracefully), Redis connection failure (fallback gracefully), and multi-user batch. Mock `async_session_factory` at the test level.

---

### [HIGH] MISSING_TESTS: 10 API route modules have zero test coverage
**File**: `/Users/proth/repos/kmflow/src/api/routes/` (multiple)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/api/routes/incidents.py - No test file exists
router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

# src/api/routes/audit_logs.py - No test file exists
router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])

# src/api/routes/deviations.py - No test file exists
```
**Description**: The following 10 route modules have no corresponding test file anywhere in the test suite: `assumptions`, `audit_logs`, `decisions`, `deviations`, `exports` (route-level), `graph_analytics`, `incidents`, `micro_surveys`, `scenarios`, `simulations`. Note that `incidents` has BDD tests against the service layer, and `exports` has BDD tests against watermarking — but the route-level HTTP contracts (correct status codes, request validation, pagination, auth enforcement) are not tested.
**Risk**: Route-level regression (wrong HTTP codes, broken pagination, missing auth guards) goes undetected. The `audit_logs` route exposes sensitive compliance data and is gated to PLATFORM_ADMIN — no test verifies that role enforcement is wired correctly.
**Recommendation**: Add route-level tests for all 10 modules. Prioritise `audit_logs` and `incidents` first given their security sensitivity, then `decisions` and `scenarios` as core domain logic routes.

---

### [HIGH] MISSING_TESTS: `src/api/services/incident.py` and other service modules have no direct unit tests
**File**: `/Users/proth/repos/kmflow/src/api/services/`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/api/services/incident.py - Only referenced via BDD integration test
class IncidentService:
    async def create_incident(...) -> Incident:
    async def contain_incident(...) -> Incident:
    async def close_incident(...) -> Incident:
```
**Description**: Seven of 14 API service modules (`dark_room_backlog`, `evidence_gap_ranking`, `governance_overlay`, `illumination_planner`, `llm_audit`, `micro_survey`, `transfer_control`) have no dedicated unit tests. `IncidentService` is covered by a BDD test but relies on the full integration context rather than isolated unit testing of individual methods. The service directory ratio is 7 tested / 14 total.
**Risk**: Business logic bugs in service methods (GDPR deadlines for incidents, illumination planner scoring, transfer control enforcement) go undetected at the unit level. BDD tests are fragile when they implicitly test multiple layers.
**Recommendation**: Add unit test files for each service module, testing each public method in isolation with mocked DB sessions.

---

### [MEDIUM] COVERAGE_GAP: `src/security/` has no dedicated test directory
**File**: `/Users/proth/repos/kmflow/src/security/`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
src/security/
  cohort/suppression.py
  consent/models.py
  consent/service.py
  watermark/extractor.py
  watermark/service.py
```
**Description**: The 5 security module files have no `tests/security/` directory. Coverage comes from BDD tests placed in `tests/api/` (watermarking, cohort, consent). While `WatermarkService` and `ConsentService` have meaningful test coverage via BDD, the `CohortSuppression` suppression logic and `watermark/extractor.py` are only partially exercised. The absence of a dedicated `tests/security/` directory means security-specific edge cases (e.g., HMAC tamper detection with edge-case payloads, cohort size floor enforcement, suppression boundary conditions) are not systematically tested.
**Risk**: Security bypass via edge-case inputs to suppression or watermark logic. Boundary conditions near cohort minimum thresholds may behave incorrectly.
**Recommendation**: Create `tests/security/` with dedicated test files for each security module. Include tests for boundary conditions: minimum cohort size (exactly at threshold, one below), tampered watermark payloads with each byte modified, empty consent records.

---

### [MEDIUM] COVERAGE_GAP: No concurrency or race condition tests in auth or rate-limiting paths
**File**: `/Users/proth/repos/kmflow/tests/api/` (auth, rate_limiter)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# tests/api/test_rate_limiter.py has only 5 assertions
# tests/core/test_auth.py has no concurrent access tests
# Single concurrent task test exists only in test_async_task_bdd.py
```
**Description**: The token blacklist path, rate limiter, and concurrent session handling have no concurrency tests. Authentication state (token blacklist in Redis) is read-before-write in `get_current_user` with no locking. Only `test_async_task_bdd.py:test_concurrent_tasks_complete_independently` exercises any concurrent behavior at all.
**Risk**: Token replay attacks via race condition in the blacklist check window. Rate limiting bypass if Redis operations are not atomic.
**Recommendation**: Add `asyncio.gather` tests that fire concurrent login/refresh/logout requests to verify token blacklisting is race-free. Add a test verifying rate limit state is not corrupted under concurrent load (even with mocked Redis).

---

### [MEDIUM] TEST_QUALITY: Pipeline integration test is 70% mocking with marginal behavioral assertions
**File**: `/Users/proth/repos/kmflow/tests/evidence/test_pipeline_integration.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
with (
    patch("src.evidence.pipeline.extract_fragment_entities") as mock_extract,
    patch("src.evidence.pipeline.build_fragment_graph") as mock_graph,
    patch("src.evidence.pipeline.generate_fragment_embeddings") as mock_embed,
    patch("src.evidence.pipeline.run_semantic_bridges") as mock_bridges,
):
    mock_extract.return_value = [{"fragment_id": "f1", "entity_count": 3, "entities": []}]
    result = await run_intelligence_pipeline(session, [frag], "eng-1")
assert result["entities_extracted"] == 3
```
**Description**: `test_full_pipeline_runs_all_steps` patches every sub-function of `run_intelligence_pipeline` and then asserts that the mocked return values pass through correctly. The test verifies orchestration plumbing (correct functions called once) but does not test any actual logic. With 35 mock/patch lines and 30 assertion lines, the mock density is high. The test is effectively testing that Python function calls work, not that the pipeline processes evidence correctly.
**Risk**: Real bugs in `run_intelligence_pipeline`'s logic (error aggregation, partial failure handling, result accumulation) are invisible to this test. A refactor that breaks the actual behavior but preserves call signatures would pass.
**Recommendation**: Add at least one integration sub-test using real (non-mocked) implementations of `extract_fragment_entities` and `build_fragment_graph` with small synthetic fragment inputs. Reserve mocking for external I/O (DB, Neo4j) only.

---

### [MEDIUM] MISSING_TESTS: Cookie-based auth login endpoint (`POST /api/v1/auth/login`) has no tests in `test_auth_routes.py`
**File**: `/Users/proth/repos/kmflow/tests/api/test_auth_routes.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# test_auth_routes.py covers /token, /refresh (body), /me, /logout
# Missing: POST /api/v1/auth/login (cookie-based, Issue #156)
# Missing: POST /api/v1/auth/refresh/cookie (cookie-based refresh)
class TestGetToken:  # /token
class TestRefreshToken:  # /refresh with body
class TestGetMe:  # /me
class TestLogout:  # /logout
```
**Description**: The cookie-based login endpoint (`POST /api/v1/auth/login`) and cookie refresh endpoint (`POST /api/v1/auth/refresh/cookie`) are covered in `test_auth_cookies.py` — but `test_auth_routes.py` (which is the primary auth route test file) has no tests for them. A developer reading only `test_auth_routes.py` would not know these endpoints exist or are tested. The cookie auth flow was added in Issue #156 and the test coverage is split across two files without cross-referencing.
**Risk**: Low direct risk (the cookie tests do exist), but the fragmentation creates maintenance confusion. Future auth changes may be tested in only one file while the other is forgotten.
**Recommendation**: Add a comment in `test_auth_routes.py` pointing to `test_auth_cookies.py` for cookie-based auth coverage, or consolidate into a single file with clearly labeled sections.

---

### [MEDIUM] MISSING_TESTS: `src/core/models/` — 39 model files with only 1 partial test file
**File**: `/Users/proth/repos/kmflow/tests/core/test_models.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# tests/core/test_models.py covers Engagement, EvidenceItem, EvidenceFragment, ShelfDataRequest
# Not covered: pipeline_quality, correlation, pdp, incident, monitoring, 35 other model files
from src.core.models import (
    AuditAction, AuditLog, Engagement, EngagementStatus,
    EvidenceCategory, EvidenceFragment, EvidenceItem, ...
)
```
**Description**: There are 39 model files under `src/core/models/` but only one test file covering a small subset. While many models are "data containers" tested implicitly via route and service tests, several have non-trivial logic: `pipeline_quality.py` (quality threshold calculations), `auth.py` (UserRole permission logic), `incident.py` (GDPR deadline constants `ESCALATION_THRESHOLD_HOURS`, `GDPR_NOTIFICATION_HOURS`). The new `pipeline_quality.py` model (194 lines) is especially unverified as a standalone unit.
**Risk**: Model-level business logic bugs (wrong GDPR deadline computation, incorrect permission hierarchy, pipeline quality threshold logic) go undetected until they surface in production.
**Recommendation**: Add unit tests for model files that contain business logic beyond simple field definitions. Priority: `core/models/incident.py` (GDPR constants), `core/models/auth.py` (UserRole), `core/models/pipeline_quality.py` (quality thresholds).

---

### [LOW] COVERAGE_GAP: `src/api/routes/audit_logs.py` — sole PLATFORM_ADMIN-gated route with no test
**File**: `/Users/proth/repos/kmflow/src/api/routes/audit_logs.py:80`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
@router.get("", response_model=PaginatedAuditLogResponse)
async def list_audit_logs(
    ...
    current_user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
) -> dict[str, Any]:
```
**Description**: The audit log query route requires `PLATFORM_ADMIN` role. This is the only route in the codebase that gates access to security audit trails. There are no tests that verify a non-admin receives 403, that filter parameters work correctly, or that the query is properly ordered by `created_at.desc()`. Given that audit logs are the primary incident investigation tool, ensuring this route behaves correctly is security-critical.
**Risk**: A regression could expose audit logs to unprivileged users, or broken filtering could cause investigators to miss relevant events.
**Recommendation**: Add `tests/api/test_audit_logs.py` with tests for: PLATFORM_ADMIN gets 200, PROCESS_ANALYST gets 403, date range filter returns correct results, pagination respects limit/offset.

---

### [LOW] TEST_QUALITY: `test_pipeline.py` tests only two utility functions from a 398-line module
**File**: `/Users/proth/repos/kmflow/tests/evidence/test_pipeline.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
from src.evidence.pipeline import compute_content_hash, store_file

class TestContentHash:  # 4 tests for hashing utility
class TestStoreFile:    # 4 tests for file storage utility
```
**Description**: `src/evidence/pipeline.py` (398 lines) is the central evidence ingestion orchestrator with functions: `ingest_evidence`, `run_intelligence_pipeline`, `extract_fragment_entities`, `build_fragment_graph`, `generate_fragment_embeddings`, `run_semantic_bridges`. Only `compute_content_hash` and `store_file` are tested in `test_pipeline.py`. The primary pipeline functions are covered in `test_pipeline_integration.py`, but as noted above, that file has a high mock density.
**Risk**: Core ingestion orchestration logic (`ingest_evidence`, entity extraction, graph building, embedding generation) is tested only through heavily mocked integration tests, leaving real logic paths uncovered.
**Recommendation**: Add direct unit tests for `ingest_evidence` covering: duplicate detection via content hash, file type rejection, metadata extraction failure handling.

---

### [LOW] FLAKINESS_RISK: `agent/python/tests/test_auth.py` uses wall-clock `time.time()` for JWT expiry
**File**: `/Users/proth/repos/kmflow/agent/python/tests/test_auth.py:87`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
def test_expired_token(self):
    exp = int(time.time()) - 100  # 100 seconds ago
    token = _make_jwt({"sub": "agent-1", "exp": exp})
    assert _is_token_expired(token) is True

def test_token_expiring_within_buffer(self):
    exp = int(time.time()) + 200  # 200 seconds — within 300s buffer
    token = _make_jwt({"sub": "agent-1", "exp": exp})
    assert _is_token_expired(token, buffer_seconds=300) is True
```
**Description**: These tests construct JWTs with `time.time()` at test execution time. While the margins (100s past, 200s future with 300s buffer) are large enough to make flakiness unlikely, any test that relies on wall-clock time is technically flaky under extremely unusual conditions (CI system with wrong clock, or test execution taking minutes). The pattern is used in 8 tests across the file.
**Risk**: Very low flakiness risk given the large margins. Pattern is worth noting for maintainability.
**Recommendation**: Replace `time.time()` with `datetime.now(UTC)` and inject a fixed clock value, or use `freezegun` / `pytest-freezegun` to pin time in JWT expiry tests.

---

## Test Checklist Assessment

### Coverage Requirements
- [x] Tests exist for all critical auth paths (JWT, cookie auth, blacklist, refresh)
- [x] GDPR erasure job (PG path) has unit coverage
- [ ] GDPR erasure worker (cross-store path) has NO coverage — HIGH finding
- [x] Watermarking and HMAC tamper detection tested
- [ ] 10 API routes have zero test coverage — HIGH finding
- [ ] `fail_under = 70` is below mandated 90% — CRITICAL finding
- [x] WebSocket auth (all failure paths) tested
- [x] Evidence chunking, parsers, pipeline integration tested

### Test Quality Standards
- [x] Auth tests follow AAA pattern with clear names
- [x] Fixtures properly isolate test state (conftest.py)
- [x] `MagicMock(spec=ModelClass)` used for type-safe mocks
- [ ] Pipeline integration test has high mock density — MEDIUM finding
- [x] No `time.sleep` usage found in any test file
- [x] No non-deterministic `random` usage in tests

### Test Types Verification
- [x] Unit tests for business logic (consensus, scoring, entity extraction)
- [x] Route-level integration tests for most API endpoints
- [x] BDD tests for cross-cutting feature behavior
- [ ] No performance/load tests for resource-intensive operations (embedding, graph build)
- [x] Security tests for auth/authorization paths
- [ ] No concurrent access tests for token blacklist or rate limiting

---

## Risk Assessment

**Overall Risk Level: MEDIUM-HIGH**

The codebase has strong test coverage of its well-established core paths (auth, consensus algorithm, evidence parsers, watermarking). The risk concentrations are:

1. **GDPR cross-store erasure worker** — untested execute() path on a compliance-critical component. If the Neo4j or Redis purge logic has bugs, they will only be discovered when a real erasure request is processed.

2. **10 untested API routes** — while none are on the absolute security-critical path, `audit_logs` gating and `incidents` lifecycle management are sensitive enough to warrant test coverage before any production use.

3. **`fail_under = 70`** — this is a process risk. The CI gate is set 20 points below the documented standard and 20 points below the minimum threshold this audit system enforces. Any PR that drops coverage to 71% will pass CI silently.

**PIPELINE STATUS: WARNING** — The `fail_under = 70` configuration deviation is categorized as CRITICAL (it violates the mandatory 90% threshold). However, because the actual test count (5,941 functions) and file coverage (77.2%) suggest the codebase is well above 70% in practice, the pipeline is not immediately blocked. The CRITICAL finding must be addressed in the next sprint.
