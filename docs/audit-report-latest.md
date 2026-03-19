# KMFlow Platform Code Audit Report — 2026-03-19

**Classification**: Confidential — Security Audit Finding
**Auditor**: Claude Opus 4.6 (12 specialized agents, 4 squads)
**Prior Audits**: 2026-02-20, 2026-02-26

## Executive Summary

- **Total findings**: 107
- **By severity**: 6 CRITICAL / 34 HIGH / 37 MEDIUM / 30 LOW
- **By squad**: Security (21) / Architecture (28) / Quality (35) / Coverage & Compliance (23)
- **Agents deployed**: 12 (5 Opus, 7 Sonnet)
- **Prior audit resolved**: 7 findings remediated since 2026-02-26

### Trend Since Prior Audit

| Metric | 2026-02-26 | 2026-03-19 | Trend |
|--------|------------|------------|-------|
| CRITICAL | 2 | 6 | +4 (expanded scope, new regressions) |
| HIGH | 18 | 34 | +16 (expanded scope — 456 endpoints vs 210) |
| Resolved | — | 7 | Improvements |
| New | — | 6 | New regressions |

### Key Corrections to Pre-Identified Findings

The audit corrected 3 of the 10 pre-identified findings:
1. `require_engagement_access()` IS actively used across 44 route files (not dead code)
2. MCP `verify_api_key()` DOES perform DB lookup with HMAC comparison (not format-only)
3. JWT in `localStorage` was RESOLVED — auth is now exclusively via HttpOnly cookies

---

## Top 10 Critical & High Findings

| # | Severity | Finding | File | Agent |
|---|----------|---------|------|-------|
| 1 | **CRITICAL** | `search_similar()` queries non-existent `fragment_embeddings` table — silently returns empty | `src/semantic/graph.py:587` | B2 |
| 2 | **CRITICAL** | N+1 embedding UPDATEs — batch method exists but not wired in | `src/evidence/pipeline.py:539` | C3 |
| 3 | **CRITICAL** | In-memory rate limiter ineffective in multi-worker deployments | `src/api/middleware/security.py:95` | B3 |
| 4 | **CRITICAL** | `generate_gap_probes` returns HTTP 201 but creates nothing in DB | `src/api/routes/gap_probes.py:82` | B3 |
| 5 | **CRITICAL** | `fail_under = 70` — 20 points below mandatory 90% threshold | `pyproject.toml:115` | D1 |
| 6 | **CRITICAL** | `debug: bool = True` default with incomplete production guard | `src/core/config.py:34` | C1 |
| 7 | **HIGH** | Conflict resolution routes entirely unauthenticated (5 endpoints) | `src/api/routes/conflicts.py:99` | A1 |
| 8 | **HIGH** | XXE regression in financial regulatory parser (missing safe XMLParser) | `src/evidence/parsers/financial_regulatory_parser.py:213` | A2 |
| 9 | **HIGH** | MCP tool handlers bypass engagement-level authorization | `src/mcp/server.py:155` | A1 |
| 10 | **HIGH** | AlertEngine unbounded in-memory lists — slow memory leak | `src/monitoring/alerting/engine.py:448` | C3 |

---

## CRITICAL Findings

### [CRITICAL] DATA-INTEGRITY: `search_similar()` queries non-existent table
**File**: `src/semantic/graph.py:587-594`
**Agent**: B2 (Data Integrity Auditor)
**Evidence**:
```python
pgvector_query = text(
    "SELECT id, entity_id, entity_type, "
    "1 - (embedding <=> :embedding::vector) AS similarity "
    "FROM fragment_embeddings "  # Table does not exist!
    "WHERE (:engagement_id IS NULL OR engagement_id = :engagement_id::uuid) "
    "ORDER BY embedding <=> :embedding::vector "
    "LIMIT :top_k"
)
```
**Description**: Queries table `fragment_embeddings` which doesn't exist in any migration or ORM model. Actual table is `evidence_fragments`. Also references non-existent columns. Exception swallowed by broad `except Exception` on line 634, silently returning empty results.
**Risk**: Semantic search via graph service is completely broken. Users get no results with no error indication.
**Recommendation**: Rewrite query to use `evidence_fragments` table with correct column names. Fix the broad exception catch.

---

### [CRITICAL] PERFORMANCE: N+1 embedding UPDATEs — batch method exists but not called
**File**: `src/evidence/pipeline.py:539`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
for frag, embedding in zip(valid_fragments, embeddings, strict=True):
    try:
        await semantic_service.store_embedding(session, str(frag.id), embedding)
        stored += 1
    except (ValueError, ConnectionError, RuntimeError) as e:
        logger.warning("Failed to store embedding for fragment %s: %s", frag.id, e)
```
**Description**: Sequential per-fragment UPDATE loop. `store_embeddings_batch()` already exists in `embeddings.py:131` and does this in a single `executemany` call.
**Risk**: 100-fragment document = 100 sequential database round-trips during upload.
**Recommendation**: Replace loop with single call to `semantic_service.store_embeddings_batch()`.

---

### [CRITICAL] API-COMPLIANCE: In-memory rate limiter ineffective in multi-worker deployments
**File**: `src/api/middleware/security.py:95`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP rate limiter.
    Note: This is per-process only. In multi-worker deployments the
    effective limit is ``workers * max_requests``."""
```
**Description**: Three separate rate-limiting mechanisms all use process-local memory. In N-worker deployment, effective limits multiply by N. Auth `/login` (5 req/min) becomes N*5.
**Risk**: Brute-force protection and LLM cost controls negated in production.
**Recommendation**: Replace with Redis-backed atomic counters using `INCR` + `EXPIRE`. Redis client already available on `app.state`.

---

### [CRITICAL] API-COMPLIANCE: `generate_gap_probes` stub returns 201 but creates nothing
**File**: `src/api/routes/gap_probes.py:82`
**Agent**: B3 (API Compliance Auditor)
**Evidence**:
```python
    """Generate gap-targeted probes for an engagement.
    TODO: Persist generated probes to database for stable IDs and
    referenceability by survey bot. Currently recomputes on every call."""
```
**Description**: Returns HTTP 201 Created but creates nothing in the database. Downstream survey bot integration is silently broken.
**Risk**: Callers expecting a resource with stable IDs receive none.
**Recommendation**: Either persist probes or change status code to 200 and document results as ephemeral.

---

### [CRITICAL] TEST-COVERAGE: `fail_under = 70` below mandatory 90% threshold
**File**: `pyproject.toml:115`
**Agent**: D1 (Test Coverage Auditor)
**Evidence**:
```toml
[tool.coverage.report]
fail_under = 70
```
**Description**: CI gate set 20 points below mandatory minimum. Actual coverage is ~84% but regressions to 71% would pass silently.
**Risk**: Coverage erosion undetected by CI.
**Recommendation**: Raise to at minimum 80% immediately (per CLAUDE.md), targeting 90%.

---

### [CRITICAL] CONFIG: `debug: bool = True` default with incomplete production guard
**File**: `src/core/config.py:34`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
app_env: str = "development"
debug: bool = True
neo4j_password: str = "neo4j_dev_password"
postgres_password: str = "kmflow_dev_password"
```
**Description**: `debug=True` has no production guard. `neo4j_password` and `postgres_password` not checked by `reject_default_secrets_in_production`. If `APP_ENV` left as `"development"`, all defaults silently accepted.
**Risk**: Misconfigured environment exposes stack traces and accepts known-weak passwords.
**Recommendation**: Add database passwords to production validator. Guard debug flag outside development.

---

## HIGH Findings

### Squad A: Security & Authorization

#### [HIGH] MISSING_AUTH: Conflict Resolution Routes Unauthenticated
**File**: `src/api/routes/conflicts.py:99-364`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/engagements/{engagement_id}/conflicts", response_model=ConflictListResponse)
async def list_conflicts(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
```
**Description**: All 5 endpoints lack any authentication. Any unauthenticated caller can read, resolve, and escalate conflicts across all engagements.
**Risk**: Information disclosure, data integrity violation, denial of service via mass escalations.
**Recommendation**: Add `Depends(require_engagement_access)` to engagement-scoped endpoints.

---

#### [HIGH] MISSING_AUTHZ: MCP Tool Handlers Bypass Engagement Isolation
**File**: `src/mcp/server.py:155-329`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def _tool_get_engagement(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        result = await session.execute(select(Engagement).where(Engagement.id == eid))
```
**Description**: API key validated, but authenticated client info never passed to tool handlers. Any valid API key accesses any engagement's data.
**Risk**: Any valid MCP API key holder can access data from any engagement, violating multi-tenant isolation.
**Recommendation**: Pass `client["user_id"]` into tool handlers and verify engagement membership.

---

#### [HIGH] XXE-REGRESSION: Unsafe XML Parsing in Financial Regulatory Parser
**File**: `src/evidence/parsers/financial_regulatory_parser.py:213`
**Agent**: A2 (Injection Auditor)
**Evidence**:
```python
async def _parse_xml(self, file_path: str, file_name: str) -> ParseResult:
    from lxml import etree
    with open(file_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    try:
        root = etree.fromstring(content.encode())  # Missing safe XMLParser!
```
**Description**: `etree.fromstring()` without safe XMLParser. All other parsers use `XMLParser(resolve_entities=False, no_network=True)`. One-line fix.
**Risk**: XXE attack via crafted regulatory XML upload.
**Recommendation**: Add `parser = etree.XMLParser(resolve_entities=False, no_network=True)` and pass to `fromstring()`.

---

#### [HIGH] SECRETS: Config Fields Not Using SecretStr
**File**: `src/core/config.py:42-70`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
postgres_password: str = "kmflow_dev_password"
neo4j_password: str = "neo4j_dev_password"
jwt_secret_key: str = "dev-secret-key-change-in-production"
encryption_key: str = "dev-encryption-key-change-in-production"
watermark_signing_key: str = "dev-watermark-key-change-in-production"
```
**Description**: Five security-critical fields are plain `str` instead of `SecretStr`. `databricks_token` already demonstrates the correct pattern.
**Risk**: Accidental exposure of secrets in logs, debug output, or error traces.
**Recommendation**: Change to `SecretStr` type. Update code to call `.get_secret_value()`.

---

### Squad B: Architecture & Data Integrity

#### [HIGH] GOD-FILE: `tom.py` — 2274 lines, 35 handlers, 51 inline schemas
**File**: `src/api/routes/tom.py`
**Agent**: B1 (Architecture Auditor)
**Description**: Largest route file. Covers TOMs, gap analysis, best practices, benchmarks, roadmaps, maturity scoring, alignment runs, and conformance checking. Tripled in schema count since Feb.
**Recommendation**: Split into sub-routers. Extract schemas to `src/api/schemas/tom.py`.

---

#### [HIGH] GOD-FILE: `pov.py` — 1875 lines, 22 handlers, 35 inline schemas
**File**: `src/api/routes/pov.py`
**Agent**: B1 (Architecture Auditor)
**Description**: Second largest route file. Redis job management logic mixed with route logic.
**Recommendation**: Split into `pov/generation.py`, `pov/models.py`, `pov/confidence.py`, etc.

---

#### [HIGH] SCHEMA-COUPLING: 14+ route files define 200+ schemas inline
**File**: Multiple route files
**Agent**: B1 (Architecture Auditor)
**Description**: Only `simulations.py` and `taskmining.py` use `src/api/schemas/`. Violates project coding standards.
**Recommendation**: Extract schemas for top 6 route files by size.

---

#### [HIGH] NEO4J-DEAD-CODE: Graph cleanup method exists but never called
**File**: `src/semantic/graph.py:663-680`
**Agent**: B2 (Data Integrity Auditor)
**Description**: `delete_engagement_subgraph()` implemented but never invoked from retention or deletion paths.
**Risk**: Neo4j accumulates orphaned graph data for deleted engagements. GDPR violation.
**Recommendation**: Call from retention cleanup and engagement delete routes.

---

#### [HIGH] PAGINATION: Multiple list endpoints without bounds
**Files**: `users.py:350`, `cost_modeling.py:129,174`
**Agent**: B3 (API Compliance Auditor)
**Description**: Unbounded SELECT queries. `total: len(items)` pattern produces wrong totals.
**Recommendation**: Add `limit`/`offset` params; use separate `COUNT(*)` query for total.

---

### Squad C: Code Quality & Performance

#### [HIGH] EXCEPTION: 56 unjustified `except Exception` catches
**File**: Multiple
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
# src/core/auth.py:431 — silent swallow on blacklist check
try:
    if await is_token_blacklisted(websocket, jwt_token):
        return None
except Exception:
    return None  # no log — exception type and message lost entirely
```
**Description**: Most severe: `core/auth.py:431` silently swallows blacklist check errors. Redis failure and code bug produce identical invisible behavior.
**Recommendation**: Catch specific exceptions. Log at minimum `logger.warning` before returning.

---

#### [HIGH] STUBS: Fabricated responses from stub implementations
**Files**: `taskmining/worker.py:43`, `security/consent/service.py:96`
**Agent**: C1 (Python Quality Auditor)
**Evidence**:
```python
if task_type == "aggregate":
    return {"status": "aggregated"}  # fabricated — no actual aggregation occurs

deletion_task_id = uuid.uuid4()
return {"status": "withdrawal_accepted", "deletion_task_id": str(deletion_task_id)}
# ID is never stored or tracked
```
**Description**: Worker returns `"aggregated"` without aggregating. Consent service generates deletion UUID that's never dispatched.
**Risk**: GDPR erasure request acknowledged but never executed.
**Recommendation**: Implement dispatch or change response to document deferred state.

---

#### [HIGH] N+1-GRAPH: CO_OCCURS_WITH and semantic bridges — per-pair Neo4j writes
**Files**: `pipeline.py:466`, `bridges/process_evidence.py:110` + 3 others
**Agent**: C3 (Performance Auditor)
**Description**: O(N^2) Neo4j sessions. `batch_create_relationships()` exists but not used.
**Risk**: Up to 5,000 sequential Neo4j transactions for 50 process + 100 evidence nodes.
**Recommendation**: Collect tuples and call `batch_create_relationships()` once per bridge.

---

#### [HIGH] MEMORY-LEAK: AlertEngine unbounded in-memory lists
**File**: `src/monitoring/alerting/engine.py:448`
**Agent**: C3 (Performance Auditor)
**Evidence**:
```python
class AlertEngine:
    def __init__(self, ...):
        self.alerts: list[Alert] = []
        self._notification_log: list[dict[str, Any]] = []
```
**Description**: Every alert and notification accumulated without eviction. `query_alerts` scans full list on every API call.
**Risk**: Memory growth and degrading query performance over process lifetime.
**Recommendation**: Persist to DB. Use `deque(maxlen=1000)` for notification log.

---

### Squad D: Coverage, Compliance & Risk

#### [HIGH] MISSING-TESTS: GDPR erasure worker `execute()` untested
**File**: `src/gdpr/erasure_worker.py`
**Agent**: D1 (Test Coverage Auditor)
**Description**: Cross-store coordination (PG + Neo4j + Redis) has zero test coverage. PG-only helper tested; wrapper is not.
**Risk**: Erasure bugs in Neo4j or Redis purge paths undetected.

---

#### [HIGH] AUDIT-TRAIL: HttpAuditEvent silently discards IP, user agent, resource type
**Files**: `src/core/audit.py:62-72`, `src/core/models/audit.py:145-169`
**Agent**: D2 (Compliance Auditor)
**Evidence**:
```python
event = HttpAuditEvent(
    method=method, path=path, user_id=user_id,
    status_code=status_code, engagement_id=engagement_id,
    duration_ms=duration_ms,
    # ip_address, user_agent, resource_type — silently dropped
)
```
**Description**: Middleware extracts IP, user agent, and resource type from every request, but `HttpAuditEvent` model has no columns for them.
**Risk**: Critical forensic data lost. Investigators must cross-reference app logs with DB.
**Recommendation**: Add columns to model. Create migration. Pass values through.

---

#### [HIGH] LOCK-FILE: requirements.lock stale — cryptography violates declared floor
**Files**: `requirements.lock:30-34`, `pyproject.toml:54`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```
# requirements.lock
cryptography==43.0.3

# pyproject.toml
"cryptography>=46.0.5,<48.0",
```
**Description**: Lock file last regenerated in PR #175 (Feb 2026). Six CVE remediation PRs updated `pyproject.toml` but none regenerated the lock. CVE floor packages `pyopenssl`, `pyasn1`, `pypdf` absent from lock entirely.
**Risk**: Lock-file-based installs get vulnerable cryptography version.
**Recommendation**: Regenerate with `uv pip compile --generate-hashes`. Wire into Dockerfile.

---

## MEDIUM Findings

| # | Category | Title | File | Agent |
|---|----------|-------|------|-------|
| 1 | Security | Watermark signing key not validated in production | `config.py:70` | A1 |
| 2 | Security | Hardcoded development credentials in config defaults | `config.py:42-70` | A1 |
| 3 | Injection | File type detection falls back to client MIME type | `pipeline.py:105` | A2 |
| 4 | Injection | Delta Lake delete predicate string interpolation | `backend.py:396` | A2 |
| 5 | Injection | ServiceNow table name URL injection | `servicenow.py:85` | A2 |
| 6 | Injection | LLM history injection via unsanitized history | `copilot.py:150` | A2 |
| 7 | Infra | Source volume mounts without `:ro` flag | `docker-compose.yml:222` | A3 |
| 8 | Infra | Fixed PBKDF2 salt in encryption | `encryption.py:29` | A3 |
| 9 | Infra | Unencrypted database connections | `config.py:48` | A3 |
| 10 | Infra | Production overlay missing CIB7/MinIO/Mailpit overrides | `docker-compose.prod.yml` | A3 |
| 11 | Arch | 60+ deferred imports hide dependency graph | Multiple | B1 |
| 12 | Arch | Dashboard in-memory cache breaks stateless design | `dashboard.py:54` | B1 |
| 13 | Arch | Evidence pipeline 865 lines spanning 5 concerns | `pipeline.py` | B1 |
| 14 | Arch | HTTPException raised from service layer | `pipeline.py:19` | B1 |
| 15 | Arch | Duplicate `_check_engagement_member` in tom.py | `tom.py:60` | B1 |
| 16 | Data | PDPAuditEntry.policy_id has no FK constraint | `pdp.py:165` | B2 |
| 17 | Data | JSON array columns store FK references (carried) | Multiple | B2 |
| 18 | Data | Engagement lacks ORM cascade for 21+ children (carried) | Multiple | B2 |
| 19 | Data | No CHECK constraints on score columns (carried) | Multiple | B2 |
| 20 | Data | Actor columns use String instead of FK (carried) | Multiple | B2 |
| 21 | Data | Missing HNSW on pattern_library_entries (carried) | Multiple | B2 |
| 22 | API | Auth endpoints not account-level rate limited | `auth.py:116` | B3 |
| 23 | API | Governance policies endpoint exposes filesystem path | `governance.py:330` | B3 |
| 24 | API | TOM endpoints missing response_model | `tom.py:533` | B3 |
| 25 | API | Governance export missing responses declaration | `governance.py:389` | B3 |
| 26 | API | Inconsistent pagination ceiling (100-2000) | Multiple | B3 |
| 27 | API | seed_lists.py DELETE returns 200 instead of 204 | `seed_lists.py:161` | B3 |
| 28 | Quality | 5 TODO comments in source code | Multiple | C1 |
| 29 | Quality | Duplicate `_parse_timestamp` — 3 copies, divergent behavior | Multiple | C1 |
| 30 | Quality | `Any` for datetime fields in 16 Pydantic schemas | Multiple | C1 |
| 31 | Frontend | Form inputs without labels (accessibility) | `FinancialTab.tsx:116` | C2 |
| 32 | Frontend | Icon-only delete button — no accessible name | `FinancialTab.tsx:228` | C2 |
| 33 | Frontend | Hardcoded engagement UUID in navigation | `AppShell.tsx:64` | C2 |
| 34 | Frontend | eslint-disable without justification | `conformance/page.tsx:64` | C2 |
| 35 | Perf | Graph stats query not scoped on target node | `graph.py:777` | C3 |
| 36 | Perf | Full file read into memory before validation | `evidence.py:179` | C3 |
| 37 | Perf | Graph expansion over-fetches top_k * 10 nodes | `retrieval.py:355` | C3 |
| 38 | Coverage | Security modules no dedicated test directory | `src/security/` | D1 |
| 39 | Coverage | No concurrency tests for auth/rate-limiting | Multiple | D1 |
| 40 | Coverage | Pipeline integration test 70% mocking | `test_pipeline_integration.py` | D1 |
| 41 | Coverage | Cookie auth tests fragmented across files | Multiple | D1 |
| 42 | Coverage | 39 model files with 1 partial test file | `tests/core/test_models.py` | D1 |
| 43 | Compliance | DataClassification stored but not enforced | `evidence.py:129` | D2 |
| 44 | Compliance | AlternativeSuggestion stores prompts permanently | `suggester.py:144` | D2 |
| 45 | Compliance | Audit log immutability gap — docstring claims nonexistent trigger | `audit.py:104` | D2 |
| 46 | Compliance | Consent not enforced before processing | `copilot.py:83` | D2 |
| 47 | Deps | Agent pyproject.toml allows vulnerable PyJWT | `agent/python/pyproject.toml:13` | D3 |
| 48 | Deps | CVE floor packages absent from lock file | `requirements.lock` | D3 |
| 49 | Deps | Coverage threshold inconsistent with standard | `pyproject.toml:114` | D3 |
| 50 | Deps | Lock file lacks hash verification | `requirements.lock` | D3 |
| 51 | Deps | bpmn-js watermark preservation not verified | `BPMNViewer.tsx` | D3 |

---

## LOW Findings

| # | Category | Title | File | Agent |
|---|----------|-------|------|-------|
| 1 | Auth | Deployment capabilities endpoint unauthenticated | `deployment.py:19` | A1 |
| 2 | Injection | Internal file paths exposed in API responses | `evidence.py:54` | A2 |
| 3 | Injection | Salesforce timestamp unsanitized in SOQL | `salesforce.py:177` | A2 |
| 4 | Infra | Redis URL built without password when not set | `config.py:216` | A3 |
| 5 | Infra | Descope project ID hardcoded in worker source | `index.ts:299` | A3 |
| 6 | Infra | AUTH_DEV_MODE enabled in docker compose | `docker-compose.yml:217` | A3 |
| 7 | Infra | Superuser password fallback in compose | `docker-compose.yml:12` | A3 |
| 8 | Arch | Embedding service singleton bypassed | `embeddings.py:24` | B1 |
| 9 | Arch | Background task sets may leak references | Multiple | B1 |
| 10 | Arch | 77 route files registered procedurally | `main.py:34` | B1 |
| 11 | Data | Pipeline quality models missing explicit nullable=False | `pipeline_quality.py:40` | B2 |
| 12 | Data | JSON column default mismatch (carried) | Multiple | B2 |
| 13 | Data | Hardcoded 768 dimension (carried) | Multiple | B2 |
| 14 | Data | SuccessMetric not engagement-scoped (carried) | Multiple | B2 |
| 15 | API | Router prefix missing on 3 route files | `users.py:31` | B3 |
| 16 | API | Manual depth validation instead of Query() | `graph.py:180` | B3 |
| 17 | API | TOM seed endpoint not idempotent | `tom.py:503` | B3 |
| 18 | API | Rate limit 429 body format inconsistent | `security.py:155` | B3 |
| 19 | API | PATCH archive without request body | `engagements.py:270` | B3 |
| 20 | Quality | 90-entry stopwords set inline in method body | `retrieval.py:244` | C1 |
| 21 | Quality | TaskProgress available but not imported | `runner.py:118` | C1 |
| 22 | Frontend | No per-route error.tsx files | `frontend/src/app/` | C2 |
| 23 | Frontend | Inline style for dynamic height | `graph/page.tsx:82` | C2 |
| 24 | Frontend | OntologyGraph synchronous cytoscape import | `OntologyGraph.tsx:4` | C2 |
| 25 | Frontend | Sidebar toggle missing aria-expanded | `AppShell.tsx:255` | C2 |
| 26 | Perf | Embedding vectors as ASCII strings | `embeddings.py:124` | C3 |
| 27 | Perf | Default pool settings unsafe for multi-worker | `database.py:39` | C3 |
| 28 | Perf | In-process rate limiter state not shared | `security.py:95` | C3 |
| 29 | Coverage | audit_logs PLATFORM_ADMIN route untested | `audit_logs.py:80` | D1 |
| 30 | Coverage | test_pipeline.py covers only 2 utility functions | `test_pipeline.py` | D1 |
| 31 | Coverage | Agent tests use wall-clock time.time() | `test_auth.py:87` | D1 |
| 32 | Compliance | Pattern anonymizer PII detection incomplete | `anonymizer.py:17` | D2 |
| 33 | Compliance | Retention cleanup disabled by default | `config.py:103` | D2 |
| 34 | Compliance | No DPA template or tracking | `config.py:100` | D2 |
| 35 | Deps | minio/mc uses floating :latest tag | `docker-compose.yml` | D3 |
| 36 | Deps | Base images use floating minor tags | `Dockerfile.backend:1` | D3 |
| 37 | Deps | minimatch override required for CVE | `package.json:41` | D3 |
| 38 | Deps | Wrangler version inconsistency across workers | Multiple | D3 |
| 39 | Deps | langdetect at end of active maintenance | `pyproject.toml:48` | D3 |

---

## Squad Reports

### A: Security & Authorization

**Overall Security Score: 7.5/10**

#### A1: Authorization & Authentication (5 findings: 2 HIGH, 2 MEDIUM, 1 LOW)
- JWT authentication, token blacklisting, cookie security, and RBAC are well-implemented
- `require_engagement_access()` actively enforced across 44 route files (correcting pre-identified finding)
- MCP API key authentication performs proper DB lookup with HMAC (correcting pre-identified finding)
- **Gaps**: Conflict routes unauthenticated; MCP tool handlers skip engagement isolation

#### A2: Injection & Input Validation (7 findings: 1 HIGH, 4 MEDIUM, 2 LOW)
- No SQL injection, XSS, command injection, or CSRF vectors found
- Cypher injection protection solid with label whitelisting and parameterized values
- **XXE regression**: New parser added after prior remediation wave, missed safe XMLParser
- 1 prior finding (Cypher injection in traversal) fully remediated

#### A3: Infrastructure Security (9 findings: 1 HIGH, 4 MEDIUM, 4 LOW)
- Score improved from 7.9/10 to 8.3/10 — XSS and init script credentials remediated
- Container hardening excellent: `no-new-privileges`, `cap_drop: ALL`, resource limits
- CORS now uses explicit origins, methods, headers
- **Main gap**: 5 secret fields as plain `str` instead of `SecretStr`

### B: Architecture & Data Integrity

#### B1: Architecture (11 findings: 3 HIGH, 5 MEDIUM, 3 LOW)
- Prior CRITICAL (async/sync mixing) fully resolved
- Prior HIGH (1717-line models.py) resolved — split into 33 domain modules
- No circular dependencies or upward layering violations
- **New god files**: `tom.py` (2274 lines) and `pov.py` (1875 lines)

#### B2: Data Integrity (14 findings: 1 CRITICAL, 3 HIGH, 6 MEDIUM, 4 LOW)
- Migration chain (001-087) fully linear with no gaps
- All ForeignKey definitions have explicit `ondelete` policies
- pgvector dimension (768) consistent throughout
- **Critical**: `search_similar()` queries non-existent table

#### B3: API Compliance (18 findings: 2 CRITICAL, 5 HIGH, 6 MEDIUM, 5 LOW)
- 456 endpoints across 76 files with ~95% response format consistency
- Pagination bounds on ~92% of list endpoints
- HTTP status codes correct on ~98% of endpoints
- Code quality score: 7.0/10

### C: Code Quality & Performance

#### C1: Python Quality (11 findings: 1 CRITICAL, 5 HIGH, 3 MEDIUM, 2 LOW)
- Zero bare `except:`, zero `datetime.utcnow()`, zero f-string loggers
- Structured logging with `__name__` throughout
- Fail-closed authentication pattern
- **Concerns**: 56 broad catches, 154 `: Any`, 2 fabricated stubs

#### C2: Frontend Quality (11 findings: 0 CRITICAL, 3 HIGH, 4 MEDIUM, 4 LOW)
- Prior CRITICAL (localStorage JWT) fully resolved
- No `dangerouslySetInnerHTML`, no `console.log`
- Error boundaries on high-risk visualization components
- AbortController in 24/25 data-fetching files

#### C3: Performance (12 findings: 1 CRITICAL, 4 HIGH, 4 MEDIUM, 3 LOW)
- Async foundation sound
- Batch infrastructure built but not wired to callers
- AlertEngine unbounded memory growth
- Performance risk: HIGH

### D: Coverage, Compliance & Risk

#### D1: Test Coverage (10 findings: 1 CRITICAL, 3 HIGH, 4 MEDIUM, 3 LOW)
- 341 test files, ~5,941 test functions, 77.2% file ratio
- Critical auth paths well-tested
- **Gaps**: Coverage threshold too low; 10 routes untested; GDPR cross-store erasure untested

#### D2: Compliance (10 findings: 0 CRITICAL, 3 HIGH, 4 MEDIUM, 3 LOW)
- Prior CRITICAL (GDPR erasure) fully resolved
- GDPR export now comprehensive (6 sources)
- 4 findings persisted across all 3 audits (require architectural decisions)

#### D3: Dependencies (13 findings: 0 CRITICAL, 2 HIGH, 6 MEDIUM, 5 LOW)
- JavaScript supply chain healthy
- **Python supply chain gap**: Lock file stale; CVE floor packages absent; Dockerfile non-deterministic

---

## Recommendations

### Top 10 Highest-Impact Actions (Ranked by Risk Reduction)

| Priority | Action | Findings Resolved | Effort |
|----------|--------|-------------------|--------|
| 1 | **Fix `search_similar()` phantom table query** | B2-CRITICAL | Low (1 hour) |
| 2 | **Wire batch APIs to callers** — embeddings + graph relationships | C3-CRITICAL + 2 C3-HIGH | Medium (1 day) |
| 3 | **Move rate limiting to Redis** | B3-CRITICAL + C3-LOW | Medium (1 day) |
| 4 | **Add auth to conflict routes + MCP engagement scoping** | A1-HIGH x2 | Low (half day) |
| 5 | **Fix XXE regression** — add safe XMLParser to financial_regulatory_parser | A2-HIGH | Low (1 hour) |
| 6 | **Regenerate requirements.lock + wire into Dockerfile** | D3-HIGH x2 | Low (half day) |
| 7 | **Raise `fail_under` to 80+** | D1-CRITICAL + D3-MEDIUM | Low (5 min) |
| 8 | **Add `debug` and DB password guards + migrate to SecretStr** | C1-CRITICAL + A3-HIGH | Medium (half day) |
| 9 | **Cap AlertEngine memory** — persist to DB or use deque(maxlen) | C3-HIGH | Low (half day) |
| 10 | **Split tom.py and pov.py** — extract schemas, create sub-routers | B1-HIGH x3 | High (2-3 days) |

---

*Report generated by 12 autonomous audit agents (5 Opus, 7 Sonnet) on 2026-03-19.*
*Individual agent reports available in `docs/audit-findings/`.*
