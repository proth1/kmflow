# KMFlow Platform Code Audit Report — 2026-02-20

## Executive Summary

A comprehensive code audit of the KMFlow platform was performed by 12 specialized agents across 4 squads. The audit covered ~170 Python files, 70 TypeScript files, ~188 API endpoints, and 18 backend modules.

| Metric | Value |
|--------|-------|
| **Total findings** | **156** |
| CRITICAL | 19 |
| HIGH | 50 |
| MEDIUM | 56 |
| LOW | 31 |

### By Squad

| Squad | Scope | Findings | CRIT | HIGH | MED | LOW |
|-------|-------|----------|------|------|-----|-----|
| **A: Security** | Auth, injection, infra | 38 | 6 | 11 | 14 | 7 |
| **B: Architecture** | Architecture, data, API | 40 | 3 | 13 | 15 | 9 |
| **C: Quality** | Python, frontend, perf | 38 | 3 | 14 | 14 | 7 |
| **D: Coverage** | Tests, compliance, deps | 40 | 7 | 12 | 13 | 8 |

### Audit Verdict: NOT DEPLOYMENT READY

The platform has well-designed authentication infrastructure and clean module boundaries, but critically lacks **multi-tenant isolation enforcement**, has **broken auth rate limiting**, **unsafe XML parsing**, and **no GDPR data subject rights**. These must be remediated before any production consideration.

---

## Top 10 Critical & High Findings

| # | Sev | Finding | File | Agent |
|---|-----|---------|------|-------|
| 1 | **CRIT** | `require_engagement_access()` defined but never called — multi-tenant isolation is dead code. ~130 endpoints across 21 route files are unprotected. | `src/core/permissions.py:188` | A1 |
| 2 | **CRIT** | MCP `verify_api_key()` validates format only (`kmflow_*.xxx`), no DB lookup. Any forged key authenticates. | `src/mcp/auth.py:129-144` | A1 |
| 3 | **CRIT** | Direct Cypher query endpoint accepts arbitrary queries. Write-keyword blocklist bypassable via APOC procedures. | `src/api/routes/graph.py:187-215` | A2 |
| 4 | **CRIT** | XXE vulnerability in BPMN, XES, and Visio parsers — `lxml.etree.parse()` with default settings resolves external entities. ARIS parser correctly uses `defusedxml`. | `src/evidence/parsers/bpmn_parser.py:54` | A2 |
| 5 | **CRIT** | Redis container deployed without authentication. Any process on Docker network has full read/write/flush access. | `docker-compose.yml:57-75` | A3 |
| 6 | **CRIT** | Default `dev-secret-key` for JWT and encryption with no production startup validation. `auth_dev_mode` defaults `True`. | `src/core/config.py:61-67` | A3 |
| 7 | **CRIT** | `slowapi` rate limiter on auth endpoints is never registered — `@limiter.limit("5/minute")` silently fails, leaving brute-force protection non-functional. | `src/api/routes/auth.py:40-41` | B3 |
| 8 | **CRIT** | Alembic migrations 005 and 006 both descend from 004 — branched revision chain. `alembic upgrade head` fails on fresh DB. | `alembic/versions/005*.py, 006*.py` | B2 |
| 9 | **CRIT** | Evidence upload API (`POST /evidence/upload`) — the primary data ingestion path — has zero HTTP-level tests. | `src/api/routes/evidence.py:129` | D1 |
| 10 | **CRIT** | No GDPR data subject rights: no user deletion endpoint, no data export, no consent tracking, no privacy policy references. | `src/api/routes/users.py` | D2 |

---

## CRITICAL Findings (19)

### Security (Squad A)

**A1-01: Multi-tenancy isolation dead code** — `require_engagement_access()` is fully implemented in `permissions.py` but never imported or used by any of the 26 route files. All routes use `require_permission()` which checks global roles but NOT engagement membership. Any authenticated user can access ANY engagement's data. ~130 endpoints across 21 route files affected.
- File: `src/core/permissions.py:188`
- Risk: Complete tenant isolation bypass

**A1-02: MCP API key validation accepts any format match** — `verify_api_key()` checks `kmflow_*.xxx` format only. The async `validate_api_key()` with DB lookup exists but is never called from the MCP server.
- File: `src/mcp/auth.py:129-144`
- Risk: Unauthenticated MCP access to all engagement data

**A2-01: Arbitrary Cypher query endpoint** — `POST /api/v1/graph/query` accepts user-supplied Cypher with a trivially bypassable keyword blocklist. APOC procedures, FOREACH, LOAD CSV all bypass the filter.
- File: `src/api/routes/graph.py:187-215`
- Risk: Full graph DB read/write by any `engagement:read` user

**A2-02: XXE in XML parsers** — `bpmn_parser.py`, `xes_parser.py`, `visio_parser.py` use `lxml.etree.parse()` with default settings (entities resolved). The `# noqa: S320` comment on BPMN parser shows awareness but no fix.
- File: `src/evidence/parsers/bpmn_parser.py:54`, `xes_parser.py:45`, `visio_parser.py:71`
- Risk: Server-side file disclosure via malicious evidence uploads

**A3-01: Redis without authentication** — No `requirepass` in dev or prod docker-compose. Redis URL uses no password. Port 6380 mapped to host.
- File: `docker-compose.yml:57-75`
- Risk: Unauthenticated data access/manipulation on Docker network

**A3-02: Default secrets accepted in production** — `jwt_secret_key = "dev-secret-key-change-in-production"`, `encryption_key = "dev-encryption-key-change-in-production"`, `auth_dev_mode = True`. No startup validation.
- File: `src/core/config.py:61-67`
- Risk: Token forgery, data decryption, auth bypass if env vars not set

### Architecture & Data (Squad B)

**B2-01: Branched migration chain** — Migrations 005 and 006 both have `down_revision = "004"`, creating two heads. `alembic upgrade head` fails on fresh database.
- File: `alembic/versions/005_create_security_tables.py:17`, `006_create_pov_tables.py:19`
- Risk: Database setup failure, potentially missing `users` table

**B2-02: Missing FK ondelete on 4 columns** — `MetricReading.metric_id`, `MetricReading.engagement_id`, `Annotation.engagement_id`, `AlternativeSuggestion.created_by` lack `ondelete` — engagement deletion will fail.
- File: `src/core/models.py:930-931, 948, 1484`
- Risk: GDPR data deletion blocked by FK violations

**B3-01: Auth rate limiter silently non-functional** — `slowapi.Limiter` decorators on auth endpoints (`5/min`) never fire because `app.state.limiter` and `SlowAPIMiddleware` are never registered.
- File: `src/api/routes/auth.py:40-41`, `src/api/main.py:172-176`
- Risk: No brute-force protection on authentication endpoints

### Quality (Squad C)

**C1-01: Silent exception swallowing** — 4 locations catch `Exception` and `pass` with no logging. Graph relationship creation failures and Databricks warehouse discovery silently lost.
- File: `src/semantic/builder.py:365,382,399`, `src/datalake/databricks_backend.py:227`
- Risk: Silent data loss in knowledge graph

**C2-01: JWT in localStorage** — `localStorage.getItem("kmflow_token")` — any XSS allows token exfiltration.
- File: `frontend/src/lib/api.ts:22`
- Risk: Full account takeover via XSS

**C3-01: N+1 query in batch validation** — One DB query per evidence ID in a loop with no batch size limit.
- File: `src/api/routes/evidence.py:342`
- Risk: Request timeouts at realistic batch sizes

### Coverage & Compliance (Squad D)

**D1-01: Evidence upload endpoint untested** — Primary data ingestion path has zero HTTP-level tests despite test file claiming coverage.
- File: `src/api/routes/evidence.py:129`
- Risk: Regressions undetected in CI

**D1-02: Token blacklist never unit-tested** — `is_token_blacklisted` and `blacklist_token` have no direct tests. Redis-unavailable fail-closed behavior unverified.
- File: `src/core/auth.py:149`
- Risk: Revoked tokens may remain usable

**D1-03: Admin routes entirely untested** — Retention cleanup and encryption key rotation have no tests for RBAC enforcement, confirmation header, or dry-run mode.
- File: `src/api/routes/admin.py:25`
- Risk: Destructive operations without safety verification

**D1-04: Data retention logic untested** — Cutoff calculation, timezone handling, and status-based filtering unverified.
- File: `src/core/retention.py:20`
- Risk: GDPR compliance failure

**D2-01: Multiple route modules mutate without AuditLog** — users.py, monitoring.py, patterns.py, annotations.py, conformance.py, metrics.py, portal.py all perform session.add/delete without database audit records.
- File: `src/api/routes/users.py:98-302` (and 6 other route files)
- Risk: Incomplete audit trail for SOC2/SOX compliance

**D2-02: No GDPR data subject rights** — No DELETE user endpoint, no data export, no consent tracking. Zero matches for `gdpr`, `privacy`, `consent`, `data.export` in codebase.
- File: `src/api/routes/users.py`
- Risk: GDPR Arts. 15, 17, 20 non-compliance

**D2-03: LLM prompts/responses stored permanently** — `AlternativeSuggestion.llm_prompt` and `CopilotMessage.content` store full client data with no TTL or retention limit.
- File: `src/core/models.py:1482-1483`
- Risk: Data minimization violation, breach exposure

---

## HIGH Findings (50)

### Squad A: Security (11)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | Refresh tokens accepted as access tokens — `get_current_user` never checks token `type` claim | `src/core/auth.py:190-260` | A1 |
| 2 | Default JWT secret in config with no production startup validation | `src/core/config.py:61` | A1 |
| 3 | IDOR — any authenticated user can view any user's profile | `src/api/routes/users.py:159-173` | A1 |
| 4 | WebSocket auth: no blacklist check, no engagement membership, no token type check | `src/api/routes/websocket.py:105-134` | A1 |
| 5 | LLM prompt injection — user queries injected unsanitized into copilot prompts | `src/rag/copilot.py:93-97` | A2 |
| 6 | SOQL injection — unsanitized f-string interpolation in Salesforce queries | `src/integrations/salesforce.py:108,153` | A2 |
| 7 | Cypher injection via unvalidated property keys in graph service | `src/semantic/graph.py:175-176` | A2 |
| 8 | CORS: `allow_methods=["*"]`, `allow_headers=["*"]` with `allow_credentials=True` | `src/api/main.py:162-168` | A3 |
| 9 | Hardcoded credentials in docker-compose (Postgres, Camunda, MinIO) | `docker-compose.yml:12,85,110-111,136` | A3 |
| 10 | Backend Docker container runs as root, `--reload` in production CMD | `Dockerfile.backend:1-21` | A3 |
| 11 | Missing HSTS and Content-Security-Policy headers | `src/api/middleware/security.py:52-63` | A3 |

### Squad B: Architecture & Data (13)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | God file: `models.py` is 1717 lines with 76 classes | `src/core/models.py:1-1717` | B1 |
| 2 | God file: `simulations.py` is 1309 lines with 27 inline schemas | `src/api/routes/simulations.py:1-1309` | B1 |
| 3 | Layering violation: `core/` modules depend on FastAPI framework | `src/core/auth.py:20`, `permissions.py:13` | B1 |
| 4 | Migration 010 stores embedding as LargeBinary but ORM uses Vector(768) — type mismatch | `alembic/versions/010*.py:52` vs `models.py:1258` | B2 |
| 5 | Neo4j property key injection — keys interpolated into Cypher without validation | `src/semantic/graph.py:175-176,230-233` | B2 |
| 6 | Orphan risk: only 3 of 18+ child tables have ORM cascade from Engagement | `src/core/models.py:502-503` | B2 |
| 7 | Migration 018 creates FK without ondelete — user deletion blocked | `alembic/versions/018*.py:101-106` | B2 |
| 8 | 12+ list endpoints missing pagination — unbounded `.all()` queries | Multiple route files | B3 |
| 9 | `list_patterns` and `search_patterns` report page size as `total`, not dataset count | `src/api/routes/patterns.py:146-165` | B3 |
| 10 | DELETE `/engagements/{id}` returns 200 with body instead of 204 | `src/api/routes/engagements.py:265-284` | B3 |
| 11 | `/health` endpoint not versioned under `/api/v1/` | `src/api/routes/health.py:18` | B3 |
| 12 | TOM/metrics/regulatory write endpoints use `engagement:read` permission | `src/api/routes/tom.py:192-211` (and others) | B3 |
| 13 | Governance `/catalog` returns raw list instead of `{items, total}` wrapper | `src/api/routes/governance.py:146-164` | B3 |

### Squad C: Quality & Performance (14)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | 25 broad `except Exception:` catches across 15 files | Multiple files | C1 |
| 2 | 76 `Any` type annotations in 38 files — timestamps, scenarios, sessions | Multiple files | C1 |
| 3 | 30 functions exceed 50 lines (worst: 223 lines) | Multiple files | C1 |
| 4 | 3 god classes exceed 300 lines (worst: 448 lines) | `builder.py`, `graph.py`, `databricks_backend.py` | C1 |
| 5 | Duplicate `_log_audit` function copy-pasted across 3 route modules | `tom.py:173`, `regulatory.py:173`, `simulations.py:239` | C1 |
| 6 | No React ErrorBoundary anywhere — render exceptions crash entire app | `frontend/src/app/layout.tsx:14` | C2 |
| 7 | `api.ts` is 1694 lines (past its own 1500-line TODO threshold) | `frontend/src/lib/api.ts:1-1694` | C2 |
| 8 | `AnnotationPanel` makes unauthenticated API calls (raw fetch, no auth headers) | `frontend/src/components/AnnotationPanel.tsx:48-57` | C2 |
| 9 | Pervasive `any` types in BPMNViewer and GraphExplorer | `BPMNViewer.tsx`, `GraphExplorer.tsx` | C2 |
| 10 | N+1: Neo4j node creation opens one session per node in loops | `src/semantic/builder.py:175` | C3 |
| 11 | N+1: Entity extraction runs sequentially per fragment instead of concurrent | `src/semantic/builder.py:147` | C3 |
| 12 | Unbounded query: `get_engagement_subgraph` fetches all nodes without LIMIT | `src/semantic/graph.py:429` | C3 |
| 13 | Multiple list endpoints fetch all rows with no LIMIT | `simulations.py:303`, `engagements.py:344` | C3 |
| 14 | Memory leak: rate limiter `_llm_request_log` unbounded dict, O(N) eviction scan | `src/api/routes/simulations.py:56` | C3 |

### Squad D: Coverage & Compliance (12)

| # | Finding | File | Agent |
|---|---------|------|-------|
| 1 | WebSocket authentication untested | `src/api/routes/websocket.py:105` | D1 |
| 2 | Audit logging middleware untested | `src/api/middleware/audit.py:20` | D1 |
| 3 | Per-user copilot rate limiter untested | `src/core/rate_limiter.py:20` | D1 |
| 4 | 8 monitoring subsystem modules untested (worker, collector, detector, events, notification) | `src/monitoring/` | D1 |
| 5 | Evidence upload intelligence pipeline over-mocked — no real-object integration tests | `tests/evidence/test_pipeline_integration.py` | D1 |
| 6 | Frontend: 65 source files, only 5 unit test files | `frontend/src/` | D1 |
| 7 | Audit middleware logs to app logger only, not database | `src/api/middleware/audit.py:50-58` | D2 |
| 8 | Security events without engagement_id dropped from database | `src/core/audit.py:59-69` | D2 |
| 9 | Retention cleanup only archives, doesn't delete evidence (misleading docstring) | `src/core/retention.py:44-61` | D2 |
| 10 | No LLM output validation before return to user | `src/rag/copilot.py:126-159` | D2 |
| 11 | PII logging via f-strings in MCP auth module | `src/mcp/auth.py:54,83,89,96` | D2 |
| 12 | No Python lock file — non-reproducible builds | `pyproject.toml` | D3 |

---

## MEDIUM Findings (56)

### Squad A: Security (14)

- Unauthenticated WebSocket status endpoint leaks engagement IDs (`websocket.py:260`)
- Unauthenticated MCP `/info` and `/tools` endpoints expose tool definitions (`mcp/server.py:43-51`)
- List engagement members has no access control beyond authentication (`users.py:305`)
- `auth_dev_mode` defaults to True — dev login endpoint exposed in production (`config.py:66`)
- Admin key rotation error response leaks internal exception details (`admin.py:96-99`)
- File type detection falls back to client MIME type when python-magic unavailable (`pipeline.py:97-106`)
- `application/octet-stream` in MIME allowlist accepts any file type (`pipeline.py:78`)
- Visio parser doesn't validate zip entry paths (`visio_parser.py:54-70`)
- Cypher write-keyword blocklist bypassable via APOC/FOREACH/LOAD CSV (`graph.py:199-206`)
- Reflected XSS in Cloudflare worker login page error parameter (`index.ts:628`)
- In-memory rate limiter unbounded growth, trusts X-Forwarded-For (`security.py:79-128`)
- OpenAPI docs exposed unconditionally in production (`main.py:155-156`)
- Source code volume mounts in dev compose without `:ro` (`docker-compose.yml:187-189`)
- Weak key derivation — SHA-256 without salt/iterations (`encryption.py:22-29`)

### Squad B: Architecture & Data (15)

- In-memory rate limiter in simulations.py not shared across workers (`simulations.py:56`)
- 67 deferred imports across 14 files indicate coupling pressure (`pipeline.py`, `simulations.py`, etc.)
- Missing service layer — route handlers directly instantiate services (`simulations.py:495-500`)
- 150+ Pydantic schemas co-located in route files (`simulations.py`, `tom.py`, etc.)
- Frontend monolith: `api.ts` is 1694 lines with 82 functions and 98 types (`api.ts:1-1694`)
- Frontend god component: `simulations/page.tsx` is 1247 lines (`simulations/page.tsx:1-1247`)
- Migration ORM-vs-migration drift on MetricReading ondelete (`models.py:930` vs `014*.py`)
- 119 nullable=True columns across ~40 models — overly permissive schema (`models.py`)
- Missing indexes on frequently queried FK columns (`evidence_fragments.evidence_id`, etc.)
- BestPractice and Benchmark tables lack uniqueness constraints (`models.py:853-886`)
- Graph.py error response leaks Neo4j internals (`graph.py:208-215`)
- `POST /graph/build` returns 202 but executes synchronously (`graph.py:144-145`)
- In-memory rate limiter not shared across workers (`simulations.py:49-80`)
- Audit logs endpoint returns unbounded results (`engagements.py:332-345`)
- Governance catalog response format inconsistent with other list endpoints (`governance.py:146-164`)

### Squad C: Quality & Performance (14)

- Deprecated `datetime.utcnow()` in `mcp/auth.py:93`
- f-strings in logger calls — 6 occurrences in `mcp/auth.py`
- 145 inline imports inside function bodies across 20+ files
- `_sanitize_filename` duplicated 3 times across storage backends
- `_headers()` method duplicated across 5 integration connectors
- Accessibility: buttons missing aria-label in GraphExplorer
- Accessibility: simulation form inputs missing labels
- Simulations page: 1247-line god component with 20+ state variables
- `EvidenceUploader` stale closure bug in upload index tracking
- Embedding generation batches sequentially instead of concurrently
- File content loaded entirely into memory (up to 100MB) before validation
- No caching on EmbeddingService — new model load per request
- Neo4j: one session per query, no session reuse in bulk operations
- Dashboard endpoint makes 6 sequential DB queries with no caching

### Squad D: Coverage & Compliance (13)

- Semantic bridges (4 modules) entirely untested
- Integration connectors (7 modules) entirely untested
- Trivial `assert X is not None` assertions in critical POV tests
- MCP server and tools untested
- CopilotMessage stores user queries indefinitely with no retention policy
- DataClassification enum exists but never enforced at access time
- System prompt not protected against extraction via user queries
- Suggester uses hardcoded model version and raw HTTP calls (not SDK)
- No immutability guarantee on audit log records — cascade-deleted with engagement
- Frontend deps use caret ranges (no exact pinning)
- Build-time packages (Tailwind, PostCSS) in production dependencies
- `cryptography` package imported but not declared as explicit dependency
- PR #127 regression: raw httpx call bypasses Anthropic SDK with hardcoded model

---

## LOW Findings (31)

### Squad A (7)
- Deprecated `datetime.utcnow()` in MCP auth
- MCP auth logs key_id/user_id — PII correlation in logs
- No Docker container security options (no-new-privileges, cap_drop)
- CIB7 Camunda engine has no authentication
- All service ports mapped to host in dev compose
- Internal file paths exposed in evidence API response
- Error detail leakage in graph and copilot HTTP responses

### Squad B (9)
- Sync file I/O inside async methods in storage backends
- No dependency injection for Neo4j driver — `request.app.state` pattern
- Route handlers return `dict[str, Any]` despite declaring `response_model`
- Alembic.ini contains plaintext database credentials
- pgvector dimension hardcoded in 4 locations (consistent but fragile)
- Neo4j read queries use `session.run()` instead of `execute_read()`
- Status filter parameter inconsistently named across routes
- Missing response model on 7+ TOM endpoints
- Camunda routes not fully reviewed for pattern consistency

### Squad C (7)
- `print()` in validate.py and migration_cli.py (acceptable for CLI)
- TODO comment in api.ts past its own threshold
- Inline styles mixed with Tailwind in BPMNViewer/GraphExplorer
- `useDataLoader` silences errors on initial load
- Vector embedding stored as string rather than native pgvector type
- Pool size may be undersized for high concurrency (20+10 per worker)
- `cosine_similarity` uses pure Python loops instead of numpy

### Squad D (8)
- Playwright E2E tests are superficial (page-load only, no user journeys)
- No coverage threshold enforced in CI (`--cov-fail-under` missing)
- No data processing agreement references in codebase
- Engagement `retention_days` optional with no default
- Pattern anonymizer PII detection regex-based and incomplete
- GitHub Actions CI removed, no automated dependency scanning gate
- `minimatch` override for historical CVE remediation
- `aiofiles` version cap may be too tight

---

## Squad Reports

### A: Security & Authorization

**Agents**: A1 (AuthZ), A2 (Injection), A3 (Infra Security)
**Total findings**: 38 (6 CRITICAL, 11 HIGH, 14 MEDIUM, 7 LOW)
**Overall security score**: 3/10

The platform has well-designed authentication infrastructure (JWT with rotation, bcrypt hashing, token blacklisting, rate limiting skeleton) but critically lacks enforcement of engagement-level authorization. The RBAC system gates by role (what actions) but not by scope (which engagements). The MCP authentication is trivially bypassable, XML parsing is unsafe in 3 of 4 XML parsers, and infrastructure defaults are insecure.

**Positive controls**: No SQL injection (ORM throughout), no `dangerouslySetInnerHTML`, no `eval()`/`pickle.load()`, CSRF mitigated by JSON bodies, SSRF mitigated by configured base URLs, good content hash integrity, rate limiting skeleton exists.

### B: Architecture & Data Integrity

**Agents**: B1 (Architecture), B2 (Data Integrity), B3 (API Compliance)
**Total findings**: 40 (3 CRITICAL, 13 HIGH, 15 MEDIUM, 9 LOW)
**Architecture risk**: MEDIUM

The architecture follows sound layering principles with 17 well-named domain packages and no circular imports. However, several files have grown beyond maintainable size (models.py 1717 lines, simulations.py 1309 lines, api.ts 1694 lines), the core layer is coupled to FastAPI, schemas are co-located with routes, and the migration chain has a branch. Database FK cascades are 70% covered but with critical gaps. API compliance is generally good but 12+ list endpoints lack pagination.

**Positive areas**: Clean module boundaries, consistent 201/204 status codes, request ID tracing, structured error responses, proper CORS origin restriction.

### C: Code Quality & Performance

**Agents**: C1 (Python Quality), C2 (Frontend Quality), C3 (Performance)
**Total findings**: 38 (3 CRITICAL, 14 HIGH, 14 MEDIUM, 7 LOW)
**Performance risk**: HIGH

Code quality is generally solid (no bare excepts, no mutable defaults, consistent type annotations) but has significant debt in error handling breadth and `Any` type overuse. The frontend lacks error boundaries and has a critical token storage vulnerability. Performance is the highest-risk area: N+1 queries in batch validation and graph construction, unbounded list queries, sequential entity extraction, and no caching on frequently-read endpoints.

**Positive areas**: No TODO/FIXME markers, proper async patterns generally, AbortController cleanup in frontend hooks, good accessibility in EvidenceUploader.

### D: Coverage, Compliance & Risk

**Agents**: D1 (Test Coverage), D2 (Compliance), D3 (Dependencies)
**Total findings**: 40 (7 CRITICAL, 12 HIGH, 13 MEDIUM, 8 LOW)

Test coverage ratio is 67.1% (98 test files / 146 source modules) — below the 80% CLAUDE.md threshold. 65 source modules have zero tests. The most critical data ingestion endpoint is untested. GDPR compliance is absent (no data subject rights, no consent tracking). Audit trail is incomplete (7 route modules mutate without AuditLog). LLM interactions stored permanently with no retention policy. Dependencies have 0 CVEs but no Python lock file.

**Positive areas**: 1,475 test functions, 0 known CVEs, good auth/permissions test coverage, encryption key rotation exists, data classification enum exists (needs enforcement).

---

## Recommendations

Top 10 highest-impact actions ranked by risk reduction:

| # | Action | Addresses | Effort | Risk Reduction |
|---|--------|-----------|--------|----------------|
| 1 | **Add `require_engagement_access` to all engagement-scoped routes** | A1-01 (CRIT) — multi-tenant bypass | Medium (21 route files) | Extreme |
| 2 | **Fix MCP auth to use async `validate_api_key` with DB lookup** | A1-02 (CRIT) — MCP bypass | Low (1 file) | High |
| 3 | **Replace `lxml.etree.parse()` with `defusedxml` in 3 parsers** | A2-02 (CRIT) — XXE | Low (3 files) | High |
| 4 | **Add startup validation rejecting default secrets in production** | A3-02 (CRIT) — token forgery | Low (1 file) | High |
| 5 | **Register slowapi middleware or replace with Redis-based auth rate limiting** | B3-01 (CRIT) — brute force | Low (1-2 files) | High |
| 6 | **Fix alembic migration chain (merge or linearize 005/006)** | B2-01 (CRIT) — DB setup failure | Low (1 migration) | High |
| 7 | **Add Redis `requirepass` and update connection URLs** | A3-01 (CRIT) — unauthenticated Redis | Low (2 files) | High |
| 8 | **Remove or restrict Cypher query endpoint** | A2-01 (CRIT) — arbitrary DB access | Low (1 file) | High |
| 9 | **Migrate JWT from localStorage to HttpOnly cookies** | C2-01 (CRIT) — XSS token theft | Medium (frontend + backend) | High |
| 10 | **Add Python lock file (poetry.lock or pinned requirements.txt)** | D3-01 (HIGH) — supply chain | Low (1 command) | Medium |

### Secondary Priority (next 10)

11. Add `ondelete="CASCADE"` to 4 FK columns missing it
12. Add ErrorBoundary components to React frontend
13. Add tests for evidence upload endpoint, admin routes, token blacklist
14. Implement GDPR data subject rights (deletion, export, consent)
15. Fix TOM/regulatory write endpoints to require write permissions
16. Add HSTS and CSP headers to security middleware
17. Add pagination to 12+ unbounded list endpoints
18. Batch Neo4j operations using UNWIND instead of per-node sessions
19. Run backend container as non-root user
20. Split `models.py` into domain-specific model modules
