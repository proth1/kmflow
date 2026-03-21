# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-03-20
**Cycle**: 7
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: WARNING (90-94% estimated — not BLOCKED, but improvements required)**

The KMFlow backend test suite now comprises 333 test files (main suite) and 15 agent test files covering 421 non-init source modules (79.1% file-coverage ratio). The `fail_under` threshold is correctly set to **90%** in `pyproject.toml`. Cycle 7 audit confirms one HIGH finding from the prior cycle was remediated: `agent/python/tests/test_retention.py` now exists and covers GDPR data retention enforcement with 13 test cases.

The primary remaining concerns are: (1) **1,728 bare `MagicMock()` instances without `spec=`** across 196 test files — effectively unchanged from cycle 6; (2) **7 API route modules with no dedicated test file** (`assumptions`, `audit_logs`, `decisions`, `exports`, `micro_surveys`, `patterns`, `simulations`) — unchanged; (3) **11 untracked test files not yet committed** meaning those source modules remain uncovered in CI; (4) **wall-clock `asyncio.sleep` assertions** remain in `test_worker_dispatch.py`.

| Metric | Value |
|--------|-------|
| Source files (non-init, src/) | 421 |
| Test files (main suite, committed) | 333 |
| Test files (agent, committed) | 13 |
| Untracked test files (not in CI) | 11 |
| Test/source file ratio (committed) | 79.1% |
| `fail_under` configured | 90% (CORRECT) |
| Route files in src/api/routes/ | 77 |
| Route files with no dedicated test | 7 |
| Bare `MagicMock()` instances | 1,728 across 196 files |
| `MagicMock(spec=...)` instances | 329 (16% spec'd rate) |
| `asyncio.sleep` in tests (non-helpers) | 9 occurrences |
| Wall-clock timing sleeps (non-trivial) | 5 (values > 0.01s) |
| Agent GDPR modules untested | 0 (FIXED this cycle) |

---

## Remediation Status vs Prior Cycle

| Prior Finding | Status |
|--------------|--------|
| `fail_under` at 80% | FIXED — raised to 90% |
| Simulation engine no tests | FIXED — `tests/simulation/test_engine.py` exists |
| Worker stubs no tests | FIXED — `tests/taskmining/test_worker.py`, `tests/monitoring/test_monitoring_worker.py` exist |
| Agent GDPR `purge.py` no tests | FIXED — `agent/python/tests/gdpr/test_purge.py` exists |
| Agent GDPR `audit_logger.py` no tests | FIXED — `agent/python/tests/gdpr/test_audit_logger.py` exists |
| Watermark extractor no tests | FIXED — `tests/security/test_watermark_extractor.py` exists |
| `re_encrypt_value` untested | FIXED — `tests/core/test_encryption.py` covers key rotation |
| Agent GDPR `retention.py` no tests | **FIXED** — `agent/python/tests/test_retention.py` now exists (13 test cases) |
| 7 API routes no HTTP-layer tests | **ONGOING** — 7 routes still missing (assumptions, audit_logs, decisions, exports, micro_surveys, patterns, simulations) |
| Bare `MagicMock()` pattern | **ONGOING** — 1,728 instances (marginal decrease of 5) |
| Timing-dependent asyncio.sleep | **ONGOING** — 5 non-trivial wall-clock sleeps remain |
| Untracked test files not in CI | **ONGOING** — 11 untracked test files/dirs |

---

## Coverage Breakdown by Module

| Module | Test File Exists | Quality Assessment |
|--------|-----------------|-------------------|
| `src/core/auth.py` | Yes — `tests/core/test_auth.py` | EXCELLENT: JWT create/decode, expiry, blacklist, cookie auth |
| `src/api/routes/auth.py` | Yes — `tests/api/test_auth_routes.py` | GOOD: dev-mode blocked in prod, refresh rejected, inactive user 401 |
| `src/api/routes/gdpr.py` | Yes — `tests/api/test_gdpr.py` | GOOD: export, erasure, consent lifecycle |
| `src/api/routes/assumptions.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/audit_logs.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/decisions.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/exports.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/micro_surveys.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/patterns.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/api/routes/simulations.py` | None — covered indirectly | MEDIUM: no dedicated HTTP-layer test |
| `src/simulation/engine.py` | Yes — `tests/simulation/test_engine.py` | GOOD: empty/single-node/what-if/capacity scenarios |
| `src/taskmining/worker.py` | Yes — `tests/taskmining/test_worker.py` | GOOD |
| `src/monitoring/worker.py` | Yes — `tests/monitoring/test_monitoring_worker.py` | GOOD |
| `src/security/watermark/extractor.py` | Yes — `tests/security/test_watermark_extractor.py` | GOOD |
| `src/core/encryption.py` | Yes — `tests/core/test_encryption.py` | GOOD: includes re_encrypt_value and key rotation fallback |
| `src/api/middleware/pep.py` | Yes — `tests/api/test_pep_middleware.py` | GOOD: permit/deny/mask/suppress via ASGI |
| `src/api/deps.py` | No dedicated test | LOW: covered implicitly by route tests |
| `agent/kmflow_agent/gdpr/audit_logger.py` | Yes — `agent/python/tests/gdpr/test_audit_logger.py` | GOOD |
| `agent/kmflow_agent/gdpr/purge.py` | Yes — `agent/python/tests/gdpr/test_purge.py` | GOOD |
| `agent/kmflow_agent/gdpr/retention.py` | Yes — `agent/python/tests/test_retention.py` | GOOD: 13 tests, deletion, preservation, audit callback, async run/shutdown |
| `src/quality/instrumentation.py` | Yes — `tests/quality/test_instrumentation.py` (untracked) | PENDING COMMIT |

---

## Findings

### [HIGH] QUALITY: Pervasive bare `MagicMock()` without `spec=` across 196 test files

**File**: `/Users/proth/repos/kmflow/tests/pov/test_aggregation.py:65`, `/Users/proth/repos/kmflow/tests/conftest.py:78` (196 files total)
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

# Top offenders by count:
# tests/core/test_reports.py: 74 bare instances
# tests/api/test_persona_dashboards_bdd.py: 54 bare instances
# tests/api/test_scenario_comparison_bdd.py: 37 bare instances
# tests/tom/test_best_practice_matcher.py: 35 bare instances
# tests/api/test_governance.py: 35 bare instances
```
**Description**: 1,728 bare `MagicMock()` instances exist across 196 test files, compared to only 329 instances using `MagicMock(spec=...)` — a spec compliance rate of approximately 16%. Without `spec=`, MagicMock accepts any attribute access silently. If production code accesses a misspelled or renamed attribute, the mock returns a new MagicMock rather than raising `AttributeError`, causing the test to pass while testing nothing. The central `tests/conftest.py` fixtures reused across the entire test suite are all unspec'd, amplifying the impact.

**Risk**: Attribute-access typos in production code go undetected. Schema refactoring (renaming fields in Pydantic models or ORM classes) does not break mock-based tests. The false-passing rate is structurally highest in POV, TOM, and core tests — the domain logic modules where correctness is most critical.

**Recommendation**: Prioritize adding `spec=` to fixtures in `tests/conftest.py` first (highest reuse impact). Then address top offenders (`test_reports.py`, `test_persona_dashboards_bdd.py`). Use `MagicMock(spec=ClassName)` or `create_autospec(instance)`. Add a pre-commit check for bare `MagicMock()` in test files.

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
**Description**: Seven route modules under `src/api/routes/` have no dedicated test file in `tests/api/`. BDD service tests may touch some logic, but the HTTP transport layer — URL matching, request body validation, authentication enforcement, HTTP status codes — is not verified for these routes. `exports.py` and `simulations.py` are security-sensitive (data export should enforce auth).

**Risk**: Route-level bugs including wrong HTTP status codes, missing auth guards, incorrect URL parameters, and schema validation gaps are not caught by service-layer BDD tests that bypass FastAPI routing entirely.

**Recommendation**: Create `tests/api/test_<route>_routes.py` for each. Minimum: unauthenticated request returns 401, happy-path returns expected status, malformed body returns 422. Use `tests/api/test_pipeline_quality_routes.py` as the template.

---

### [MEDIUM] FLAKY: Wall-clock `asyncio.sleep` assertions in worker dispatch tests

**File**: `/Users/proth/repos/kmflow/tests/core/test_worker_dispatch.py:311,332,388`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# test_worker_dispatch.py:311 — gate for shutdown signal
async def stop_after_start() -> None:
    await asyncio.sleep(0.05)
    shutdown.set()

# test_worker_dispatch.py:332 — gate before task.cancel()
await asyncio.sleep(0.02)
task.cancel()

# test_worker_dispatch.py:388 — gate for retry-after-backoff assertion
await asyncio.sleep(0.15)
```
**Description**: Three tests use hardcoded wall-clock sleeps (0.02s, 0.05s, 0.15s) as timing gates for async state transitions. The 0.15s sleep asserts that an error+retry cycle completes within 150ms. Under CI load or test parallelism this window is insufficient. The 0.02s sleep before `task.cancel()` is particularly fragile — if the task has not yet started processing when cancel fires, test behavior is nondeterministic.

**Risk**: Intermittent CI failures on slow runners erode trust in the test suite and lead to test suppression, removing regression protection from the worker dispatch path.

**Recommendation**: Replace wall-clock waits with event-driven synchronization: inject an `asyncio.Event` that signals state transitions, then `await asyncio.wait_for(event.wait(), timeout=10)`. Preserve the `asyncio.sleep(0)` yield-to-event-loop pattern used correctly in `test_async_task_bdd.py:75` and `test_audit_logging_bdd.py:681`.

---

### [MEDIUM] QUALITY: 11 untracked test files not counted in CI coverage

**File**: Multiple (see evidence)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
?? agent/python/tests/ipc/test_socket_server.py
?? agent/python/tests/test_auth.py
?? agent/python/tests/upload/test_batch_uploader.py
?? tests/api/test_pipeline_quality_routes.py
?? tests/evaluation/test_entity_evaluator.py
?? tests/evaluation/test_golden_dataset.py
?? tests/evaluation/test_graph_health.py
?? tests/evaluation/test_rag_evaluator.py
?? tests/evaluation/test_retrieval_evaluator.py
?? tests/evidence/parsers/test_financial_regulatory_parser.py
?? tests/integrations/test_apex_clearing.py
?? tests/integrations/test_charles_river.py
?? tests/quality/test_instrumentation.py
?? tests/quality/test_metrics_collector.py
```
**Description**: 14 test files across 5 areas are untracked in git and therefore excluded from CI coverage runs. Corresponding source modules (`src/quality/`, `src/integrations/apex_clearing.py`, `src/integrations/charles_river.py`, agent IPC, agent upload) have no coverage in CI until these files are committed.

**Risk**: CI coverage measurement underreports the true state. New source modules added without committing their tests create a misleading picture of 90% coverage — the actual denominator is incomplete.

**Recommendation**: Commit all untracked test files. This is a single `git add` + commit operation with no source code changes required.

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
**Description**: `src/api/deps.py` is the canonical database session dependency for all 77 route files. The `AttributeError` path (missing `db_session_factory`) and session-cleanup-on-exception path are untested. These can occur during startup races or misconfiguration.

**Risk**: Low — route-level tests implicitly exercise the happy path. Error paths could cause transaction leaks.

**Recommendation**: Add `tests/api/test_deps.py`: normal session yield and cleanup, `AttributeError` when state missing, session closed even when route raises.

---

## Lessons Learned Checklist

| Category | Count | Threshold | Status |
|----------|-------|-----------|--------|
| Bare `MagicMock()` without `spec=` | 1,728 | 0 ideal | FAIL |
| `asyncio.sleep` in test assertions (non-trivial) | 5 | 0 ideal | WARNING |
| Missing test files for route modules | 7 | 0 ideal | FAIL |
| Agent GDPR `retention.py` untested | 0 | 0 | PASS (FIXED) |

---

## Risk Assessment

| Risk Area | Current State | Severity |
|-----------|--------------|----------|
| Bare `MagicMock()` without `spec=` (1,728 instances) | Active — attribute typos pass silently | HIGH |
| 7 API route modules without dedicated test files | Active | HIGH |
| 14 untracked test files not counted in CI | Active | MEDIUM |
| Wall-clock `asyncio.sleep` in worker dispatch tests | Active — 5 non-trivial sleeps | MEDIUM |
| `src/api/deps.py` corner cases untested | Low risk | LOW |

---

## Recommendations Summary

1. **Immediate**: Commit all 14 untracked test files so CI coverage is accurate.
2. **Short-term**: Create dedicated HTTP-layer test files for the 7 missing route modules. Use `/Users/proth/repos/kmflow/tests/api/test_pipeline_quality_routes.py` as template.
3. **Medium-term**: Replace bare `MagicMock()` in `tests/conftest.py` with `MagicMock(spec=ClassName)` — single-file change with suite-wide impact.
4. **Medium-term**: Replace wall-clock `asyncio.sleep` in `test_worker_dispatch.py` with event-driven synchronization.
5. **Ongoing**: Enforce `MagicMock(spec=ClassName)` in code review. Target spec-compliance rate >80% (currently 16%).
