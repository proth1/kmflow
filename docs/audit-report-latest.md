# KMFlow Platform Code Audit Report — 2026-03-20

**Audit Cycle**: 6th (post Audit R2 remediation)
**Agents**: 12 specialized agents across 4 squads
**Codebase**: ~113K LOC, 479 Python files, 76 route files, 463 endpoints

## Executive Summary

- **Total findings: 83**
- By severity: **2 CRITICAL** / **13 HIGH** / **25 MEDIUM** / **43 LOW**
- By squad: Security (23) / Architecture (20) / Quality (34) / Coverage & Compliance (16)
- **Resolved since last audit**: 28 findings remediated across all categories
- **New findings**: 12 (vs 28 resolved — net improvement)

### Trend

| Audit | Date | CRIT | HIGH | MED | LOW | Total |
|-------|------|------|------|-----|-----|-------|
| 1st | 2026-02-20 | 10 | 28 | 35 | 22 | 95 |
| 2nd | 2026-02-26 | 3 | 18 | 30 | 25 | 76 |
| 3rd | 2026-03-19 | 2 | 15 | 28 | 30 | 75 |
| 4th | 2026-03-19 | 2 | 14 | 26 | 35 | 77 |
| 5th | 2026-03-20 (pre-R2) | 2 | 24 | 42 | 35 | 103 |
| **6th** | **2026-03-20 (post-R2)** | **2** | **13** | **25** | **43** | **83** |

### Domain Scores

| Domain | Score | Trend |
|--------|-------|-------|
| Injection | 8.5/10 | Up from 7.5 |
| Infrastructure | 8.4/10 | Stable |
| Architecture | 8.5/10 | Up from 8.0 |
| Data Integrity | 8.5/10 | Up from 7.9 |
| API Compliance | 7.5/10 | Improved (prior CRITs resolved) |
| Frontend | 7.5/10 | Stable |

---

## Top 10 Critical & High Findings

1. **[CRITICAL] C3-PERF**: N+1 graph read in `search_similar` — one Neo4j call per pgvector result row (`src/semantic/graph.py:612`)
2. **[CRITICAL] A1-AUTH**: Dev mode auto-auth as platform_admin — misconfigured deployment could expose full admin access (`src/core/auth.py:372`)
3. **[HIGH] D1-TEST**: 1,733 bare `MagicMock()` without `spec=` across 195 test files — attribute typos pass silently
4. **[HIGH] C1-QUALITY**: 65 unjustified `except Exception` catches concentrated in semantic/, pipeline_quality, websocket modules
5. **[HIGH] C1-QUALITY**: 12 god classes >300 lines — `KnowledgeGraphService` at 728 lines
6. **[HIGH] C1-QUALITY**: GDPR Art. 17 stub returns `deletion_task_id` but no deletion is dispatched (`src/security/consent/service.py:96`)
7. **[HIGH] B3-API**: 176 of 463 endpoints (38%) missing `response_model=`
8. **[HIGH] B2-DATA**: 2 engagement-scoped tables (`role_rate_assumptions`, `volume_forecasts`) missing from RLS policy list
9. **[HIGH] A3-INFRA**: CIB7 REST API lacks HTTP-level authentication — any process on backend-net can deploy workflows
10. **[HIGH] A3-INFRA**: Frontend Dockerfile runs as root (backend Dockerfile correctly uses non-root `appuser`)

---

## CRITICAL Findings (2)

### [CRITICAL] PERF: N+1 graph read in `search_similar`
**File**: `src/semantic/graph.py:612`
**Agent**: C3 (Performance Auditor)
**Description**: Each pgvector similarity result triggers an individual Neo4j `get_node()` call. For a query returning 50 results, this means 50 sequential Neo4j round-trips. Should batch into a single Cypher query with `IN` clause.

### [CRITICAL] AUTH: Dev mode auto-authenticates as platform_admin
**File**: `src/core/auth.py:372-382`
**Agent**: A1 (AuthZ Auditor)
**Description**: When `AUTH_DEV_MODE=true`, unauthenticated requests auto-authenticate as `platform_admin`. Protected by startup validator in production, but a misconfigured deployment environment variable could expose full admin access to all endpoints.

---

## HIGH Findings (13)

### Security (5)
- **A1**: Token blacklisting silently fails during Redis outage — refreshed tokens remain valid
- **A1**: CSRF cookie not cryptographically bound to session — stolen cookie usable cross-session
- **A1**: Admin routes lack response_model filtering — potential over-exposure of internal fields
- **A3**: CIB7 REST API unauthenticated on backend-net — any container can deploy BPMN workflows
- **A3**: Frontend Dockerfile `runner` stage runs as root

### Architecture & Data (2)
- **B1**: `tom.py` (1762 lines) and `pov.py` (1537 lines) remain god files, still growing
- **B2**: `role_rate_assumptions` and `volume_forecasts` tables missing from RLS policy list

### Quality (5)
- **C1**: 65 unjustified broad `except Exception` catches
- **C1**: 12 god classes >300 lines (`KnowledgeGraphService` at 728 lines)
- **C1**: GDPR Art. 17 deletion stub — no actual deletion dispatched
- **C1**: ~40 unjustified `: Any` scalar parameter annotations
- **C2**: BPMNViewer 6x `as unknown as BpmnViewer` double casts bypass type safety

### Coverage (3)
- **B3**: 176 endpoints (38%) missing `response_model=`
- **D1**: 1,733 bare `MagicMock()` without `spec=` (16% spec compliance)
- **D1**: 7 API route modules with no dedicated test file + agent GDPR `retention.py` untested

### Compliance (1)
- **D2**: GDPR data export missing LLMAuditLog and CopilotFeedback tables

---

## MEDIUM Findings (25)

### Security (5)
- **A1**: WebSocket JWT passed in query params (logged in access logs)
- **A1**: MCP rate limiting uses in-memory dict (not multi-worker safe)
- **A1**: Refresh cookie path fragility
- **A2**: Magic MIME fallback to untrusted client type on detection failure
- **A3**: PBKDF2 salt derived deterministically from secret (documented trade-off)

### Architecture & Data (9)
- **A3**: Default dev database URIs use unencrypted transport
- **A3**: Redis URL fallback builder omits password
- **B1**: 4 route files (tom, pov, simulations, taskmining) growing toward 500-line threshold
- **B2**: No compensation job for dual-write failures (DualWriteFailure table accumulates)
- **B3**: 111 POST endpoints missing explicit `status_code`
- **B3**: 7 POV analytics endpoints with unbounded queries
- **B3**: Inconsistent pagination ceilings across API
- **B3**: Rate limiting sparse — only 3 of ~463 endpoints have per-user limits

### Quality (7)
- **C1**: 10 TODO/FUTURE markers across 7 files
- **C1**: 17 functions in 150-196 line range
- **C1**: 3 divergent `_parse_timestamp` implementations remain
- **C1**: Pydantic schemas using `Any` for datetime fields
- **C2**: Missing cancellation guards in 2 async useEffects
- **C2**: Secondary data load failures silently swallowed in 2 pages
- **C2**: No `role="status"` on loading containers (accessibility)

### Performance (2)
- **C3**: Sequential dashboard queries in pipeline_quality (5 independent awaits)
- **C3**: Sync blocking in async loop (retention.py enforce_now)

### Compliance (2)
- **D2**: Consent enforcement not implemented (persists across 5 audits — product decision needed)
- **D2**: `list_evidence()` classification gap for CLIENT_VIEWER role

---

## LOW Findings (43)

### Security (9)
- **A1**: ~55 routes missing `response_model` (overlap with B3 count)
- **A1**: WebSocket status endpoint leaks engagement IDs
- **A1**: HS256 symmetric JWT algorithm
- **A3**: 4 infrastructure low-severity items

### Architecture & Data (10)
- **B1**: 3 architecture observations (route-to-route import, etc.)
- **B2**: 6 carried-forward accepted risks (nullable columns, JSON FK refs, etc.)
- **B3**: 4 API compliance lows (hardcoded paths, manual validation, PATCH semantics, duplicate seeds)

### Quality (14)
- **C1**: 2 functions missing type annotations, inline stopwords set
- **C2**: 4 index-key violations, no per-route `error.tsx`, ontology bare catch, citation index key
- **C3**: 5 performance lows (keychain subprocess, audit log rotation, etc.)

### Coverage & Compliance (10)
- **D1**: asyncio.sleep assertions remain, untracked test files
- **D2**: Intake token + copilot feedback audit gaps, anonymization incomplete for new tables
- **D3**: 4 dependency lows (Neo4j tag, minimatch CVE comment, wrangler versions, langdetect)

---

## Lessons Learned Checklist Summary

| # | Check | Count | Trend |
|---|-------|-------|-------|
| 1 | Routes missing `response_model=` | 176 | Down from 200+ |
| 2 | ID routes missing engagement access | 0 significant | Resolved |
| 3 | Broad `except Exception` unjustified | 65 | Down from 80+ |
| 4 | `: Any` unjustified | ~40 | Down from 148 |
| 5 | Unbounded queries in routes | 9 | Down from 15+ |
| 6 | Route files > 500 lines | 4 | Stable |
| 7 | Missing test files for routes | 7 | Down from 10+ |
| 8 | Stubs returning fake success | 2 | Down from 8 |
| 9 | Bare MagicMock() without spec= | 1,733 | Stable |
| 10 | asyncio.sleep in test assertions | 5 | Down from 28 |

---

## Squad Reports

### A: Security & Authorization
- **A1 (AuthZ)**: 13 findings — 1 CRIT, 3 HIGH, 4 MED, 5 LOW → `docs/audit-findings/A1-authz.md`
- **A2 (Injection)**: 1 finding — 0 CRIT, 0 HIGH, 1 MED, 0 LOW → `docs/audit-findings/A2-injection.md`
- **A3 (Infrastructure)**: 9 findings — 0 CRIT, 2 HIGH, 3 MED, 4 LOW → `docs/audit-findings/A3-infra-security.md`

### B: Architecture & Data Integrity
- **B1 (Architecture)**: 8 findings — 0 CRIT, 1 HIGH, 4 MED, 3 LOW → `docs/audit-findings/B1-architecture.md`
- **B2 (Data Integrity)**: 11 findings — 0 CRIT, 1 HIGH, 4 MED, 6 LOW → `docs/audit-findings/B2-data-integrity.md`
- **B3 (API Compliance)**: 9 findings — 0 CRIT, 1 HIGH, 4 MED, 4 LOW → `docs/audit-findings/B3-api-compliance.md`

### C: Code Quality & Performance
- **C1 (Python Quality)**: 10 findings — 0 CRIT, 4 HIGH, 4 MED, 2 LOW → `docs/audit-findings/C1-python-quality.md`
- **C2 (Frontend)**: 8 findings — 0 CRIT, 1 HIGH, 3 MED, 4 LOW → `docs/audit-findings/C2-frontend-quality.md`
- **C3 (Performance)**: 16 findings — 1 CRIT, 4 HIGH, 6 MED, 5 LOW → `docs/audit-findings/C3-performance.md`

### D: Coverage, Compliance & Risk
- **D1 (Test Coverage)**: 6 findings — 0 CRIT, 3 HIGH, 2 MED, 1 LOW → `docs/audit-findings/D1-test-coverage.md`
- **D2 (Compliance)**: 5 findings — 0 CRIT, 1 HIGH, 2 MED, 2 LOW → `docs/audit-findings/D2-compliance.md`
- **D3 (Dependencies)**: 4 findings — 0 CRIT, 0 HIGH, 0 MED, 4 LOW → `docs/audit-findings/D3-dependencies.md`

---

## Recommendations (Top 10 by Risk Reduction)

1. **Batch-fix N+1 in `search_similar`** — Replace per-row Neo4j calls with single `WHERE id IN [...]` Cypher query. Eliminates the only CRITICAL performance finding.

2. **Add `response_model=` to remaining 176 endpoints** — Prevents over-serialization, enables OpenAPI docs. Largest single finding by count. Track incrementally (top 50 per sprint).

3. **Fix GDPR Art. 17 deletion stub** — `consent/service.py:96` returns task ID but dispatches nothing. Implement actual deletion or raise `NotImplementedError`. Compliance risk.

4. **Add RLS for `role_rate_assumptions` and `volume_forecasts`** — Financial rate data is competitively sensitive. Quick fix: add to `ENGAGEMENT_SCOPED_TABLES` list.

5. **Add Basic auth to CIB7 in production** — Any container on backend-net can deploy workflows. Add `CAMUNDA_USER`/`CAMUNDA_PASSWORD` enforcement in prod overlay.

6. **Fix frontend Dockerfile to run as non-root** — Add `adduser`/`USER` directive matching backend pattern. Quick win.

7. **Implement dual-write compensation job** — `DualWriteFailure` table records failures but never retries. Add periodic job to retry `retried=false` rows.

8. **Reduce bare `MagicMock()` count** — 1,733 unspec'd mocks risk silent test rot. Prioritize conftest.py fixtures (highest amplification) and POV/semantic tests.

9. **Split god files** — `tom.py` (1762 lines) and `pov.py` (1537 lines) need sub-router decomposition. Track in dedicated refactor PRs.

10. **Add per-endpoint rate limits to LLM-heavy routes** — `tom.py` alignment, `semantic.py` extraction, `reports.py` generation have no rate limits but call expensive LLM APIs.

---

*Report compiled from 12 agent findings on 2026-03-20. Full per-agent reports in `docs/audit-findings/`.*
