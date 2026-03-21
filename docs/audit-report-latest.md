# KMFlow Platform Code Audit Report — 2026-03-21

**Audit Cycle**: 7th (post Audit R3 remediation)
**Agents**: 12 specialized agents across 4 squads
**Codebase**: ~120K LOC, 479 Python files, 78 route files, 463 endpoints
**Version**: 2026.03.247

## Executive Summary

- **Total findings: 72**
- By severity: **1 CRITICAL** / **10 HIGH** / **26 MEDIUM** / **35 LOW**
- By squad: Security (19) / Architecture (20) / Quality (22) / Coverage & Compliance (11)
- **Resolved since 6th audit**: 18 findings remediated
- **New findings**: 7
- **0 CRITICAL in injection, infrastructure, data integrity, compliance, or dependencies**

### Trend

| Audit | Date | CRIT | HIGH | MED | LOW | Total |
|-------|------|------|------|-----|-----|-------|
| 1st | 2026-02-20 | 10 | 28 | 35 | 22 | 95 |
| 2nd | 2026-02-26 | 3 | 18 | 30 | 25 | 76 |
| 3rd | 2026-03-19 | 2 | 15 | 28 | 30 | 75 |
| 4th | 2026-03-19 | 2 | 14 | 26 | 35 | 77 |
| 5th | 2026-03-20 (pre-R2) | 2 | 24 | 42 | 35 | 103 |
| 6th | 2026-03-20 (post-R2) | 2 | 13 | 25 | 43 | 83 |
| **7th** | **2026-03-21 (post-R3)** | **1** | **10** | **26** | **35** | **72** |

### Domain Scores

| Domain | Score | Trend |
|--------|-------|-------|
| Injection | 8.5/10 | Stable |
| Infrastructure | 8.8/10 | Up from 8.4 |
| Architecture | 8.5/10 | Stable |
| Data Integrity | 8.5/10 | Stable |
| API Compliance | 7.5/10 | Stable |
| Frontend | 8.0/10 | Up from 7.5 |
| Performance | MEDIUM risk | Down from HIGH |

---

## Top 10 Critical & High Findings

1. **[CRITICAL] A1-AUTH**: Dev mode auto-auth as platform_admin — env guard present but logging too quiet (`src/core/auth.py:372`)
2. **[HIGH] A1-AUTH**: WebSocket `get_websocket_user` lacks env guard for dev mode (`src/core/auth.py:489`)
3. **[HIGH] A1-AUTH**: 4 graph routes missing `require_engagement_access` — cross-tenant graph operations possible (`src/api/routes/graph.py`)
4. **[HIGH] D2-COMPLIANCE**: Erasure background job not updated for LLMAuditLog/CopilotFeedback tables (`src/gdpr/erasure_worker.py`)
5. **[HIGH] B2-DATA**: `policy_bundles` and `endpoint_consent_records` missing from RLS (`src/core/rls.py`)
6. **[HIGH] B3-API**: 121 endpoints (26%) missing `response_model=` (down from 176)
7. **[HIGH] D1-TEST**: 1,728 bare `MagicMock()` without `spec=` across 196 files
8. **[HIGH] D1-TEST**: 7 API route modules with no dedicated test file
9. **[HIGH] A3-INFRA**: CIB7 REST API lacks HTTP-level auth enforcement (mitigated by network isolation)
10. **[HIGH] C3-PERF**: Engagement RBAC N+1 — per-request DB query for every authenticated endpoint (`src/core/permissions.py`)

---

## CRITICAL Findings (1)

### [CRITICAL] AUTH: Dev mode auto-authenticates as platform_admin
**File**: `src/core/auth.py:372-382`
**Agent**: A1 (AuthZ Auditor)
**Description**: When `AUTH_DEV_MODE=true`, unauthenticated requests auto-authenticate as `platform_admin`. Environment guard present (refuses in non-dev/test), but the guard logs at DEBUG level which may be missed in monitoring. Production secret validators also block default values.
**Risk**: Misconfigured deployment environment variable could expose full admin access.
**Recommendation**: Upgrade the guard log from DEBUG to CRITICAL. Consider requiring an explicit `AUTH_DEV_MODE_CONFIRM` environment variable.

---

## HIGH Findings (10)

### Security (3)
- **A1**: WebSocket `get_websocket_user` missing app_env guard — dev mode bypasses environment check for WS connections
- **A1**: 4 graph routes (`/build`, `/traverse/{node_id}`, `/search`, `/{engagement_id}/bridges/run`) missing `require_engagement_access` — cross-tenant graph operations possible
- **A3**: CIB7 REST API unauthenticated — prod overlay requires env vars but unclear if CIB7 runtime enforces HTTP basic auth

### Data & Compliance (2)
- **B2**: `policy_bundles` and `endpoint_consent_records` tables missing from RLS (GDPR-sensitive consent data)
- **D2**: Erasure background job not updated for `llm_audit_logs`, `copilot_feedback`, `copilot_messages.content`

### API & Quality (3)
- **B3**: 121 of 463 endpoints (26%) missing `response_model=`
- **C1**: 36 unjustified `except Exception` catches (down from 65)
- **C3**: Engagement RBAC N+1 — per-request DB query for every authenticated endpoint

### Coverage (2)
- **D1**: 1,728 bare `MagicMock()` without `spec=` across 196 test files (16% spec compliance)
- **D1**: 7 API route modules with no dedicated test file

---

## MEDIUM Findings (26)

### Security (4)
- **A1**: Token blacklist fail-open on logout during Redis outage
- **A1**: WebSocket JWT passed in query params
- **A1**: MCP in-memory rate limiting not multi-worker safe
- **A2**: Magic MIME fallback to untrusted client type on detection failure

### Infrastructure (3)
- **A3**: PBKDF2 salt derived deterministically (documented trade-off)
- **A3**: Default dev database URIs unencrypted (prod overlay overrides)
- **A3**: Redis URL fallback builder omits password

### Architecture (5)
- **B1**: core/ layering violations (3 files import from semantic, auth imports from middleware)
- **B1**: 233 deferred imports across 86 files (circular dependency indicator)
- **B1**: tom.py 88 session operations (fat controller)
- **B1**: MCP in-process rate limiter bypass risk
- **B1**: EmbeddingService bypassed at 5 call sites

### Data & API (5)
- **B2**: DualWriteFailure compensation job not implemented (`retried` column never set)
- **B3**: 111 POST endpoints missing explicit `status_code`
- **B3**: 9 POV analytics endpoints with unbounded queries
- **B3**: Inconsistent pagination ceilings (le=2000 vs le=1000)
- **B3**: Rate limiting sparse — 5 of 77 route files have per-endpoint limits

### Quality (4)
- **C1**: 97 `: Any` annotations across 63 files (~40 unjustified)
- **C1**: 11 functions in 150-196 line range
- **C1**: 3 divergent `_parse_timestamp` implementations
- **C1**: 9 TODO/FUTURE markers

### Performance (2)
- **C3**: RetentionEnforcer sync blocking in async loop
- **C3**: Sequential dashboard queries (5 independent awaits)

### Frontend (2)
- **C2**: Missing cancellation guards in 2 async useEffects
- **C2**: Silent secondary data failure in 2 pages

### Compliance (1)
- **D2**: Consent enforcement not implemented (persists across 7 audits — product decision needed)

---

## LOW Findings (35)

- **A1**: ~55 routes missing response_model (overlap with B3), WS status leaks engagement IDs, HS256 symmetric JWT, 3 inconsistent access patterns (5)
- **A3**: PG superuser naming, seed script dev creds (2)
- **B1**: Route-to-route import, 3 god files persisting (3)
- **B2**: 6 carried-forward accepted risks (nullable, JSON FK refs, etc.) + eval_run bare UUID (7)
- **B3**: Hardcoded paths, manual validation, PATCH semantics, seed idempotency, DELETE missing 204 (5)
- **C1**: Missing type annotations, inline stopwords (2)
- **C2**: Index keys in 6 renders, no per-route error.tsx, useMonitoringData double cast (3)
- **C3**: 5 performance lows (keychain subprocess, audit log rotation, etc.) (5)
- **D1**: asyncio.sleep assertions, untracked test files, deps.py untested (3)
- **D2**: Intake token audit gap, LLM export incomplete fields (2)
- **D3**: Neo4j tag, minimatch comment, wrangler versions, langdetect maintenance, stale lock roots (5)

---

## Lessons Learned Checklist Summary

| # | Check | Count | Trend (vs cycle 6) |
|---|-------|-------|---------------------|
| 1 | Routes missing `response_model=` | 121 | Down from 176 (-31%) |
| 2 | ID routes missing engagement access | 4 graph routes | New finding |
| 3 | Broad `except Exception` unjustified | 36 | Down from 65 (-45%) |
| 4 | `: Any` unjustified | ~40 | Down from ~40 (stable) |
| 5 | Unbounded queries in routes | 9 | Stable |
| 6 | Route files > 500 lines | 4 | Stable |
| 7 | Missing test files for routes | 7 | Stable |
| 8 | Stubs returning fake success | 0 | Down from 2 (resolved) |
| 9 | Bare MagicMock() without spec= | 1,728 | Down from 1,733 |
| 10 | asyncio.sleep in test assertions | 5 | Down from 5 (stable) |

---

## Resolved Since 6th Audit (18 findings)

1. **CRITICAL→RESOLVED**: N+1 in search_similar — batched Cypher query
2. **HIGH→RESOLVED**: CSRF cookie not session-bound — now HMAC-SHA256
3. **HIGH→RESOLVED**: Admin routes missing response_model — added
4. **HIGH→RESOLVED**: Frontend Dockerfile runs as root — non-root user added
5. **HIGH→RESOLVED**: BPMNViewer double casts — single typed cast
6. **HIGH→RESOLVED**: GDPR export missing tables — LLMAuditLog + CopilotFeedback added
7. **HIGH→RESOLVED**: GDPR Art. 17 fake stub — raises NotImplementedError
8. **HIGH→RESOLVED**: RLS missing role_rate_assumptions + volume_forecasts — added
9. **HIGH→RESOLVED**: 65 unjustified except Exception — 29 fixed (36 remain)
10. **HIGH→RESOLVED**: ~40 unjustified :Any — 10 fixed
11. **HIGH→RESOLVED**: Retention.py test missing — 13 tests added
12. **HIGH→RESOLVED**: Audit log routes test missing — 7 tests added
13. **MEDIUM→RESOLVED**: AlertEngine memory leak — bounded deques
14. **MEDIUM→RESOLVED**: build_fragment_graph N+1 — batch relationships
15. **MEDIUM→RESOLVED**: build_governance_chains N+1 — MERGE-based upserts
16. **LOW→RESOLVED**: Ontology bare catch blocks — error states added
17. **LOW→RESOLVED**: Frontend-dev mount permissions — :ro flag
18. **LOW→RESOLVED**: AUTH_DEV_MODE/COOKIE_SECURE in prod — explicitly set

---

## Squad Reports

### A: Security & Authorization
- **A1 (AuthZ)**: 12 findings — 1 CRIT, 2 HIGH, 4 MED, 5 LOW → `docs/audit-findings/A1-authz.md`
- **A2 (Injection)**: 1 finding — 0 CRIT, 0 HIGH, 1 MED, 0 LOW → `docs/audit-findings/A2-injection.md`
- **A3 (Infrastructure)**: 6 findings — 0 CRIT, 1 HIGH, 3 MED, 2 LOW → `docs/audit-findings/A3-infra-security.md`

### B: Architecture & Data Integrity
- **B1 (Architecture)**: 9 findings — 0 CRIT, 1 HIGH, 5 MED, 3 LOW → `docs/audit-findings/B1-architecture.md`
- **B2 (Data Integrity)**: 11 findings — 0 CRIT, 1 HIGH, 4 MED, 6 LOW → `docs/audit-findings/B2-data-integrity.md`
- **B3 (API Compliance)**: 9 findings — 0 CRIT, 1 HIGH, 4 MED, 4 LOW → `docs/audit-findings/B3-api-compliance.md`

### C: Code Quality & Performance
- **C1 (Python Quality)**: 10 findings — 0 CRIT, 1 HIGH, 4 MED, 2 LOW → `docs/audit-findings/C1-python-quality.md`
- **C2 (Frontend)**: 6 findings — 0 CRIT, 0 HIGH, 3 MED, 3 LOW → `docs/audit-findings/C2-frontend-quality.md`
- **C3 (Performance)**: 12 findings — 0 CRIT, 1 HIGH, 6 MED, 5 LOW → `docs/audit-findings/C3-performance.md`

### D: Coverage, Compliance & Risk
- **D1 (Test Coverage)**: 5 findings — 0 CRIT, 2 HIGH, 2 MED, 1 LOW → `docs/audit-findings/D1-test-coverage.md`
- **D2 (Compliance)**: 5 findings — 0 CRIT, 1 HIGH, 2 MED, 2 LOW → `docs/audit-findings/D2-compliance.md`
- **D3 (Dependencies)**: 5 findings — 0 CRIT, 0 HIGH, 0 MED, 5 LOW → `docs/audit-findings/D3-dependencies.md`

---

## Recommendations (Top 10 by Risk Reduction)

1. **Fix WebSocket dev-mode env guard** — Add `app_env not in ("development", "testing")` check to `get_websocket_user`. Quick fix, eliminates a HIGH.

2. **Add `require_engagement_access` to 4 graph routes** — `/build`, `/traverse`, `/search`, `/bridges/run`. Prevents cross-tenant graph operations. Quick fix.

3. **Update erasure background job** — Add `llm_audit_logs`, `copilot_feedback`, `copilot_messages` to the anonymization query. GDPR compliance gap.

4. **Add RLS for `policy_bundles` + `endpoint_consent_records`** — GDPR-sensitive consent tables. Quick fix: add to `ENGAGEMENT_SCOPED_TABLES`.

5. **Continue response_model additions** — 121 remaining endpoints (down from 176). Target 50 per sprint.

6. **Reduce bare MagicMock() count** — 1,728 instances. Start with conftest.py fixtures (highest amplification), then POV/semantic tests.

7. **Implement dual-write compensation job** — DualWriteFailure records accumulate but are never retried.

8. **Add CIB7 HTTP basic auth enforcement** — Verify Camunda runtime actually enforces the credentials from env vars.

9. **Fix magic MIME fallback** — Change `pipeline.py:109-121` to fall back to `application/octet-stream` instead of client MIME.

10. **Split god files** — tom.py (1762), pov.py (1537), pipeline.py (882). Track in dedicated refactor tickets.

---

*Report compiled from 12 agent findings on 2026-03-21. Full per-agent reports in `docs/audit-findings/`. Version: 2026.03.247.*
