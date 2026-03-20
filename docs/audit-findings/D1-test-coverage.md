# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-03-20
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: WARNING (90-94% estimated — not BLOCKED, but improvements required)**

The KMFlow backend test suite has grown significantly since the prior audit, now comprising 332 test files (main suite) and 14 agent test files covering 421 non-init source modules (78.9% file-coverage ratio). The `fail_under` threshold has been correctly raised to **90%** in `pyproject.toml`, and several HIGH-severity gaps from the previous audit have been remediated: simulation engine tests exist, worker tests exist, watermark extractor tests exist, and agent GDPR `audit_logger` and `purge` tests exist.

The primary remaining concerns are: (1) **1,733 bare `MagicMock()` instances without `spec=`** across 195 test files, representing a pervasive test quality risk where attribute-access typos pass silently; (2) **7 API route modules with no dedicated test file** including `assumptions`, `audit_logs`, `decisions`, `exports`, `micro_surveys`, `patterns`, and `simulations`; (3) **agent GDPR `retention.py` still has no test file**; (4) **timing-dependent `asyncio.sleep` assertions** remain in `test_worker_dispatch.py`.

| Metric | Value |
|--------|-------|
| Source files (non-init, src/) | 421 |
| Test files (main suite) | 332 |
| Test files (agent) | 14 |
| Test/source file ratio | 78.9% |
| `fail_under` configured | 90% (CORRECT — meets audit requirement) |
| Route files in src/api/routes/ | 77 |
| Route files with no dedicated test | 7 |
| Bare `MagicMock()` instances | 1,733 across 195 files |
| `MagicMock(spec=...)` instances | 328 (16% spec'd rate) |
| `asyncio.sleep` in tests (non-helpers) | 9 occurrences |
| Wall-clock timing sleeps (non-trivial) | 5 (values > 0.01s) |
| Agent GDPR modules untested | 1 (`retention.py`) |

---

## Remediation Status vs Prior Audit

| Prior Finding | Status |
|--------------|--------|
| `fail_under` at 80% | FIXED — raised to 90% |
| Simulation engine no tests | FIXED — `tests/simulation/test_engine.py` exists with 20+ tests |
| Worker stubs no tests | FIXED — `tests/taskmining/test_worker.py`, `tests/monitoring/test_monitoring_worker.py` exist |
| Agent GDPR `purge.py` no tests | FIXED — `agent/python/tests/gdpr/test_purge.py` exists |
| Agent GDPR `audit_logger.py` no tests | FIXED — `agent/python/tests/gdpr/test_audit_logger.py` exists |
| Watermark extractor no tests | FIXED — `tests/security/test_watermark_extractor.py` exists |
| `re_encrypt_value` untested | FIXED — `tests/core/test_encryption.py` now has 9 tests including key rotation |
| Agent GDPR `retention.py` no tests | **STILL MISSING** |
| 40+ API routes no HTTP-layer tests | **PARTIALLY FIXED** — 7 routes still missing |
| Bare `MagicMock()` pattern | **ONGOING** — 1,733 instances |
| Timing-dependent asyncio.sleep | **PARTIALLY FIXED** — reduced to 9 occurrences, 5 non-trivial |

---

## Coverage Breakdown by Module

| Module | Test File Exists | Quality Assessment |
|--------|-----------------|-------------------|
| `src/core/auth.py` | Yes — `tests/core/test_auth.py` | EXCELLENT: covers password hash, JWT create/decode, expiry, blacklist, cookie auth |
| `src/api/routes/auth.py` | Yes — `tests/api/test_auth_routes.py` | GOOD: dev-mode blocked in prod, refresh with access token rejected, inactive user 401 |
| `src/api/routes/gdpr.py` | Yes — `tests/api/test_gdpr.py` | GOOD: export, erasure, consent lifecycle, invalid consent_type |
| `src/api/routes/assumptions.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/audit_logs.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/decisions.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/exports.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/micro_surveys.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/patterns.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/simulations.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/simulation/engine.py` | Yes — `tests/simulation/test_engine.py` | GOOD: 20+ tests, empty/single-node/what-if/capacity scenarios |
| `src/taskmining/worker.py` | Yes — `tests/taskmining/test_worker.py` | GOOD: stub dispatch, missing engagement_id, UUID validation |
| `src/monitoring/worker.py` | Yes — `tests/monitoring/test_monitoring_worker.py` | GOOD: detect/alert/collect/unknown paths |
| `src/security/watermark/extractor.py` | Yes — `tests/security/test_watermark_extractor.py` | GOOD |
| `src/core/encryption.py` | Yes — `tests/core/test_encryption.py` | GOOD: 9 tests including re_encrypt_value and key rotation fallback |
| `src/api/middleware/pep.py` | Yes — `tests/api/test_pep_middleware.py` | GOOD: permit/deny/mask/suppress via ASGI integration |
| `src/api/deps.py` | No dedicated test | LOW: covered implicitly by route tests |
| `agent/kmflow_agent/gdpr/audit_logger.py` | Yes — `agent/python/tests/gdpr/test_audit_logger.py` | GOOD |
| `agent/kmflow_agent/gdpr/purge.py` | Yes — `agent/python/tests/gdpr/test_purge.py` | GOOD |
| `agent/kmflow_agent/gdpr/retention.py` | None | MISSING — compliance-critical |
| `src/quality/instrumentation.py` | Yes — `tests/quality/test_instrumentation.py` | GOOD |

---

## Findings

### [HIGH] QUALITY: Pervasive bare `MagicMock()` without `spec=` across 195 test files

**File**: `/Users/proth/repos/kmflow/tests/pov/test_aggregation.py:65`, `/Users/proth/repos/kmflow/tests/conftest.py:78` (195 files total)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# tests/pov/test_aggregation.py:65
mock_result = MagicMock()
mock_scalars = MagicMock()
mock_unique = MagicMock()

# tests/conftest.py:78
mock_result = MagicMock()
session.add = MagicMock()
driver = MagicMock()
```
**Description**: 1,733 bare `MagicMock()` instances exist across 195 test files, compared to only 328 instances using `MagicMock(spec=...)` — a spec compliance rate of approximately 16%. Without `spec=`, MagicMock accepts any attribute access silently. If production code accesses a misspelled attribute or a field that was renamed during refactoring, the mock still returns a new MagicMock rather than raising `AttributeError`, causing the test to pass while testing nothing. The central `tests/conftest.py` fixtures that are reused across the entire test suite (`mock_result`, `driver`, `mock_pipe`) are all unspec'd, amplifying the impact.

**Risk**: Attribute-access typos in production code go undetected. Schema refactoring (renaming fields in Pydantic models or ORM classes) will not break mock-based tests. The false-passing rate is structurally highest in POV, TOM, and core tests — exactly the domain logic modules where correctness matters most.

**Recommendation**: Prioritize adding `spec=` to fixtures in `tests/conftest.py` first (highest reuse impact). Then work module by module. Use `MagicMock(spec=ClassName)` where the class is importable, or `create_autospec(instance)` for complex objects. Add a `ruff` custom rule or pre-commit hook checking for bare `MagicMock()` in test files.

---

### [HIGH] MISSING COVERAGE: 7 API route modules have no dedicated test file

**File**: `/Users/proth/repos/kmflow/src/api/routes/assumptions.py`, `audit_logs.py`, `decisions.py`, `exports.py`, `micro_surveys.py`, `patterns.py`, `simulations.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
MISSING dedicated test file: src/api/routes/assumptions.py
MISSING dedicated test file: src/api/routes/audit_logs.py
MISSING dedicated test file: src/api/routes/decisions.py
MISSING dedicated test file: src/api/routes/exports.py
MISSING dedicated test file: src/api/routes/micro_surveys.py
MISSING dedicated test file: src/api/routes/patterns.py
MISSING dedicated test file: src/api/routes/simulations.py
```
**Description**: Seven route modules under `src/api/routes/` have no dedicated `test_<route>.py` file in `tests/api/`. Some are covered by adjacent BDD service tests or overlapping route tests (e.g., `audit_logs` is touched in `test_audit_logging_bdd.py`), but the HTTP transport layer — URL matching, request body validation, authentication enforcement, error response format — is not verified for these routes. For `simulations.py` and `exports.py` in particular, the route files define POST/GET endpoints that are security-sensitive (data exports should enforce auth).

**Risk**: Route-level bugs including wrong HTTP status codes, missing auth guards on specific verbs, incorrect URL parameters, and schema validation gaps are not caught by service-layer BDD tests that bypass the FastAPI routing stack entirely.

**Recommendation**: Create `tests/api/test_<route>_routes.py` for each missing route. Minimum coverage: unauthenticated request returns 401, happy-path GET/POST returns expected status code, malformed body returns 422. The pattern used in `tests/api/test_pipeline_quality_routes.py` (using `ASGITransport` with mocked deps) is a good template.

---

### [HIGH] MISSING COVERAGE: Agent GDPR `retention.py` has no test file

**File**: `/Users/proth/repos/kmflow/agent/python/kmflow_agent/gdpr/retention.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
agent/python/kmflow_agent/gdpr/
  audit_logger.py  ← has test (test_audit_logger.py)
  purge.py         ← has test (test_purge.py)
  retention.py     ← NO TEST FILE
```
**Description**: The agent's GDPR module contains three files. `audit_logger.py` and `purge.py` gained tests in the recent remediation batch, but `retention.py` — which enforces GDPR data retention schedules on the local SQLite event buffer — remains untested. Retention enforcement is compliance-critical: a bug that silently fails to delete data past its retention period constitutes a GDPR Art. 5(1)(e) storage limitation violation.

**Risk**: GDPR data retention failures are silent. A logic error in the retention date calculation or the deletion predicate could retain data indefinitely without any test exposing it. Given that `purge.py` now has tests using `tmp_path`, the pattern is established and adding `retention.py` tests is low-effort.

**Recommendation**: Create `agent/python/tests/gdpr/test_retention.py` following the pattern of `test_purge.py`. Test: records past retention age are deleted, records within retention window are kept, empty database returns 0, retention calculation uses correct timezone handling.

---

### [MEDIUM] FLAKY: Wall-clock `asyncio.sleep` assertions in worker dispatch tests

**File**: `/Users/proth/repos/kmflow/tests/core/test_worker_dispatch.py:311`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# test_worker_dispatch.py:311
async def stop_after_start() -> None:
    await asyncio.sleep(0.05)
    shutdown.set()

# test_worker_dispatch.py:332
task = asyncio.create_task(run_task_worker(...))
await asyncio.sleep(0.02)
task.cancel()

# test_worker_dispatch.py:388
await asyncio.sleep(0.15)
```
**Description**: Three tests in `test_worker_dispatch.py` use hardcoded wall-clock sleep durations (0.02s, 0.05s, 0.15s) as timing gates for async state transitions. The 0.15s sleep on line 388 is used to allow a "retry after backoff" assertion — meaning the test assumes the error + retry cycle completes within 150ms. Under CI load, slow VMs, or test parallelism, this window is insufficient.

**Risk**: Intermittent CI failures on slow runners erode trust in the test suite and lead to test suppression, which removes regression protection from the worker dispatch path. The 0.02s sleep before `task.cancel()` is particularly fragile — if the task has not yet started processing when cancel fires, the test behavior is nondeterministic.

**Recommendation**: Replace wall-clock waits with event-driven synchronization: inject an `asyncio.Event` into the worker that signals when each state transition completes, then `await asyncio.wait_for(event.wait(), timeout=10)` in the test. The `asyncio.sleep(0)` yield-to-event-loop pattern used in `test_async_task_bdd.py` and `test_audit_logging_bdd.py` is correct and should be preserved.

---

### [MEDIUM] QUALITY: Test/source file ratio below 80% indicates structural coverage gaps

**File**: `/Users/proth/repos/kmflow/` (aggregate metric)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
Source files (non-init): 421
Test files (main suite): 332
Test/source ratio: 78.9%

Route files: 77
Route test files: ~70 (matching by name)
Route coverage: ~91%
```
**Description**: At 78.9%, the test-to-source file ratio has not kept pace with recent source additions. New route files (`pipeline_quality.py`, `apex_clearing.py`, `charles_river.py`, etc.) were added along with test files, but the 7 missing route test files and the unpaired source modules in `src/integrations/` (new `apex_clearing.py` and `charles_river.py` have untracked test files not yet committed) create a gap. The `tests/quality/` and `tests/evaluation/` directories contain tests for newly added source modules but are not yet committed, meaning they are not counted in CI coverage runs.

**Risk**: Untracked test files (`tests/quality/`, `tests/evaluation/`, `tests/integrations/test_apex_clearing.py`, `tests/integrations/test_charles_river.py`) are not included in pytest runs until committed, leaving corresponding source modules uncovered in CI.

**Recommendation**: Commit untracked test files in `tests/quality/`, `tests/evaluation/`, and `tests/integrations/` to include them in CI coverage measurements. Review all new source modules added in the last sprint for matching test file existence.

---

### [LOW] QUALITY: `src/api/deps.py` has no dedicated test

**File**: `/Users/proth/repos/kmflow/src/api/deps.py:14`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session
```
**Description**: `src/api/deps.py` is the canonical database session dependency used by all 77 route files. It has no dedicated test. The `AttributeError` path (missing `db_session_factory` in app state) and the session-cleanup-on-exception path are both untested. These scenarios can occur during application misconfiguration or startup races.

**Risk**: Low — route-level tests implicitly exercise the session dependency. However, the error path (session cleanup when a route raises) is not tested and could cause transaction leaks under error conditions.

**Recommendation**: Add `tests/api/test_deps.py` verifying: normal session yield and cleanup, `AttributeError` when state missing, session closed even when route raises.

---

## Lessons Learned Checklist

| Category | Count | Threshold | Status |
|----------|-------|-----------|--------|
| Bare `MagicMock()` without `spec=` | 1,733 | 0 ideal | FAIL |
| `asyncio.sleep` in test assertions (non-trivial) | 5 | 0 ideal | WARNING |
| Missing test files for route modules | 7 | 0 ideal | FAIL |

---

## Risk Assessment

| Risk Area | Current State | Severity |
|-----------|--------------|----------|
| Bare `MagicMock()` without `spec=` (1,733 instances) | Active — attribute typos pass silently | HIGH |
| 7 API route modules without dedicated test files | Active | HIGH |
| Agent GDPR `retention.py` untested | Active | HIGH |
| Wall-clock `asyncio.sleep` in worker dispatch tests | Active — 5 non-trivial sleeps | MEDIUM |
| Untracked test files not counted in CI | Active — 9 test dirs/files pending commit | MEDIUM |
| `src/api/deps.py` corner cases untested | Low risk | LOW |

---

## Recommendations Summary

1. **Immediate**: Commit untracked test files (`tests/quality/`, `tests/evaluation/`, `tests/integrations/test_apex_clearing.py`, `tests/integrations/test_charles_river.py`, `agent/python/tests/ipc/`, `agent/python/tests/upload/`) so they are included in CI coverage.
2. **Short-term**: Create `agent/python/tests/gdpr/test_retention.py` — the `test_purge.py` pattern with `tmp_path` is directly reusable.
3. **Short-term**: Create dedicated HTTP-layer test files for the 7 missing route modules. Use `tests/api/test_pipeline_quality_routes.py` as the template.
4. **Medium-term**: Systematically replace bare `MagicMock()` in `tests/conftest.py` with `MagicMock(spec=ClassName)` — this single file change propagates benefit to the entire test suite.
5. **Medium-term**: Replace wall-clock `asyncio.sleep` assertions in `test_worker_dispatch.py` with event-driven synchronization using injected `asyncio.Event` objects.
6. **Ongoing**: Enforce `MagicMock(spec=ClassName)` pattern in code review. Target spec-compliance rate of >80% (currently 16%).
