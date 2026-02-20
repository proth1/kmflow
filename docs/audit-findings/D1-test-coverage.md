# D1: Test Coverage Audit Findings

**Agent**: D1 (Test Coverage Auditor)
**Date**: 2026-02-20
**Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage

---

## Executive Summary

**PIPELINE STATUS: CRITICAL — BLOCKED**

The KMFlow backend test suite has a **67.1% file coverage ratio** (98 test files covering 146 source modules). While the test count of 1,475 individual test functions is substantial, significant coverage gaps exist in security-critical paths, infrastructure modules, and the frontend. The evidence upload API endpoint — the primary data ingestion path — has **zero API-level tests** for its actual HTTP upload flow. Multiple monitoring subsystem modules have no tests at all.

| Metric | Value |
|--------|-------|
| Source files (non-init) | 146 |
| Test files | 98 |
| File coverage ratio | 67.1% |
| Total test functions | 1,475 |
| Source modules with no tests | 65 |
| HTTP status code assertions | 278 |
| Frontend component unit tests | 5 (covering 65 source components) |

---

## Coverage Map

### Modules WITH Tests

| Module | Test File | Assessment |
|--------|-----------|------------|
| `src/core/auth.py` | `tests/core/test_auth.py` | Good — JWT creation, expiry, wrong key tested |
| `src/core/permissions.py` | `tests/core/test_permissions.py` | Good — role hierarchy, RBAC matrix tested |
| `src/core/security.py` | `tests/core/test_security.py` | Good — engagement-level isolation tested |
| `src/core/encryption.py` | `tests/core/test_encryption.py` | Good — roundtrip, invalid input tested |
| `src/core/models.py` | `tests/core/test_models.py` | Adequate — schema structure tests |
| `src/api/routes/auth.py` | `tests/api/test_auth_routes.py` | Good — login, refresh, logout with blacklist |
| `src/api/routes/evidence.py` | `tests/api/test_evidence.py` | PARTIAL — upload endpoint has NO tests |
| `src/api/routes/engagements.py` | `tests/api/test_engagements.py` | Good — CRUD, filters tested |
| `src/api/routes/users.py` | `tests/api/test_users.py` | Good — RBAC create/update/delete tested |
| `src/api/middleware/security.py` | `tests/api/test_security_middleware.py` | Good — headers, rate limiting tested |
| `src/monitoring/alerting.py` | `tests/monitoring/test_monitoring.py` | Adequate — severity, dedup tested |
| `src/monitoring/baseline.py` | `tests/monitoring/test_monitoring.py` | Adequate — snapshot, comparison tested |
| `src/monitoring/scheduler.py` | `tests/monitoring/test_monitoring.py` | Adequate — cron parsing tested |
| `src/simulation/engine.py` | `tests/simulation/test_simulation.py` | Good — all simulation types tested |
| `src/evidence/pipeline.py` | `tests/evidence/test_pipeline.py` | Partial — hash/storage tested; intelligence pipeline mocked |
| `src/mcp/auth.py` | `tests/mcp/test_mcp.py` | Adequate — key gen, validate tested |

### Modules WITHOUT Tests (65 modules)

#### Security/Infrastructure Critical (HIGH RISK)
| Module | Risk |
|--------|------|
| `src/api/middleware/audit.py` | Audit trail logic completely untested |
| `src/core/retention.py` | Data deletion policy completely untested |
| `src/core/rate_limiter.py` | Per-user copilot rate limiter untested |
| `src/core/database.py` | DB session factory untested |
| `src/api/deps.py` | Session dependency untested |
| `src/api/routes/admin.py` | Admin-only retention cleanup route untested |
| `src/api/routes/websocket.py` | WebSocket auth + connection limit untested |

#### Monitoring Subsystem (Partial Coverage Only)
| Module | Risk |
|--------|------|
| `src/monitoring/worker.py` | Redis stream consumer untested |
| `src/monitoring/collector.py` | Data collection untested |
| `src/monitoring/detector.py` | Deviation detection untested |
| `src/monitoring/events.py` | Event publishing untested |
| `src/monitoring/notification.py` | Alert notification untested |

#### Evidence Parsers (Majority Untested)
| Module | Risk |
|--------|------|
| `src/evidence/parsers/audio_parser.py` | Untested |
| `src/evidence/parsers/communication_parser.py` | Untested |
| `src/evidence/parsers/document_parser.py` | Untested |
| `src/evidence/parsers/factory.py` | Parser factory untested |
| `src/evidence/parsers/image_parser.py` | Untested |
| `src/evidence/parsers/job_aids_parser.py` | Untested |
| `src/evidence/parsers/km4work_parser.py` | Untested |
| `src/evidence/parsers/regulatory_parser.py` | Untested |
| `src/evidence/parsers/structured_data_parser.py` | Untested |
| `src/evidence/parsers/video_parser.py` | Untested |
| `src/evidence/dedup.py` | Deduplication logic untested |

#### Integration Connectors (Entirely Untested)
| Module | Risk |
|--------|------|
| `src/integrations/camunda.py` | Untested |
| `src/integrations/celonis.py` | Untested |
| `src/integrations/salesforce.py` | Untested |
| `src/integrations/sap.py` | Untested |
| `src/integrations/servicenow.py` | Untested |
| `src/integrations/soroco.py` | Untested |
| `src/integrations/field_mapping.py` | Untested |

#### Simulation Subsystem (Partial)
| Module | Risk |
|--------|------|
| `src/simulation/scenarios.py` | `validate_scenario` is partially tested via test_simulation.py |
| `src/simulation/engine.py` | `run_simulation` is tested |
| `src/simulation/impact.py` | `calculate_cascading_impact` is tested |
| `src/simulation/suggester.py` | Untested |

#### MCP (Partial)
| Module | Risk |
|--------|------|
| `src/mcp/server.py` | Server routing untested |
| `src/mcp/tools.py` | Tool implementations untested |
| `src/mcp/schemas.py` | Schemas untested |

#### RAG (Partial)
| Module | Risk |
|--------|------|
| `src/rag/copilot.py` | Copilot orchestration untested |
| `src/rag/embeddings.py` | Embedding generation untested |
| `src/rag/retrieval.py` | Partially tested |

#### Semantic Bridges (Entirely Untested)
| Module | Risk |
|--------|------|
| `src/semantic/bridges/communication_deviation.py` | Untested |
| `src/semantic/bridges/evidence_policy.py` | Untested |
| `src/semantic/bridges/process_evidence.py` | Untested |
| `src/semantic/bridges/process_tom.py` | Untested |
| `src/semantic/ontology/loader.py` | Untested |
| `src/semantic/ontology/validate.py` | Untested |

---

## Findings

### [CRITICAL] COVERAGE: Evidence Upload API — Zero HTTP-Level Tests

**File**: `src/api/routes/evidence.py:129`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    engagement_id: UUID = Form(...),
    category: EvidenceCategory | None = Form(None),
    metadata: str | None = Form(None),
    ...
```
**Description**: The `POST /api/v1/evidence/upload` endpoint is the primary data ingestion path for the entire platform. The test file `tests/api/test_evidence.py` covers `GET`, `validate`, and `batch_validate` endpoints but contains **zero tests** for the upload endpoint. The comment in the test file says "Tests cover: upload, get, list..." — upload is listed but absent. There are no multipart/form-data POST tests anywhere in the API test suite for this route.

**Risk**: The most-used API endpoint for evidence ingestion — including file size validation, MIME type detection, deduplication, and fragment extraction — runs completely untested at the HTTP layer. Regressions in authentication, permission checking, or file handling for this endpoint will not be caught by CI.

**Recommendation**: Add `TestUploadEvidence` class covering: (1) successful upload with multipart form, (2) empty file rejection (400), (3) invalid JSON metadata rejection (400), (4) missing engagement_id (422), (5) unauthorized upload (403).

---

### [CRITICAL] COVERAGE: Token Blacklist Functions — No Unit Tests

**File**: `src/core/auth.py:149`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def is_token_blacklisted(request: Request, token: str) -> bool:
    """Check if a token has been blacklisted in Redis."""
    ...
    result = await redis.get(f"token:blacklist:{token}")

async def blacklist_token(request: Request, token: str, expires_in: int = 1800) -> None:
    """Add a token to the blacklist in Redis."""
    await redis.setex(f"token:blacklist:{token}", expires_in, "1")
```
**Description**: The `is_token_blacklisted` and `blacklist_token` functions are never directly tested. The logout test (`test_auth_routes.py:232`) only verifies that Redis `setex` was called once, but does not test: (1) that a blacklisted token is rejected on subsequent requests, (2) the Redis-unavailable fallback path (`failing closed` behavior), or (3) the blacklist key format/TTL correctness.

**Risk**: If the blacklist check is bypassed or the Redis fallback behaves incorrectly, revoked tokens remain usable — a direct authentication bypass vulnerability.

**Recommendation**: Add unit tests for `is_token_blacklisted` with: Redis returning "1" (blocked), Redis returning None (not blocked), Redis raising exception (fail-closed). Add integration test verifying that a logged-out token is rejected on a subsequent authenticated request.

---

### [CRITICAL] COVERAGE: Admin Routes — Entirely Untested

**File**: `src/api/routes/admin.py:25`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
@router.post("/retention-cleanup")
async def run_retention_cleanup(
    user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    ...
    dry_run: bool = Query(default=True),
    x_confirm_action: str | None = Header(default=None),
) -> dict[str, Any]:
```
**Description**: The admin routes (`/api/v1/admin/retention-cleanup`, `/api/v1/admin/rotate-encryption-key`) are entirely untested. These routes perform destructive operations: bulk archiving of engagement data and encryption key rotation. There are no tests verifying: (1) that non-admin users receive 403, (2) that the confirmation header requirement is enforced, (3) that dry_run vs. live execution behaves differently.

**Risk**: Admin-only destructive operations could be inadvertently called without confirmation, or could be called by non-admin users if the `require_role` dependency is misconfigured.

**Recommendation**: Add `tests/api/test_admin_routes.py` covering: RBAC enforcement (non-admin 403), dry-run mode response, missing confirmation header enforcement, and successful execution flow.

---

### [CRITICAL] COVERAGE: Data Retention Logic — Untested

**File**: `src/core/retention.py:20`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def find_expired_engagements(session: AsyncSession) -> list[Engagement]:
    """Find engagements that have exceeded their retention period."""
    ...
    for eng in engagements:
        cutoff = eng.created_at.replace(tzinfo=UTC) + timedelta(days=eng.retention_days or 0)
        if now > cutoff:
            expired.append(eng)

async def cleanup_expired_engagements(session: AsyncSession) -> int:
    """Archive expired engagements and cascade-delete their evidence."""
```
**Description**: The data retention enforcement functions have zero tests. The cutoff calculation (`created_at + retention_days`) and filtering logic are untested. Edge cases such as: engagements with `retention_days=0`, engagements in ACTIVE status being exempt, and timezone handling in `created_at.replace(tzinfo=UTC)` are not verified.

**Risk**: Incorrect retention logic could archive active engagements prematurely, or fail to archive expired ones — a GDPR compliance risk.

**Recommendation**: Add `tests/core/test_retention.py` covering: expired engagement detection, non-expired exclusion, status-based filtering (ACTIVE skipped), and the cleanup archiving path.

---

### [HIGH] COVERAGE: WebSocket Authentication — Untested

**File**: `src/api/routes/websocket.py:105`
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
    try:
        settings = get_settings()
        decode_token(token, settings)
    except Exception as e:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    # Check connection limit
    current_count = manager.get_connection_count(engagement_id)
    if current_count >= settings.ws_max_connections_per_engagement:
        await websocket.close(code=1008, reason=...)
```
**Description**: The WebSocket endpoints `/ws/monitoring/{engagement_id}` and `/ws/alerts/{engagement_id}` have zero tests. Authentication (missing token, invalid token, expired token), connection limit enforcement, Redis pub/sub message forwarding, heartbeat behavior, and disconnect cleanup are all untested. The `ConnectionManager` class itself is also untested.

**Risk**: WebSocket authentication bypass could allow unauthenticated clients to receive real-time security alerts and monitoring data.

**Recommendation**: Add `tests/api/test_websocket.py` testing the `ConnectionManager` class directly, plus WebSocket endpoint tests for: no token → close 1008, invalid token → close 1008, connection limit exceeded → close 1008.

---

### [HIGH] COVERAGE: Audit Logging Middleware — Untested

**File**: `src/api/middleware/audit.py:20`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
class AuditLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: ...) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)
        ...
        logger.info("AUDIT method=%s path=%s user=%s ...", ...)
        response.headers["X-Audit-Logged"] = "true"
        return response
```
**Description**: The `AuditLoggingMiddleware` is included in the application stack but has no tests. The middleware is responsible for logging all mutating (POST/PUT/PATCH/DELETE) operations — a compliance requirement. No test verifies: (1) that the `X-Audit-Logged` header is set on mutating requests, (2) that GET requests are skipped, (3) that engagement_id is extracted from paths correctly, or (4) that anonymous requests are recorded correctly.

**Risk**: Audit trail compliance could silently fail if the middleware is misconfigured or produces incorrect audit records.

**Recommendation**: Add tests for audit middleware verifying header presence on POST/PUT/DELETE, absence on GET, and engagement_id path extraction logic.

---

### [HIGH] COVERAGE: Per-User Rate Limiter — Untested

**File**: `src/core/rate_limiter.py:20`
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
```
**Description**: The copilot rate limiter uses a Redis sliding window. No tests verify: (1) that requests beyond the limit are rejected with 429, (2) that the Redis-unavailable fallback allows requests (the stated fail-open behavior), (3) that different users have independent limits, or (4) that the sliding window correctly expires old entries.

**Risk**: Rate limiting failure could allow unlimited LLM API calls per user, incurring unbounded cost.

**Recommendation**: Add `tests/core/test_rate_limiter.py` covering: under-limit allowed, over-limit rejected (429), Redis unavailable fallback (allow), per-user isolation.

---

### [HIGH] COVERAGE: Monitoring Worker and Event Pipeline — Untested

**File**: `src/monitoring/worker.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
async def process_task(task_data: dict[str, Any]) -> dict[str, Any]:
    task_type = task_data.get("task_type", "unknown")
    if task_type == "collect":
        from src.monitoring.collector import collect_evidence
        return await collect_evidence(...)
```
**Description**: Eight monitoring subsystem modules have no tests: `worker.py`, `collector.py`, `detector.py`, `events.py`, `notification.py`. The `test_monitoring.py` file covers only `config.py`, `baseline.py`, `scheduler.py`, `comparator.py`, and `alerting.py`. The worker dispatch loop, event publishing, and notification delivery paths are completely untested.

**Risk**: Silent failures in the monitoring pipeline would not be caught in CI. Monitoring workers could silently drop tasks or fail to deliver alerts.

**Recommendation**: Add tests for `submit_monitoring_task`, `process_task` dispatch routing, and notification delivery pathways with mocked Redis streams.

---

### [HIGH] MOCK_QUALITY: Evidence Upload Intelligence Pipeline — Over-Mocked

**File**: `tests/evidence/test_pipeline_integration.py:7`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
from unittest.mock import AsyncMock, MagicMock, patch

async def test_builds_nodes_from_entity_metadata(self) -> None:
    """Should create graph nodes from fragment entity metadata."""
    ...
    frag = MagicMock(spec=EvidenceFragment)
    frag.content = content
    frag.metadata_json = None
```
**Description**: The intelligence pipeline integration tests mock `EvidenceFragment` objects with `MagicMock(spec=EvidenceFragment)` and wire in mocked Neo4j drivers. While this is appropriate for unit isolation, the critical path of `ingest_evidence` → `extract_fragment_entities` → `build_fragment_graph` → `run_semantic_bridges` is never tested end-to-end with real objects flowing through. The session is always mocked, meaning database interaction patterns (flush order, refresh behavior) are not validated.

**Risk**: Structural integration bugs between the pipeline stages will not be caught in CI.

**Recommendation**: Add at least one integration test that instantiates `EvidenceItem` and `EvidenceFragment` directly (without MagicMock) and runs the full pipeline with only the Neo4j driver mocked.

---

### [HIGH] COVERAGE: Frontend Components — Critically Undertested

**File**: `frontend/src/` (65 source files)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
frontend/src/__tests__/useDataLoader.test.ts     (1 hook)
frontend/src/__tests__/api.test.ts               (API client)
frontend/src/hooks/__tests__/useDebouncedValue.test.ts  (1 hook)
frontend/src/lib/__tests__/api.test.ts           (API lib)
frontend/src/lib/__tests__/validation.test.ts    (validation)
```
**Description**: The frontend has 65 TypeScript/TSX source files but only 5 unit test files. All React page components (`dashboard/page.tsx`, `evidence/page.tsx`, `admin/page.tsx`, `portal/[engagementId]/page.tsx`, etc.) have zero unit tests. There are E2E Playwright specs that provide some coverage, but these require a running server and are not part of the standard CI unit test suite.

**Risk**: React component regressions (broken state management, missing error boundaries, incorrect RBAC UI enforcement) go undetected.

**Recommendation**: Add React Testing Library unit tests for at minimum: evidence upload component, dashboard engagement list, auth login flow, and admin page (verifying it does not render for non-admins).

---

### [MEDIUM] COVERAGE: Semantic Bridges — Entirely Untested

**File**: `src/semantic/bridges/` (4 modules)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
src/semantic/bridges/communication_deviation.py  — 0 tests
src/semantic/bridges/evidence_policy.py          — 0 tests
src/semantic/bridges/process_evidence.py         — 0 tests
src/semantic/bridges/process_tom.py              — 0 tests
```
**Description**: The four semantic bridge modules that connect evidence to process models, policies, and TOM alignment have zero tests. These are the core intelligence components that produce the platform's primary analytical outputs.

**Risk**: Incorrect bridge logic silently produces wrong process intelligence recommendations.

**Recommendation**: Add tests for each bridge covering: basic relationship creation, empty input handling, and type validation.

---

### [MEDIUM] COVERAGE: Integration Connectors — Entirely Untested

**File**: `src/integrations/` (7 connector modules)
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
src/integrations/camunda.py     — 0 tests
src/integrations/celonis.py     — 0 tests
src/integrations/salesforce.py  — 0 tests
src/integrations/sap.py         — 0 tests
src/integrations/servicenow.py  — 0 tests
src/integrations/soroco.py      — 0 tests
src/integrations/field_mapping.py — 0 tests
```
**Description**: While external connector integration tests are expected to require external service mocks, none of the connectors have even basic unit tests for: field mapping, error handling, authentication flow, or response parsing.

**Risk**: Connector bugs go undetected until deployed against real external systems.

**Recommendation**: Add unit tests for each connector mocking the HTTP client. At minimum test: successful connection, auth error handling, and field mapping correctness.

---

### [MEDIUM] TEST_QUALITY: Trivial Assertions in Critical Tests

**File**: `tests/pov/test_generator.py:76`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```python
assert result.process_model is not None
assert result.process_model.bpmn_xml is not None
assert model.metadata_json is not None
assert model.generated_at is not None
```
**Description**: Multiple test files use `assert X is not None` as their primary assertion. While not universally wrong, in several cases these tests could assert the actual content type, format, or value range of the result. The POV generator tests confirm that a `process_model` exists but do not verify that the BPMN XML is valid, contains expected elements, or follows correct structure.

**Risk**: Tests pass even when the actual output is malformed (e.g., empty BPMN string is not None but is invalid).

**Recommendation**: Replace `assert X is not None` assertions with meaningful content checks where the output structure is known.

---

### [MEDIUM] COVERAGE: MCP Server and Tools — Untested

**File**: `src/mcp/server.py`, `src/mcp/tools.py`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```
src/mcp/server.py   — 0 tests
src/mcp/tools.py    — 0 tests
src/mcp/schemas.py  — 0 tests
```
**Description**: The MCP (Model Context Protocol) server and tool implementations have no tests, only `src/mcp/auth.py` has coverage. The MCP tools expose platform capabilities to external LLM agents — untested tool implementations could return incorrect data or fail silently.

**Risk**: MCP tool regressions would not be caught in CI, potentially exposing incorrect data to LLM consumers.

---

### [LOW] E2E: Playwright E2E Tests Are Superficial

**File**: `frontend/e2e/evidence.spec.ts`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```typescript
test("evidence page loads with heading", async ({ page }) => {
  await page.goto("/evidence");
  await expect(page.getByRole("heading", { name: "Evidence Upload" })).toBeVisible();
});

test("upload area is disabled without engagement ID", async ({ page }) => {
  await page.goto("/evidence");
  await expect(page.getByText("Enter a valid engagement ID above...")).toBeVisible();
});
```
**Description**: The Playwright E2E specs primarily test that pages load and contain expected UI elements, but do not test complete user journeys (upload a file, verify it appears in the list). They do not test error states, authentication flows, or cross-page workflows. The auth/login E2E flow is absent.

**Risk**: E2E tests provide false confidence — they pass even if the core functionality is broken.

**Recommendation**: Add flow-based E2E tests: (1) login → upload evidence → verify in list, (2) admin creates user → new user logs in, (3) evidence upload fails with correct error message for invalid file type.

---

### [LOW] CONFIG: No Coverage Thresholds Enforced in CI

**File**: `pyproject.toml`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
```
**Description**: The pytest configuration has no `--cov-fail-under` threshold. Coverage is measured manually but not enforced in the CI pipeline. This means coverage regressions are silent.

**Risk**: Developers can merge PRs that reduce coverage below any threshold without CI failure.

**Recommendation**: Add `--cov=src --cov-fail-under=80 --cov-report=term-missing` to `addopts` in `pyproject.toml`. Target 90% as the mandatory gate.

---

## Critical Untested Paths Summary

| Path | Criticality | Status |
|------|-------------|--------|
| Evidence upload API endpoint (`POST /api/v1/evidence/upload`) | CRITICAL | No tests |
| Token blacklist check after logout | CRITICAL | No unit tests |
| Admin routes (retention-cleanup, rotate-key) | CRITICAL | No tests |
| Data retention cleanup logic | CRITICAL | No tests |
| WebSocket authentication | HIGH | No tests |
| Audit logging middleware | HIGH | No tests |
| Per-user rate limiter | HIGH | No tests |
| Monitoring worker/event pipeline | HIGH | No tests |
| Semantic bridges (4 modules) | MEDIUM | No tests |
| Integration connectors (7 modules) | MEDIUM | No tests |
| MCP server and tools | MEDIUM | No tests |
| Frontend React components (60+ pages) | HIGH | No unit tests |

---

## Findings Count

| Severity | Count |
|----------|-------|
| CRITICAL | 4 |
| HIGH | 6 |
| MEDIUM | 4 |
| LOW | 2 |
| **Total** | **16** |

---

## Coverage Rating

**Overall**: WARNING — 67.1% file coverage ratio

- The file coverage ratio of 67.1% is below the CLAUDE.md stated threshold of 80%.
- Structural coverage is skewed: well-tested modules (auth, permissions, encryption) create a false impression of breadth.
- 65 source modules have zero corresponding test files.
- The most critical data ingestion endpoint has no HTTP-layer tests.

**PIPELINE STATUS: BLOCKED** — Coverage is below the 80% gate specified in CLAUDE.md (`coverage_above_80`). The missing test coverage for the evidence upload endpoint and admin routes represents a blocking gap.
