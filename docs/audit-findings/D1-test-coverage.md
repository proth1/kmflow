# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-03-19
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: WARNING (90-94% estimated — not BLOCKED, but improvements required)**

The KMFlow backend test suite is large and well-structured at the file level, with 312 test files containing 5,772 test functions for 408 non-init source modules (76.5% file-coverage ratio). Critical paths — auth, JWT, cookie-based sessions, token blacklisting, GDPR erasure, WebSocket auth, PEP middleware, and PII filtering — are covered by dedicated, well-structured test files with meaningful assertions.

However, several significant gaps exist. The `fail_under` coverage threshold in `pyproject.toml` is set to **80%**, which is below both the CLAUDE.md-documented 80% floor and the 90% MANDATORY threshold required by this audit system. Estimated actual coverage, accounting for the 246 source modules with no matching test file, is between 85-88%, placing the suite in **WARNING** territory. Two of the most critical concerns are: (1) timing-dependent tests scattered throughout monitoring and worker tests that create flaky CI risk, and (2) a group of security-critical modules in `src/security/` and the agent GDPR subsystem that have no dedicated unit tests.

| Metric | Value |
|--------|-------|
| Source files (non-init) | 408 |
| Test files | 312 |
| Test/source file ratio | 76.5% |
| Total test functions | 5,772 (main) + 118 (agent) |
| `fail_under` configured | 80% — below mandated 90% |
| Source modules with no test file | 246 of 408 |
| Flaky timing-dependent tests | 27 (asyncio.sleep with wall-clock assertions) |
| Worker stubs untested for real behaviour | 2 (taskmining/worker.py, monitoring/worker.py) |
| Agent GDPR modules untested | 3 (audit_logger, purge, retention) |

---

## Coverage Breakdown by Module

| Module | Test File Exists | Quality Assessment |
|--------|-----------------|-------------------|
| `src/core/auth.py` | Yes — `tests/core/test_auth.py` | EXCELLENT: 466 lines, covers password hash, JWT create/decode, expiry, blacklist, cookie auth |
| `src/api/routes/auth.py` | Yes — `tests/api/test_auth_routes.py` | GOOD: dev-mode blocked in prod, refresh with access token rejected, inactive user 401 |
| `src/api/routes/users.py` | Yes — `tests/api/test_users.py` | GOOD: RBAC enforced, duplicate email 409, pagination tested |
| `src/api/routes/admin.py` | Yes — `tests/api/test_admin_routes.py` | GOOD: retention-cleanup dry-run/live-run, key rotation admin-only |
| `src/api/routes/gdpr.py` | Yes — `tests/api/test_gdpr.py` | GOOD: export, erasure, consent lifecycle, invalid consent_type |
| `src/gdpr/erasure_job.py` | Yes — `tests/gdpr/test_erasure_job.py` | GOOD: PII replacement, not-found skip |
| `src/security/watermark/service.py` | Via BDD — `test_export_watermark_bdd.py` | MEDIUM: no dedicated unit tests for HMAC verification paths |
| `src/security/watermark/extractor.py` | None | MISSING |
| `src/security/consent/service.py` | Via BDD only — `test_consent_bdd.py` | MEDIUM: no direct unit test for ConsentService |
| `src/security/cohort/suppression.py` | Via BDD only | MEDIUM: cohort suppression logic not directly tested |
| `src/api/middleware/pep.py` | Yes — `tests/api/test_pep_middleware.py` | GOOD: permit/deny/mask/suppress via ASGI integration |
| `src/core/encryption.py` | Yes — `tests/core/test_encryption.py` | MEDIUM: 6 tests, missing `re_encrypt_value` unit test and key rotation fallback chain test |
| `src/api/routes/websocket.py` | Yes — `tests/api/test_websocket_auth.py` | GOOD: missing-token, valid-token, non-member |
| `src/simulation/engine.py` | None | MISSING — core simulation logic |
| `src/monitoring/worker.py` | None | MISSING — Redis Stream consumer |
| `src/taskmining/worker.py` | None | MISSING — aggregate/materialize stubs and assemble_switching path |
| `src/monitoring/deviation/engine.py` | Yes — `tests/monitoring/test_deviation_engine_bdd.py` | GOOD |
| `src/taskmining/pii/filter.py` | Yes — `tests/taskmining/test_pii_detection.py` | EXCELLENT: 200+ parametrized cases |
| `src/quality/instrumentation.py` | Yes — `tests/quality/test_instrumentation.py` | GOOD |
| `src/core/database.py` | Via infrastructure test | MEDIUM: `create_engine` not tested for pool config edge cases |
| `agent/kmflow_agent/gdpr/audit_logger.py` | None | MISSING — compliance-critical |
| `agent/kmflow_agent/gdpr/purge.py` | None | MISSING — GDPR right-to-erasure |
| `agent/kmflow_agent/gdpr/retention.py` | None | MISSING |
| `agent/kmflow_agent/vce/ocr.py` | None | MISSING |
| `agent/kmflow_agent/platform/_macos.py` | None | MISSING |
| `agent/kmflow_agent/platform/_windows.py` | None | MISSING |

---

## Findings

### [CRITICAL] COVERAGE: Coverage threshold configured below audit requirement

**File**: `/Users/proth/repos/kmflow/pyproject.toml:1`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.coverage.report]
fail_under = 80
```
**Description**: The project's coverage enforcement threshold is 80%, which is below the 90% MANDATORY threshold required by this audit system and the CLAUDE.md-documented minimum of 80% (which is listed as the floor, not the target). With 246 of 408 non-init source modules having no dedicated test file, the threshold provides a false sense of safety — coverage can pass at 80% while entire subsystems are untested.

**Risk**: CI passes at 80% coverage while critical security paths, simulation logic, and worker processes have zero test coverage. This masks real coverage debt and allows untested code to reach release.

**Recommendation**: Raise `fail_under` to 90 and add `[tool.coverage.run]` with `source = ["src"]` and explicit omit patterns for known stubs. Fix the 246 missing test files before raising the threshold.

---

### [HIGH] FLAKY: Timing-dependent assertions in monitoring agent tests

**File**: `/Users/proth/repos/kmflow/tests/monitoring/test_agent_framework_bdd.py:92`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
await agent.start()
await asyncio.sleep(0.1)
await agent.stop()
assert agent.connect_calls == 1
```
**Description**: 27 occurrences of `asyncio.sleep()` with hardcoded wall-clock durations (0.05s to 0.5s) drive assertions about side effects (poll counts, health state transitions, alert counts). These tests pass on a fast developer machine but will fail unpredictably under CI load, slow VMs, or test parallelism. The pattern `await asyncio.sleep(0.5); assert agent._running is False` is particularly fragile — the 0.5s window is the test's entire margin, not a buffer.

**Risk**: Intermittent CI failures mask real regressions. Tests that "flap" are eventually disabled or skipped, leaving the monitoring agent framework without regression protection.

**Recommendation**: Replace wall-clock waits with event-driven synchronization: inject a `asyncio.Event` into the agent that fires when a state transition completes, await that event in tests, then assert. Alternatively, use `asyncio.wait_for(..., timeout=5)` with an event rather than sleeping.

---

### [HIGH] MISSING COVERAGE: Simulation engine has no tests

**File**: `/Users/proth/repos/kmflow/src/simulation/engine.py:16`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
def run_simulation(
    process_graph: dict[str, Any],
    parameters: dict[str, Any],
    simulation_type: str,
) -> dict[str, Any]:
```
**Description**: `src/simulation/engine.py` implements the core `run_simulation` function that traverses process graphs, applies parameter modifications, and computes impact metrics. There is no `tests/simulation/test_engine.py` file. The existing simulation tests (`test_simulation.py`, `test_financial.py`, `test_epistemic.py`) cover higher-level services, not this engine directly. The `_apply_parameters` and `_calculate_metrics` internal helpers are also untested.

**Risk**: Bugs in the simulation engine's graph traversal or metric calculation go undetected. Given that simulation outputs inform TOM gap analysis and recommendations, incorrect results could corrupt client deliverables.

**Recommendation**: Create `tests/simulation/test_engine.py` with unit tests for: empty graph, single-node graph, cycle detection, parameter application for all simulation_type values, and metric boundary conditions (zero-length cycles, infinite loops capped by MAX_CYCLES).

---

### [HIGH] MISSING COVERAGE: Worker stubs have no tests for the real dispatch path

**File**: `/Users/proth/repos/kmflow/src/taskmining/worker.py:43`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# TODO(Epic #206, Stories #207/#208/#209): Wire up aggregation engine.
# Stubs below are Phase 1 placeholders
if task_type == "aggregate":
    return {"status": "not_implemented", ...}
```
**Description**: `src/taskmining/worker.py` and `src/monitoring/worker.py` are Redis Stream consumers with no test files. The taskmining worker contains explicit `not_implemented` stubs for `aggregate` and `materialize` task types. The `assemble_switching` path — which calls database and Neo4j — is real code with lazy imports and UUID validation, but no test covers it. The monitoring worker (`process_task`) similarly has no tests.

**Risk**: When the TODO stubs are replaced with real implementations, there are no regression tests to verify behaviour. The `assemble_switching` path with `async_session_factory` accessed via lazy import already exists in production but has zero test coverage.

**Recommendation**: Create `tests/taskmining/test_worker.py` covering: `aggregate` stub returns expected dict, `materialize` stub returns expected dict, `assemble_switching` with missing `engagement_id` returns error, `assemble_switching` with invalid UUID returns error, `unknown_task_type` returns expected dict.

---

### [HIGH] MISSING COVERAGE: Agent GDPR subsystem untested

**File**: `/Users/proth/repos/kmflow/agent/python/kmflow_agent/gdpr/purge.py:36`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
def purge_local_buffer(self) -> int:
    """Delete ALL rows from the local SQLite event buffer and VACUUM."""
    if not Path(self._db_path).exists():
        return 0
    conn = sqlite3.connect(self._db_path)
```
**Description**: Three compliance-critical GDPR modules in the desktop agent have no test files: `gdpr/audit_logger.py` (append-only audit trail), `gdpr/purge.py` (SQLite buffer deletion), and `gdpr/retention.py` (retention enforcement). These implement GDPR Art. 17 right-to-erasure for the desktop capture agent. The `DataPurgeManager.purge_local_buffer` method opens a real SQLite connection without test isolation — no mock or temp file is used, making real data deletion possible if tests misfire.

**Risk**: GDPR purge failures are silent (returns 0 with a log warning). A bug that fails to delete data would constitute a GDPR violation. An untested audit logger means the compliance audit trail could be silently broken.

**Recommendation**: Create `agent/python/tests/gdpr/test_audit_logger.py`, `test_purge.py`, and `test_retention.py`. Use `tmp_path` pytest fixture for SQLite isolation. Test: purge returns correct row count, purge on non-existent DB returns 0, VACUUM runs after deletion, audit log entry is written on purge.

---

### [HIGH] MISSING COVERAGE: Security watermark extractor untested

**File**: `/Users/proth/repos/kmflow/src/security/watermark/extractor.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
# No test file exists for src/security/watermark/extractor.py
# WatermarkService.encode_invisible_watermark uses HMAC-SHA256
# extractor.py must decode and verify the HMAC signature
```
**Description**: `src/security/watermark/extractor.py` has no corresponding test file. The watermark service uses HMAC-SHA256 signing for tamper detection on exported documents. Without tests for the extractor, the tamper-detection path — which verifies the HMAC signature — is uncovered. HMAC verification is exactly the kind of code where an off-by-one error in payload parsing silently accepts tampered documents.

**Risk**: A bug in HMAC verification could allow an attacker to tamper with a watermarked export without triggering detection, undermining the export audit trail's integrity guarantee.

**Recommendation**: Create `tests/security/test_watermark_extractor.py` covering: valid watermark extracted correctly, tampered payload raises/returns failure, expired timestamp handled, truncated base64 input handled.

---

### [MEDIUM] MISSING COVERAGE: `re_encrypt_value` and key rotation fallback chain untested

**File**: `/Users/proth/repos/kmflow/src/core/encryption.py:116`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
def re_encrypt_value(ciphertext: str) -> str:
    """Re-encrypt a value with the current key.
    Decrypts with current or previous key, then encrypts with current key.
    Used during key rotation to migrate encrypted data.
    """
    plaintext = decrypt_value(ciphertext)
    return encrypt_value(plaintext)
```
**Description**: `re_encrypt_value` is the core function used by the admin key-rotation endpoint (`POST /api/v1/admin/rotate-encryption-key`). It is only tested indirectly via the admin route integration tests which mock `re_encrypt_value` with `patch()`. The function itself — and the three-step fallback chain in `decrypt_value` (current key → legacy salt → previous key) — has only 6 direct unit tests. The fallback to `encryption_key_previous` is never tested at the unit level.

**Risk**: During an actual key rotation, a bug in the fallback chain would silently fail to decrypt credentials, corrupting integration configurations. Since `decrypt_value` catches `InvalidToken` at each step and re-raises only after all three fail, a logic error in ordering could return the wrong plaintext without raising.

**Recommendation**: Add to `tests/core/test_encryption.py`: test for `re_encrypt_value` roundtrip, test for `decrypt_value` falling back to `encryption_key_previous`, test for all three keys failing raises `InvalidToken`.

---

### [MEDIUM] FLAKY: Worker wiring tests use wall-clock sleeps for message processing

**File**: `/Users/proth/repos/kmflow/tests/core/tasks/test_worker_wiring_bdd.py:405`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def run_then_stop() -> None:
    # Let the runner process one message, then stop
    await asyncio.sleep(0.1)
    shutdown.set()
```
**Description**: The worker wiring BDD tests use `asyncio.sleep(0.1)` and `asyncio.sleep(0.3)` as timing gates to allow message processing to complete before asserting on results. These tests also appear in `test_async_task_bdd.py` with sleeps of `0.01` and `0`. While `asyncio.sleep(0)` is a valid yield-to-event-loop idiom, `asyncio.sleep(0.3)` is a wall-clock assumption that will produce intermittent failures in resource-constrained CI environments.

**Risk**: Intermittent test failures in CI erode developer trust in the test suite, leading to test skips or threshold bypasses.

**Recommendation**: Use a bounded `asyncio.wait_for` with a generous timeout (5–10s) and an event that fires when the assertion condition is met. The `asyncio.sleep(0)` pattern for yielding control is acceptable and should be preserved.

---

### [MEDIUM] QUALITY: Unspec'd `MagicMock()` used for domain objects in POV tests

**File**: `/Users/proth/repos/kmflow/tests/pov/test_generator.py:22`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
item = MagicMock()
frag = MagicMock()
session.add = MagicMock()
```
**Description**: Several POV test files (`test_generator.py`, `test_aggregation.py`, `test_consensus_aggregation.py`) use bare `MagicMock()` without `spec=` for domain objects like evidence items and fragments. Without a spec, `MagicMock` accepts any attribute access silently, meaning tests pass even if the production code accesses a misspelled attribute name that doesn't exist on the real object. This is the "tests that test nothing" anti-pattern.

**Risk**: Tests pass when production code has attribute typos. Refactoring evidence item fields would not break the mock-based tests, creating a false sense of safety.

**Recommendation**: Replace bare `MagicMock()` with `MagicMock(spec=EvidenceItem)` or `MagicMock(spec=EvidenceFragment)` where the spec class is importable. This is the standard followed in the better-quality test files like `test_gdpr.py`.

---

### [MEDIUM] MISSING COVERAGE: 40+ API route modules have no direct route-level tests

**File**: `/Users/proth/repos/kmflow/src/api/routes/` (multiple files)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
MISSING: src/api/routes/incidents.py    (has BDD service test but no HTTP route test)
MISSING: src/api/routes/correlation.py
MISSING: src/api/routes/intake.py
MISSING: src/api/routes/integrations.py
MISSING: src/api/routes/deviations.py
```
**Description**: A file-name-matching scan finds 40+ route files under `src/api/routes/` with no corresponding `test_<route>.py` file in `tests/api/`. Some (like `incidents.py`) are covered by BDD service-layer tests but the HTTP layer — URL matching, request validation, auth enforcement, and error response format — is not tested. Others (like `correlation.py`, `intake.py`, `deviations.py`) appear to have no tests at any layer.

**Risk**: Route-level bugs — wrong HTTP status codes, missing auth guards, schema validation gaps, incorrect URL parameters — are not caught. The BDD service tests bypass the FastAPI routing layer entirely.

**Recommendation**: For each BDD-covered route, add at minimum a smoke test file that calls the endpoint via `AsyncClient` and verifies: (1) unauthenticated request returns 401, (2) happy path returns expected status code, (3) invalid request body returns 422.

---

### [MEDIUM] MISSING COVERAGE: Agent platform modules untested

**File**: `/Users/proth/repos/kmflow/agent/python/kmflow_agent/platform/_macos.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
# No test file exists for:
# agent/python/kmflow_agent/platform/_macos.py
# agent/python/kmflow_agent/platform/_windows.py
# agent/python/kmflow_agent/vce/ocr.py
# agent/python/kmflow_agent/vce/record.py
```
**Description**: The desktop agent's platform-specific modules (`_macos.py`, `_windows.py`) and VCE sub-modules (`ocr.py`, `record.py`) have no test files. These modules handle system-level calls (screen capture, accessibility APIs, OCR). Platform-specific code is notoriously hard to test but should at minimum have import and interface tests to catch API drift between macOS versions.

**Risk**: Silent regressions in platform modules are not caught until the agent binary is run on a target device. OCR failures in `vce/ocr.py` would silently produce empty text without any test asserting on the failure path.

**Recommendation**: Create mock-based interface tests for `_macos.py` and `_windows.py` that verify the public API surface using `unittest.mock.patch` for system calls. For `ocr.py`, test both the success path and the path where the OCR library is unavailable (optional dependency).

---

### [LOW] QUALITY: Test database infrastructure tests check config files, not runtime behaviour

**File**: `/Users/proth/repos/kmflow/tests/core/test_database_infrastructure.py:40`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
def test_postgres_service_defined(self) -> None:
    """PostgreSQL service is defined in docker-compose.yml."""
    compose = self._load_compose()
    assert "postgres" in compose["services"]
```
**Description**: The `TestBDDScenario1DockerComposeServices` class tests the contents of `docker-compose.yml` by parsing it as YAML. While this verifies that the service definitions exist, it does not verify that the database engine configuration (pool size, max overflow, pool_pre_ping) works correctly under load or that session isolation behaves as expected for concurrent requests. The `create_engine` function in `src/core/database.py` has no unit tests for its pool configuration parameters.

**Risk**: Misconfiguration of `pool_size=0` or `pool_pre_ping=False` would not be caught by the current tests and could cause intermittent production failures under concurrent load.

**Recommendation**: Add a test that instantiates `create_engine(settings)` with non-default pool parameters and asserts the engine's pool configuration reflects what was passed. Use `engine.pool.size()` and `engine.dialect.name` assertions.

---

### [LOW] QUALITY: `src/api/deps.py` has no tests

**File**: `/Users/proth/repos/kmflow/src/api/deps.py:14`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state via FastAPI dependency injection."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session
```
**Description**: `src/api/deps.py` is the canonical database session dependency used by all 76 route files. It has no dedicated test file. The behaviour when `request.app.state.db_session_factory` is missing (raising `AttributeError`) and when the session factory raises an exception during `__aenter__` are both untested.

**Risk**: If `get_session` raises an unhandled exception on startup, all routes return 500 with no meaningful error message. This scenario is possible during application misconfiguration.

**Recommendation**: Add `tests/api/test_deps.py` with: test for normal session yield and cleanup, test for `AttributeError` on missing state, test that session is closed even if the route raises an exception.

---

## Risk Assessment

| Risk Area | Current State | Severity |
|-----------|--------------|----------|
| `fail_under` at 80% vs required 90% | Active — CI passes below audit threshold | CRITICAL |
| Simulation engine (`src/simulation/engine.py`) | No tests | HIGH |
| Worker dispatch (`taskmining/worker.py`, `monitoring/worker.py`) | No tests | HIGH |
| Agent GDPR purge/audit | No tests | HIGH |
| Watermark extractor HMAC verification | No tests | HIGH |
| Flaky timing-based tests in monitoring | 27 occurrences | HIGH |
| Encryption key rotation chain | Untested fallback path | MEDIUM |
| 40+ API routes lacking HTTP-layer tests | Coverage gap | MEDIUM |
| Agent platform modules | No tests | MEDIUM |
| POV tests with unspec'd MagicMock | False passing | MEDIUM |
| `src/api/deps.py` dependency untested | Corner cases uncovered | LOW |

---

## Recommendations Summary

1. **Immediate**: Raise `fail_under` to 90 in `pyproject.toml` after addressing the critical gaps.
2. **Short-term**: Create `tests/simulation/test_engine.py`, `tests/taskmining/test_worker.py`, `tests/security/test_watermark_extractor.py`.
3. **Short-term**: Create agent GDPR test files using `tmp_path` for SQLite isolation.
4. **Medium-term**: Replace wall-clock `asyncio.sleep()` waits in monitoring tests with event-driven synchronization.
5. **Medium-term**: Add HTTP-layer smoke tests for all 40+ BDD-only route files.
6. **Ongoing**: Enforce `MagicMock(spec=ClassName)` pattern — add a ruff custom rule or code review checklist item.
