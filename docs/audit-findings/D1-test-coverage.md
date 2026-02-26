# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-02-26
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: CRITICAL — BLOCKED**

The KMFlow backend test suite reports **84% overall line coverage** across 7,765 statements. However, this headline figure masks severe gaps in security-critical and infrastructure modules. Eight source files have 0% coverage, the monitoring subsystem runs at 61.8%, and several complete functional areas (evidence deduplication, audit logging, per-user rate limiting) have no tests at all. The frontend has 99 source files with only 13 unit test files covering components.

| Metric | Value |
|--------|-------|
| Overall backend line coverage | 84.0% (6,521 / 7,765 statements) |
| Backend test files | 132 |
| Backend source files (non-init) | 181 |
| Frontend source files | 99 |
| Frontend unit test files | 13 |
| Files with 0% coverage | 8 confirmed zero-coverage modules |
| Minimum threshold (CLAUDE.md) | 80% line coverage |
| Threshold met | YES (84% > 80%) — but critical path gaps remain |

**Threshold Note**: The 84% aggregate clears the 80% floor set in CLAUDE.md. However, the coverage threshold gates in the SDLC (`coverage_above_80`) do not substitute for the critical path coverage deficits identified below. This report recommends BLOCKING the pipeline until the CRITICAL-severity paths are addressed, because several zero-coverage modules are on the security and data-integrity critical path.

---

## Coverage Breakdown by Module

| Module | Coverage | Statements | Missing | Status |
|--------|----------|------------|---------|--------|
| `src/simulation` | 100.0% | 148 | 0 | EXCELLENT |
| `src/tom` | 97.6% | 206 | 5 | EXCELLENT |
| `src/patterns` | 96.2% | 78 | 3 | EXCELLENT |
| `src/semantic` | 95.2% | 687 | 33 | EXCELLENT |
| `src/integrations` | 93.5% | 216 | 14 | GOOD |
| `src/pov` | 88.1% | 486 | 58 | GOOD |
| `src/rag` | 87.8% | 156 | 19 | GOOD |
| `src/conformance` | 87.7% | 187 | 23 | GOOD |
| `src/core` | 86.9% | 1,256 | 165 | GOOD |
| `src/api` | 84.9% | 2,995 | 453 | WARNING |
| `src/evidence` | 67.4% | 724 | 236 | CRITICAL |
| `src/mcp` | 66.2% | 231 | 78 | CRITICAL |
| `src/monitoring` | 61.8% | 327 | 125 | CRITICAL |
| `src/agents` | 52.9% | 68 | 32 | CRITICAL |

### Files with 0% Coverage (Critical)

| File | Statements Missing | Risk Level |
|------|--------------------|------------|
| `src/monitoring/worker.py` | 47 | HIGH |
| `src/monitoring/detector.py` | 27 | HIGH |
| `src/monitoring/notification.py` | 15 | HIGH |
| `src/monitoring/collector.py` | 24 | HIGH |
| `src/monitoring/events.py` | 11 | MEDIUM |
| `src/core/audit.py` | 28 | HIGH |
| `src/evidence/dedup.py` | 24 | MEDIUM |
| `src/agents/recommender.py` | 32 | MEDIUM |

### Source Files with No Test File At All

The following source files have neither a direct test file nor significant indirect coverage via integration paths:

- `src/api/middleware/audit.py` — Audit trail middleware
- `src/core/rate_limiter.py` — Per-user Redis rate limiter
- `src/core/database.py` — DB session factory (47.4% covered)
- `src/core/neo4j.py` — Neo4j helper (33.3% covered)
- `src/core/redis.py` — Redis stream helpers (38.0% covered)
- `src/governance/migration_cli.py` — CLI entry point
- `src/simulation/service.py` — Scenario serialization
- `src/simulation/suggester.py` — LLM scenario suggester
- `src/simulation/coverage.py` — Evidence coverage classifier
- `src/simulation/epistemic.py` — Uncertainty quantification
- `src/simulation/financial.py` — Financial modeling
- `src/simulation/ranking.py` — Scenario ranking

---

## Findings

### [CRITICAL] COVERAGE: Monitoring Worker — Zero Coverage on 47 Statements

**File**: `src/monitoring/worker.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def process_task(task_data: dict[str, Any]) -> dict[str, Any]:
    task_type = task_data.get("task_type", "unknown")
    if task_type == "collect":
        from src.monitoring.collector import collect_evidence
        return await collect_evidence(...)
    elif task_type == "detect":
        return {"status": "detection_completed", "deviations_found": 0}
    elif task_type == "alert":
        return {"status": "alert_processed"}
```
**Description**: The monitoring worker module (`worker.py`) has 0% line coverage across 47 executable statements. This includes `submit_monitoring_task`, `process_task` (the dispatch router), and `run_worker` (the Redis stream consumer loop). The same zero-coverage status applies to `collector.py` (24 missing), `detector.py` (27 missing), `notification.py` (15 missing), and `events.py` (11 missing). The `test_monitoring.py` file covers only config, baseline, scheduler, comparator, and alerting — the five modules that process already-collected data. The entire data collection and delivery pipeline is untested.

**Risk**: Silent failures in the monitoring pipeline — dropped Redis stream tasks, failed evidence collection, or undelivered alerts — will not be caught by CI. A regression in task routing logic would go undetected until a monitoring job silently fails in deployment.

**Recommendation**: Add tests for `process_task` dispatch routing (collect, detect, alert, unknown), `submit_monitoring_task` stream publishing, and `notify_deviation`/`notify_alert` publishing paths using mocked Redis. The `run_worker` loop can be tested with a pre-populated mock stream and a fast shutdown event.

---

### [CRITICAL] COVERAGE: Core Audit Logging — Zero Coverage

**File**: `src/core/audit.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def log_audit_event_async(
    method: str,
    path: str,
    user_id: str,
    status_code: int,
    engagement_id: str | None = None,
    duration_ms: float = 0.0,
    session: AsyncSession | None = None,
) -> None:
    """Persist an HTTP audit event for compliance.
    Always writes a structured log record for SIEM ingestion.
    When a database session is provided, also persists the event to
    the http_audit_events table."""
```
**Description**: `src/core/audit.py` has 0% line coverage across 28 statements. This module is responsible for structured audit logging of all HTTP mutating operations (POST/PUT/PATCH/DELETE) for SIEM ingestion and the `http_audit_events` database table. No tests verify that: (1) audit records are created with correct fields, (2) anonymous requests are recorded correctly, (3) the structured log format is correct, or (4) the session-conditional persistence path works.

**Risk**: Compliance violations: if audit logging silently fails or produces malformed records, the platform's audit trail requirement is unmet without any CI warning.

**Recommendation**: Add `tests/core/test_audit.py` covering: record creation with all fields, anonymous actor fallback, `session=None` path (log-only), and `session` provided path (DB persist). Use mocked `AsyncSession`.

---

### [CRITICAL] COVERAGE: Evidence Deduplication — Zero Coverage

**File**: `src/evidence/dedup.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def find_duplicates_by_hash(
    session: AsyncSession,
    content_hash: str,
    engagement_id: uuid.UUID,
    exclude_id: uuid.UUID | None = None,
) -> list[EvidenceItem]:
    query = select(EvidenceItem).where(
        EvidenceItem.engagement_id == engagement_id,
        EvidenceItem.content_hash == content_hash,
    )
```
**Description**: `src/evidence/dedup.py` has 0% coverage across 24 statements. The module provides three functions — `find_duplicates_by_hash`, `check_is_duplicate`, and `get_duplicate_groups` — that the evidence upload pipeline calls to detect duplicate submissions. None are tested. The `exclude_id` path in `find_duplicates_by_hash` and the grouping logic in `get_duplicate_groups` are entirely unvalidated.

**Risk**: Duplicate detection logic failures could allow the same evidence file to be ingested multiple times, creating data integrity issues and inflating evidence counts. Alternatively, a bug could incorrectly flag non-duplicate files.

**Recommendation**: Add `tests/evidence/test_dedup.py` covering: hash match found, hash not found, `exclude_id` exclusion logic, and `get_duplicate_groups` grouping of multiple duplicates.

---

### [CRITICAL] COVERAGE: Auth `get_current_user` — 20.5% of Function Untested

**File**: `src/core/auth.py` (lines 289-377)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> User:
    # Auth source priority:
    # 1. Authorization: Bearer <token> header
    # 2. kmflow_access HttpOnly cookie
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get(ACCESS_COOKIE_NAME)  # line 313
    if token is None:
        raise HTTPException(...)                           # line 316
```
**Description**: Coverage analysis shows lines 208, 217, 226-227, 239, 246 are uncovered in `auth.py`. These correspond to the `set_auth_cookies` / `clear_auth_cookies` helper functions (lines 194-274) and the cookie-based token extraction path in `get_current_user` (line 313). The `test_auth_cookies.py` file exists but the cookie authentication fallback path — when no Bearer header is present but `kmflow_access` cookie is set — has no integration test exercising the full flow from cookie to authenticated user. The `set_auth_cookies` and `clear_auth_cookies` functions also have no tests verifying cookie attributes (httponly, secure, samesite, path, max_age).

**Risk**: The HttpOnly cookie auth path (Issue #156) is a browser-facing security feature. Untested cookie security attributes (especially `samesite` and `path` on the refresh cookie) could silently regress, creating CSRF exposure.

**Recommendation**: Add tests in `test_auth_cookies.py` verifying: (1) `set_auth_cookies` sets correct `httponly=True`, `samesite="strict"` on refresh cookie with path restriction, (2) `clear_auth_cookies` zeroes max_age, (3) `get_current_user` succeeds with only a valid `kmflow_access` cookie (no Bearer header).

---

### [HIGH] COVERAGE: WebSocket Endpoint — 80.8% of Code Untested

**File**: `src/api/routes/websocket.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
@router.websocket("/ws/monitoring/{engagement_id}")
async def monitoring_websocket(
    websocket: WebSocket,
    engagement_id: str,
    token: str | None = Query(default=None),
) -> None:
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
    ...
    current_count = manager.get_connection_count(engagement_id)
    if current_count >= settings.ws_max_connections_per_engagement:
        await websocket.close(code=1008, reason=...)
```
**Description**: `src/api/routes/websocket.py` has 19.2% coverage with 122 statements unexercised. The existing `test_websocket_auth.py` tests use `TestClient` with `with client.websocket_connect(...)` for the auth token checks, but the Redis pub/sub forwarding loop, the heartbeat mechanism, the `ConnectionManager.broadcast()` method, and the `alerts` WebSocket endpoint are all untested. The `ConnectionManager` class itself (connect, disconnect, broadcast, cleanup of dead connections) has no dedicated unit tests.

**Risk**: Real-time alert delivery could silently fail. Dead connection cleanup bugs could cause memory leaks under sustained usage. The broadcast method silently swallows exceptions from dead websockets — if this exception handling is wrong, a single failed connection could terminate delivery to all other connections.

**Recommendation**: Add unit tests for `ConnectionManager` (connect, disconnect, broadcast with one dead socket), and expand WebSocket tests to cover the pub/sub message forwarding and heartbeat paths using mocked Redis pub/sub.

---

### [HIGH] COVERAGE: MCP Server and Tools — 41.8% Untested

**File**: `src/mcp/server.py`, `src/mcp/tools.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/mcp/server.py: 58.2% covered (59 missing statements)
@router.get("/mcp/tools", response_model=ToolsListResponse)
async def list_tools(
    api_key_data: dict = Depends(require_mcp_api_key),
) -> ToolsListResponse:
    """List available MCP tools."""
    from src.mcp.tools import TOOL_REGISTRY
    return ToolsListResponse(tools=list(TOOL_REGISTRY.values()))
```
**Description**: `src/mcp/server.py` has 58.2% coverage with 59 missing statements. `src/mcp/tools.py` is not tracked in the coverage run at all, indicating it is never imported during the test suite. The MCP `list_api_keys` function in `src/mcp/auth.py` (lines 129-162) is also uncovered — only `generate_api_key`, `validate_api_key`, and `revoke_api_key` have tests.

**Risk**: MCP tools expose platform data to external LLM agents. Untested tool implementations could return incorrect engagement data or fail silently, causing hallucination or data leakage in downstream LLM workflows.

**Recommendation**: Add tests for `list_api_keys` (active-only filter, include_inactive flag), MCP tool execution paths via `/mcp/tools/call`, and verify the `TOOL_REGISTRY` entries are callable and return correct response shapes.

---

### [HIGH] COVERAGE: Evidence Module — 32.6% of Module Untested

**File**: `src/evidence/parsers/` (9 of 17 parser files have no dedicated test)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/evidence/parsers/document_parser.py: 29.7% coverage
# No test files exist for:
# bpmn_parser.py, communication_parser.py, document_parser.py,
# image_parser.py, job_aids_parser.py, km4work_parser.py,
# regulatory_parser.py, structured_data_parser.py, factory.py
```
**Description**: The evidence module has 67.4% overall coverage with 236 missing statements. Nine evidence parsers have no dedicated test files. The `document_parser.py` (29.7% covered) handles PDF, Word, and spreadsheet files — the most common evidence type in consulting engagements. The `factory.py` (which routes files to the correct parser) has no tests. The `dedup.py` is at 0%. While `test_extended_parsers.py` and `test_parsers.py` provide some indirect coverage, the full parser behavior for complex inputs (malformed XML in BPMN, corrupted PDFs, large CSV files) is untested.

**Risk**: Evidence parser failures for common file types will not be caught before deployment. A malformed BPMN file or a large spreadsheet could cause unhandled exceptions in the pipeline.

**Recommendation**: Add tests for `BpmnParser` with valid and invalid BPMN XML, `DocumentParser` with a minimal PDF mock, `factory.py` classify_by_extension for all 17 supported extensions, and `dedup.py` hash matching logic.

---

### [HIGH] COVERAGE: Per-User Rate Limiter — Untested

**File**: `src/core/rate_limiter.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def copilot_rate_limit(
    request: Request,
    user=Depends(require_permission("copilot:query")),
):
    """FastAPI dependency that enforces per-user rate limiting on copilot.
    Uses Redis sorted sets with timestamps as scores for sliding window.
    Falls back to allowing the request if Redis is unavailable.
    """
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return user  # fail-open when Redis unavailable
```
**Description**: `src/core/rate_limiter.py` has no tests. The copilot rate limiter uses a Redis sliding window sorted set — a stateful mechanism that requires specific test scenarios. The fail-open fallback (when Redis is unavailable) is undocumented from a testing perspective. The `test_rate_limiter.py` file tests only the in-memory LLM rate limiter in `simulations.py` — a different module entirely.

**Risk**: Unbounded LLM API calls could occur if the rate limiter regresses. The fail-open vs. fail-closed behavior on Redis unavailability affects security posture (fail-open is correct here for availability but needs to be explicit).

**Recommendation**: Add `tests/core/test_rate_limiter.py` with mocked Redis pipeline: under-limit request allowed, over-limit raises 429, Redis unavailable returns user (fail-open), per-user key isolation.

---

### [MEDIUM] COVERAGE: Agents Module — 52.9% Coverage

**File**: `src/agents/recommender.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/agents/recommender.py: 0% coverage (32 missing statements)
# The agent recommender is only tested indirectly via the graph tests
```
**Description**: `src/agents/recommender.py` has 0% coverage across 32 statements. The agents module overall is at 52.9% (36/68 statements). The recommender generates actionable recommendations from gap analysis results — a core output of the platform. No tests verify recommendation generation, prioritization logic, or the recommendation data structure.

**Risk**: Recommendation quality issues (wrong priority, missing recommendations, invalid output structure) are not caught by CI.

**Recommendation**: Add `tests/agents/test_recommender.py` with basic unit tests for recommendation generation from mock gap data, priority scoring, and empty input handling.

---

### [MEDIUM] COVERAGE: Simulation Service and Suggester — Not in Coverage Run

**File**: `src/simulation/service.py`, `src/simulation/suggester.py`, `src/simulation/coverage.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# src/simulation/suggester.py — uses Claude API for LLM suggestions
import anthropic

def _sanitize_text(text: str, max_len: int) -> str:
    """Strip control characters and truncate to max_len."""
```
**Description**: Five simulation files (`service.py`, `suggester.py`, `coverage.py`, `epistemic.py`, `financial.py`, `ranking.py`) are not tracked in the coverage run at all — they are never imported during the test suite. The coverage.json shows only 4 simulation files tracked (engine, impact, scenarios, `__init__`). The LLM suggester (`suggester.py`) calls the Anthropic API and performs input sanitization — the sanitization logic is untested. The financial modeling (`financial.py`) and epistemic uncertainty (`epistemic.py`) modules perform numerical calculations that should have unit tests.

**Risk**: The simulation suggestion feature and financial calculations run completely untested. The `_sanitize_text` function in `suggester.py` that removes control characters before sending to the LLM is untested, which could allow prompt injection via control characters.

**Recommendation**: Add tests for `_sanitize_text` input sanitization in `suggester.py`, financial calculation functions in `financial.py`, evidence coverage classification thresholds in `coverage.py`, and the `scenario_to_response` serializer in `service.py`.

---

### [MEDIUM] TEST_QUALITY: Over-Mocking in Pipeline Integration Tests

**File**: `tests/evidence/test_pipeline_integration.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def test_builds_nodes_from_entity_metadata(self) -> None:
    frag = MagicMock(spec=EvidenceFragment)
    frag.content = content
    frag.metadata_json = None
    frag.id = uuid.uuid4()
    frag.evidence_id = uuid.uuid4()
    # Neo4j driver, session, everything is mocked
    mock_driver = AsyncMock()
    with patch("src.semantic.builder.AsyncGraphDatabase") as mock_db:
        ...
```
**Description**: The evidence pipeline integration tests mock `EvidenceFragment` with `MagicMock(spec=EvidenceFragment)` and wire in mocked Neo4j drivers and database sessions. While appropriate for unit isolation, these tests do not exercise the actual data flow through multiple pipeline stages. The critical path of `ingest_evidence` → `extract_entities` → `build_fragment_graph` → `run_semantic_bridges` is never tested end-to-end with real domain objects flowing through. Database flush ordering, SQLAlchemy lazy-loading, and Neo4j transaction boundaries are not validated.

**Risk**: Structural integration bugs between pipeline stages will not be caught by the mocked unit tests. A real integration bug (e.g., flushing session before foreign key constraint satisfies) would only surface in deployment.

**Recommendation**: Add at least one semi-integration test that instantiates real `EvidenceItem` and `EvidenceFragment` objects (not MagicMock) and runs the full pipeline with only Neo4j mocked. This validates ORM interaction patterns without requiring a live database.

---

### [MEDIUM] TEST_QUALITY: Trivial `assert is not None` Assertions

**File**: `tests/pov/test_generator.py`, `tests/simulation/test_simulation.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
# tests/pov/test_generator.py
assert result.process_model is not None
assert result.process_model.bpmn_xml is not None
assert model.metadata_json is not None
assert model.generated_at is not None

# tests/simulation/test_simulation.py
assert result is not None
assert "metrics" in result
```
**Description**: Multiple test files use `assert X is not None` as their primary assertion for complex output objects. In the POV generator tests, the BPMN XML content is never validated — an empty string `""` or a minimal `<bpmn:definitions/>` would both pass. In simulation tests, the presence of a `"metrics"` key is checked but the actual metric values, types, or ranges are not asserted.

**Risk**: Tests pass even when output is structurally malformed. The POV generator could produce invalid BPMN and CI would not catch it.

**Recommendation**: Replace `assert X is not None` with content-aware assertions: for BPMN XML, assert `bpmn_xml.startswith("<bpmn:definitions")` or parse with lxml. For metrics, assert expected keys exist with expected numeric ranges.

---

### [MEDIUM] COVERAGE: Frontend Components — 13 Test Files for 99 Source Files

**File**: `frontend/src/` (99 source files)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
frontend/__tests__/ (13 files total):
  AppShell.test.tsx, BPMNViewer.test.tsx, ErrorBoundary.test.tsx,
  EvidenceHeatmap.test.tsx, EvidenceUploader.test.tsx, GraphExplorer.test.tsx,
  HealthStatus.test.tsx, Sidebar.test.tsx, SuggestionCard.test.tsx,
  api.test.ts, api-extended.test.ts, taskmining-api.test.ts,
  taskmining-pages.test.tsx

Missing unit tests for (sample):
  AnnotationPanel.tsx, ConfidenceBadge.tsx, GapTable.tsx,
  KPICard.tsx, RegulatoryOverlay.tsx, RoadmapTimeline.tsx,
  TOMDimensionCard.tsx, PageLayout.tsx, Legend.tsx
  + 31 page.tsx files with zero tests
```
**Description**: The frontend has 99 source TypeScript/TSX files but only 13 unit test files. Nine business logic components have no tests: `AnnotationPanel`, `ConfidenceBadge`, `GapTable`, `KPICard`, `RegulatoryOverlay`, `RoadmapTimeline`, `TOMDimensionCard`, `PageLayout`, `Legend`. All 31 Next.js page components have zero unit tests. The Playwright E2E specs (25 files) provide page-load validation but not component behavior testing.

**Risk**: React component regressions in RBAC-gated UI elements (e.g., `AnnotationPanel` should only render for authorized roles), data formatting in `GapTable`, or confidence score display in `ConfidenceBadge` will not be caught by CI.

**Recommendation**: Add React Testing Library tests for at minimum: `GapTable` (renders correct columns, handles empty data), `ConfidenceBadge` (color thresholds), `RegulatoryOverlay` (correct regulation labels), and the portal upload page (disabled state without engagement ID).

---

### [LOW] COVERAGE: E2E Tests Are Structural Rather Than Behavioral

**File**: `frontend/e2e/evidence.spec.ts`, `frontend/e2e/admin.spec.ts`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```typescript
test("evidence page loads with heading", async ({ page }) => {
  await page.goto("/evidence");
  await expect(
    page.getByRole("heading", { name: "Evidence Upload" })
  ).toBeVisible();
});
test("upload area is disabled without engagement ID", async ({ page }) => {
  await page.goto("/evidence");
  await expect(
    page.getByText("Enter a valid engagement ID above to enable file uploads")
  ).toBeVisible();
});
```
**Description**: The 25 Playwright E2E spec files primarily test that pages load and contain expected headings or UI elements. They do not test complete user journeys: authentication → upload file → verify in list, or admin login → execute retention cleanup → verify result. The login flow E2E is absent. No E2E test sends an actual HTTP request to the backend.

**Risk**: E2E tests provide a false confidence floor — they pass even if the core workflows are broken, as long as the page renders its static heading.

**Recommendation**: Add flow-based E2E tests: (1) user logs in via `/api/v1/auth/token` and accesses an authenticated page, (2) evidence upload with a real file via the uploader component, (3) admin page shows 403 UI for non-admin credentials.

---

### [LOW] CONFIG: No Coverage Threshold Enforced in CI

**File**: `/Users/proth/repos/kmflow/pyproject.toml`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
# No --cov-fail-under threshold configured
```
**Description**: The pytest configuration has no `--cov-fail-under` threshold. Coverage is measured and reported but not gated. A developer can merge a PR that drops coverage from 84% to 60% without any CI failure. The SDLC quality gate `coverage_above_80` requires manual verification rather than automated enforcement.

**Risk**: Coverage regressions are silent. Future development could erode coverage incrementally below the 80% threshold without triggering CI failure.

**Recommendation**: Add `--cov=src --cov-fail-under=82 --cov-report=term-missing` to `addopts`. Set an initial threshold of 82% (2% above current) to prevent regression while allowing the existing gaps to be addressed iteratively.

---

## Risk Assessment

| Finding | Severity | Risk if Left Unaddressed |
|---------|----------|--------------------------|
| Monitoring worker/collector/detector: 0% | CRITICAL | Silent monitoring pipeline failures; missed alerts |
| Core audit logging: 0% | CRITICAL | Undetected audit trail corruption; compliance failure |
| Evidence deduplication: 0% | CRITICAL | Duplicate evidence ingest; data integrity issues |
| Auth cookie helpers untested | CRITICAL | CSRF exposure from misconfigured samesite/path attributes |
| WebSocket: 80.8% untested | HIGH | Auth bypass, memory leak from dead connections |
| MCP server/tools: 41.8% untested | HIGH | Incorrect data to LLM agents; silent tool failures |
| Evidence parsers: 9 of 17 untested | HIGH | Parser failures on common file types in production |
| Per-user rate limiter: untested | HIGH | Unbounded LLM API cost from rate limit regression |
| Agents recommender: 0% | MEDIUM | Wrong recommendations without CI detection |
| Simulation suggester (LLM): 0% | MEDIUM | Prompt injection via unsanitized input |
| Frontend components: 13/99 tested | MEDIUM | UI regressions in RBAC-gated components |
| Over-mocked integration tests | MEDIUM | Integration bugs hidden by mock seams |
| Trivial assertions | MEDIUM | Malformed outputs pass CI |
| E2E tests superficial | LOW | False confidence in user journey coverage |
| No CI coverage threshold | LOW | Silent coverage regression |

---

## Findings Count

| Severity | Count |
|----------|-------|
| CRITICAL | 4 |
| HIGH | 5 |
| MEDIUM | 6 |
| LOW | 2 |
| **Total** | **17** |

---

## Overall Coverage Assessment

**Overall line coverage**: 84.0% — above the 80% CLAUDE.md threshold.

**Pipeline Status**: BLOCKED — The 84% aggregate obscures zero-coverage in the security audit trail module (`src/core/audit.py`) and the monitoring delivery pipeline (5 modules at 0%). These are not low-risk infrastructure modules; they are compliance and alerting critical paths. The recommendation is to block merge until the four CRITICAL findings are addressed.

**PIPELINE STATUS: BLOCKED**
