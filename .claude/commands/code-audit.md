# KMFlow Comprehensive Code Audit

You are the **audit lead** for a comprehensive code audit of the KMFlow platform. Your job is to orchestrate 12 specialized audit agents across 4 squads, compile their findings into a single structured report, and save it to `docs/audit-report-latest.md`.

## Rules

- Do NOT create GitHub issues
- Do NOT fix anything
- Do NOT modify any source files
- Report findings ONLY
- Save the final report to `docs/audit-report-latest.md`

## Execution Plan

### Phase 1: Create the team and task list

Create a team called `code-audit` using TeamCreate. Then create 12 tasks (one per agent) plus a final compilation task. Set up dependencies so the compilation task is blocked by all 12 agent tasks.

### Phase 2: Spawn all 12 agents in parallel (4 squads)

Launch all 12 agents simultaneously using the Task tool. Each agent writes its findings to a dedicated file under `docs/audit-findings/` (create this directory first). Each agent MUST use the exact finding format specified below.

**IMPORTANT**: Every agent prompt must include these instructions:
1. This is a READ-ONLY audit. Do NOT modify any source files.
2. Use Grep, Glob, and Read tools to examine code. Use Bash only for `wc -l` or similar read-only commands.
3. Write your findings to your assigned output file using the finding format below.
4. Each finding MUST include the actual code evidence (3-5 lines from the file).
5. Mark your task as completed when done.

---

## Squad A: Security & Authorization

### Agent A1: AuthZ Auditor (`authz-auditor`)
- **SubAgent Type**: `security-reviewer`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/A1-authz.md`
- **Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication
- **Hotspot Files**:
  - `src/core/auth.py` — JWT token creation/validation
  - `src/core/permissions.py` — RBAC and engagement-level access control
  - `src/core/security.py` — Security utilities
  - `src/mcp/auth.py` — MCP server authentication
  - All 26 route files in `src/api/routes/` — verify auth decorators are applied
- **Specific Checks**:
  1. Grep for `require_engagement_access` — is it defined but never called in route files?
  2. Check `verify_api_key` in `src/mcp/auth.py` — does it actually validate against DB or accept any format match?
  3. Check every route handler in `src/api/routes/` — which endpoints lack authentication?
  4. Search for hardcoded secrets: `dev-secret-key`, `password.*=.*["']`
  5. Check JWT token expiration and refresh logic
  6. Look for privilege escalation paths (user can access admin routes?)

### Agent A2: Injection Auditor (`injection-auditor`)
- **SubAgent Type**: `security-reviewer`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/A2-injection.md`
- **Scope**: OWASP injection vectors, file upload security, LLM prompt injection, XSS, SSRF
- **Hotspot Files**:
  - `src/evidence/pipeline.py` — file upload and processing pipeline
  - `src/evidence/parsers/*` — all 17 parser files
  - `src/rag/copilot.py` — RAG copilot with user query handling
  - `src/rag/prompts.py` — LLM prompt templates
  - `src/simulation/suggester.py` — simulation suggestions
  - `frontend/src/` — all React components for XSS
- **Specific Checks**:
  1. Grep for `query.*format|f".*query` in RAG/LLM files — unsanitized user input in prompts?
  2. Grep for `subprocess|create_subprocess` — command injection risk
  3. Grep for `os.path.join|Path(` in evidence parsers — path traversal?
  4. Grep for `dangerouslySetInnerHTML` in frontend — XSS vectors
  5. Check file upload validation — are file types, sizes, and contents validated?
  6. Check for SQL injection in any raw query construction
  7. Check for SSRF in any URL-fetching code

### Agent A3: Infrastructure Security Auditor (`infra-security-auditor`)
- **SubAgent Type**: `security-reviewer`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/A3-infra-security.md`
- **Scope**: Docker configuration, Cloudflare worker, Redis/Neo4j authentication, secrets management, CORS, encryption
- **Hotspot Files**:
  - `docker-compose.yml` — container security configuration
  - `src/core/config.py` — application configuration and secrets
  - `src/core/encryption.py` — encryption key derivation
  - `src/api/main.py` — CORS configuration, middleware stack
  - `src/api/middleware/security.py` — security middleware
  - `infrastructure/cloudflare-workers/presentation-auth/src/index.ts` — worker security
- **Specific Checks**:
  1. Check `docker-compose.yml` for: missing Redis `requirepass`, exposed ports, default passwords
  2. Check CORS config in `api/main.py` — `allow_methods=["*"]`, `allow_headers=["*"]`?
  3. Check `core/config.py` — does it validate secrets at startup or accept defaults in production?
  4. Check `core/encryption.py` — `_derive_fernet_key` uses proper KDF (PBKDF2/scrypt) or just SHA-256?
  5. Check for TLS enforcement, secure cookie flags, HSTS headers
  6. Check Neo4j connection string for hardcoded credentials
  7. Grep for `password|secret|key` in all config files

---

## Squad B: Architecture & Data Integrity

### Agent B1: Architecture Auditor (`architecture-auditor`)
- **SubAgent Type**: `architecture-reviewer`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/B1-architecture.md`
- **Scope**: Module boundaries, god files, coupling analysis, async patterns, scalability concerns
- **Hotspot Files**:
  - `src/core/models.py` (1717 lines) — potential god file
  - `src/api/routes/simulations.py` (1309 lines) — potential god file
  - `src/evidence/pipeline.py` (830 lines) — complex processing pipeline
  - `frontend/src/lib/api.ts` (1695 lines) — monolithic API client
- **Specific Checks**:
  1. Run `wc -l` on all Python files, flag any > 500 lines as god files
  2. Run `wc -l` on all TypeScript files, flag any > 500 lines
  3. Check for circular imports: grep for `from src.` inside function bodies (deferred imports = coupling smell)
  4. Check for global mutable state: `defaultdict` or mutable objects at module level
  5. Analyze module dependency graph — which modules import which?
  6. Check async/sync mixing — are there `sync` calls inside `async` functions blocking the event loop?
  7. Identify layering violations (routes importing from other routes, core importing from api)

### Agent B2: Data Integrity Auditor (`data-integrity-auditor`)
- **SubAgent Type**: `architecture-reviewer`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/B2-data-integrity.md`
- **Scope**: Database schema design, FK constraints, cascade deletes, migration chain integrity, Neo4j graph model, pgvector usage
- **Hotspot Files**:
  - `src/core/models.py` — all SQLAlchemy models
  - `alembic/versions/` — all 19 migration files
  - `src/semantic/graph.py` — Neo4j graph operations
  - `src/semantic/embeddings.py` — pgvector embedding storage
- **Specific Checks**:
  1. Check all ForeignKey definitions — do they have `ondelete="CASCADE"` or appropriate cascade?
  2. Count `nullable=True` columns — are there overly nullable columns that should be required?
  3. Verify alembic migration chain — do all revisions link properly (no gaps, no conflicts)?
  4. Check Neo4j operations — are transactions properly managed? Injection via string concatenation?
  5. Check for orphan record risks — what happens when parent records are deleted?
  6. Check index coverage — are frequently queried columns indexed?
  7. Verify pgvector dimension consistency across embeddings

### Agent B3: API Compliance Auditor (`api-compliance-auditor`)
- **SubAgent Type**: `code-quality-reviewer`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/B3-api-compliance.md`
- **Scope**: REST standards, response format consistency, pagination, error handling, rate limiting, API versioning
- **Hotspot Files**:
  - All 26 route files in `src/api/routes/`
  - `src/api/main.py` — error handlers, middleware registration
  - `src/api/middleware/security.py` — rate limiting implementation
- **Specific Checks**:
  1. Check response format consistency — do all endpoints return the same structure?
  2. Check pagination — do list endpoints support `limit`/`offset`? Are there unbounded queries?
  3. Check error handling — do all routes use consistent error response format?
  4. Check rate limiting — is it applied to all endpoints or just some?
  5. Check HTTP method usage — proper GET/POST/PUT/DELETE semantics?
  6. Check for missing response status codes (201 for creation, 204 for deletion, etc.)
  7. Count total endpoints and categorize by authentication status

---

## Squad C: Code Quality & Performance

### Agent C1: Python Quality Auditor (`python-quality-auditor`)
- **SubAgent Type**: `code-quality-reviewer`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/C1-python-quality.md`
- **Scope**: Type safety, error handling patterns, anti-patterns, DRY/SOLID violations, dead code
- **Scope Files**: All files under `src/`
- **Specific Checks**:
  1. Count `except Exception:` occurrences — flag broad exception handling
  2. Count `except:` (bare except) — always flag these
  3. Count `: Any` type annotations — flag type safety gaps
  4. Grep for `datetime.utcnow()` — deprecated in Python 3.12
  5. Grep for `logger.*(f"` — f-strings in logger calls (should use lazy formatting)
  6. Grep for `# TODO|# FIXME|# HACK` — unfinished work markers (count and list)
  7. Check for functions > 50 lines, classes > 300 lines
  8. Look for duplicate code patterns across modules
  9. Check for unused imports at the top of files

### Agent C2: Frontend Quality Auditor (`frontend-quality-auditor`)
- **SubAgent Type**: `code-quality-reviewer`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/C2-frontend-quality.md`
- **Scope**: React component patterns, error boundaries, accessibility, token storage security, state management
- **Scope Files**: All files under `frontend/src/`
- **Specific Checks**:
  1. Check for error boundaries — are they used around key component trees?
  2. Grep for `localStorage.*token|localStorage.*kmflow` — JWT in XSS-accessible storage
  3. Check for loading states — do async operations show loading indicators?
  4. Check for accessibility: `aria-` attributes, `alt` on images, keyboard navigation
  5. Grep for `dangerouslySetInnerHTML` — XSS risk
  6. Check for proper cleanup in useEffect hooks (return cleanup functions)
  7. Check for console.log statements left in production code
  8. Look for inline styles vs proper CSS patterns
  9. Check for proper TypeScript types vs `any` usage

### Agent C3: Performance Auditor (`performance-auditor`)
- **SubAgent Type**: `performance-analyzer`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/C3-performance.md`
- **Scope**: N+1 queries, async anti-patterns, memory leaks, connection pooling, caching strategy
- **Hotspot Files**:
  - All route handlers with DB queries in `src/api/routes/`
  - `src/evidence/pipeline.py` — file I/O operations
  - `src/api/middleware/security.py` — rate limiter implementation
  - `src/semantic/graph.py` — Neo4j query patterns
  - `src/semantic/embeddings.py` — vector operations
- **Specific Checks**:
  1. Look for N+1 query patterns — loops that execute DB queries
  2. Check for missing eager loading (joinedload, selectinload) in SQLAlchemy queries
  3. Check async anti-patterns — sync I/O in async handlers, blocking calls
  4. Check connection pool configuration — pool size, max overflow, timeout
  5. Look for missing caching on expensive operations
  6. Check for memory leaks — large objects held in global scope, unclosed file handles
  7. Check for unbounded result sets — queries without LIMIT

---

## Squad D: Coverage, Compliance & Risk

### Agent D1: Test Coverage Auditor (`test-coverage-auditor`)
- **SubAgent Type**: `test-coverage-analyzer`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/D1-test-coverage.md`
- **Scope**: Test coverage gaps, mock quality, missing integration tests, edge case coverage
- **Specific Checks**:
  1. List all source modules and check which have corresponding test files
  2. Check test quality — are tests testing behavior or just structure?
  3. Look for over-mocking — tests that mock everything and test nothing
  4. Identify critical paths without tests: auth flows, payment-like flows, data deletion
  5. Check for missing edge case tests: empty inputs, large inputs, concurrent access
  6. Check for flaky test indicators: `time.sleep`, random data, global state mutation
  7. Count test files vs source files ratio

### Agent D2: Compliance Auditor (`compliance-auditor`)
- **SubAgent Type**: `critical-thinking`
- **Model**: `opus`
- **Output File**: `docs/audit-findings/D2-compliance.md`
- **Scope**: Audit trail completeness, GDPR considerations, LLM safety, data retention, regulatory alignment
- **Hotspot Files**:
  - `src/api/middleware/audit.py` — audit logging middleware
  - `src/core/models.py` — data models for PII
  - `src/rag/copilot.py` — LLM interaction safety
  - `src/rag/prompts.py` — prompt safety
- **Specific Checks**:
  1. Check audit trail — do all data-modifying operations create audit log entries?
  2. Grep for `session.add|session.delete` without corresponding AuditLog creation
  3. Grep for `logger.*email|logger.*name` — PII in application logs
  4. Check `max_tokens` usage — are LLM cost controls in place?
  5. Check data retention — is there a mechanism to purge old data?
  6. Check for GDPR-relevant operations — data export, data deletion, consent tracking
  7. Check LLM prompt safety — system prompts, input validation, output sanitization
  8. Check for data classification — is sensitive data marked/handled differently?

### Agent D3: Dependency & Regression Auditor (`dependency-regression-auditor`)
- **SubAgent Type**: `dependency-checker`
- **Model**: `sonnet`
- **Output File**: `docs/audit-findings/D3-dependencies.md`
- **Scope**: CVEs in dependencies, lock file status, abandoned packages, PR #127 regression risks
- **Specific Checks**:
  1. Check for Python lock file (poetry.lock, Pipfile.lock, requirements.txt pinning)
  2. Check `package.json` and `package-lock.json` — are frontend deps locked?
  3. Look for known vulnerable package versions in requirements
  4. Check for abandoned/deprecated packages
  5. Verify dependency version compatibility
  6. Check for unnecessary dependencies (imported but not used)
  7. Review PR #127 changes — look at recent git log for any regression indicators

---

## Phase 3: Compile the Report

After all 12 agents complete, read all files from `docs/audit-findings/` and compile into `docs/audit-report-latest.md` with this structure:

```markdown
# KMFlow Platform Code Audit Report — YYYY-MM-DD

## Executive Summary
- Total findings: X
- By severity: X CRITICAL / X HIGH / X MEDIUM / X LOW
- By squad: Security (X) / Architecture (X) / Quality (X) / Coverage (X)

## Top 10 Critical & High Findings
[Numbered list with file:line references]

## CRITICAL Findings
[All CRITICAL findings from all squads]

## HIGH Findings
[All HIGH findings from all squads]

## MEDIUM Findings
[All MEDIUM findings from all squads]

## LOW Findings
[All LOW findings from all squads]

## Squad Reports
### A: Security & Authorization
[Full findings from A1, A2, A3]

### B: Architecture & Data Integrity
[Full findings from B1, B2, B3]

### C: Code Quality & Performance
[Full findings from C1, C2, C3]

### D: Coverage, Compliance & Risk
[Full findings from D1, D2, D3]

## Recommendations
Top 10 highest-impact actions ranked by risk reduction
```

## Finding Format

Every individual finding MUST use this format:

```markdown
### [SEVERITY] CATEGORY: Title
**File**: `src/path/to/file.py:123`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
\```python
# 3-5 lines of actual code from the file
\```
**Description**: What is wrong and why it matters.
**Risk**: What could go wrong if exploited or left unfixed.
**Recommendation**: How to fix it.
```

Severity levels: CRITICAL, HIGH, MEDIUM, LOW

## Pre-identified Findings

These findings have already been confirmed via grep. Your agents MUST find and report these (plus any additional findings). If an agent doesn't report a known finding in its scope, that's a gap.

1. **CRITICAL** — `require_engagement_access()` defined in `permissions.py` but never called in any route file — multi-tenant isolation is dead code
2. **HIGH** — MCP `verify_api_key()` in `mcp/auth.py` skips DB lookup, accepts any `kmflow_*.xxx` format string
3. **HIGH** — JWT stored in `localStorage` in `frontend/src/lib/api.ts` — vulnerable to XSS
4. **HIGH** — Redis container has no authentication in `docker-compose.yml`
5. **HIGH** — CORS uses `allow_methods=["*"]`, `allow_headers=["*"]` in `api/main.py`
6. **HIGH** — RAG copilot injects user queries into LLM prompts unsanitized in `rag/copilot.py`
7. **MEDIUM** — Default `dev-secret-key` with no production startup validation in `core/config.py`
8. **MEDIUM** — Fernet key derivation uses SHA-256 without salt/iterations in `core/encryption.py`
9. **MEDIUM** — No Python lock file — non-reproducible builds
10. **MEDIUM** — `core/models.py` is 1717 lines — god file with 40+ models
