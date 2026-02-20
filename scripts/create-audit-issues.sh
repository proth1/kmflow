#!/bin/bash
# Create GitHub issues for all audit findings
# Organized as 4 Epics + individual issues grouped by remediation task
set -e

REPO="proth1/kmflow"

echo "=== Creating Epic Issues ==="

EPIC_A=$(gh issue create --repo "$REPO" \
  --title "Epic: Security & Authorization Remediation" \
  --label "epic,priority:critical,component:security" \
  --body "$(cat <<'BODY'
## Scope
Remediate all findings from Squad A (Security & Authorization) of the 2026-02-20 code audit.

**Source**: `docs/audit-findings/A1-authz.md`, `docs/audit-findings/A2-injection.md`, `docs/audit-findings/A3-infra-security.md`

## Finding Summary
- A1 (AuthZ): 2 CRITICAL, 4 HIGH, 5 MEDIUM, 2 LOW (13 total)
- A2 (Injection): 2 CRITICAL, 3 HIGH, 4 MEDIUM, 2 LOW (11 total)
- A3 (Infra Security): 2 CRITICAL, 4 HIGH, 5 MEDIUM, 3 LOW (14 total)
- **Total: 6 CRITICAL, 11 HIGH, 14 MEDIUM, 7 LOW = 38 findings**

## Key CRITICAL Issues
1. Multi-tenancy isolation dead code (`require_engagement_access` never called)
2. MCP API key validation format-only (no DB lookup)
3. Arbitrary Cypher query endpoint
4. XXE in 3 XML parsers
5. Redis without authentication
6. Default secrets accepted in production
BODY
)" 2>&1 | grep -oE '[0-9]+$')

echo "Created Epic A: #$EPIC_A"

EPIC_B=$(gh issue create --repo "$REPO" \
  --title "Epic: Architecture & Data Integrity Remediation" \
  --label "epic,priority:high,component:backend" \
  --body "$(cat <<'BODY'
## Scope
Remediate all findings from Squad B (Architecture & Data Integrity) of the 2026-02-20 code audit.

**Source**: `docs/audit-findings/B1-architecture.md`, `docs/audit-findings/B2-data-integrity.md`, `docs/audit-findings/B3-api-compliance.md`

## Finding Summary
- B1 (Architecture): 0 CRITICAL, 3 HIGH, 6 MEDIUM, 3 LOW (12 total)
- B2 (Data Integrity): 2 CRITICAL, 4 HIGH, 4 MEDIUM, 3 LOW (13 total)
- B3 (API Compliance): 1 CRITICAL, 6 HIGH, 5 MEDIUM, 3 LOW (15 total)
- **Total: 3 CRITICAL, 13 HIGH, 15 MEDIUM, 9 LOW = 40 findings**

## Key CRITICAL Issues
1. Branched migration chain (005 and 006 both from 004)
2. Missing FK ondelete on 4 columns
3. slowapi rate limiter never registered
BODY
)" 2>&1 | grep -oE '[0-9]+$')

echo "Created Epic B: #$EPIC_B"

EPIC_C=$(gh issue create --repo "$REPO" \
  --title "Epic: Code Quality & Performance Remediation" \
  --label "epic,priority:high,component:backend" \
  --body "$(cat <<'BODY'
## Scope
Remediate all findings from Squad C (Code Quality & Performance) of the 2026-02-20 code audit.

**Source**: `docs/audit-findings/C1-python-quality.md`, `docs/audit-findings/C2-frontend-quality.md`, `docs/audit-findings/C3-performance.md`

## Finding Summary
- C1 (Python Quality): 1 CRITICAL, 5 HIGH, 5 MEDIUM, 1 LOW (12 total)
- C2 (Frontend Quality): 1 CRITICAL, 4 HIGH, 4 MEDIUM, 3 LOW (12 total)
- C3 (Performance): 1 CRITICAL, 5 HIGH, 5 MEDIUM, 3 LOW (14 total)
- **Total: 3 CRITICAL, 14 HIGH, 14 MEDIUM, 7 LOW = 38 findings**

## Key CRITICAL Issues
1. Silent exception swallowing (4 locations)
2. JWT stored in localStorage (XSS-accessible)
3. N+1 query in batch validation
BODY
)" 2>&1 | grep -oE '[0-9]+$')

echo "Created Epic C: #$EPIC_C"

EPIC_D=$(gh issue create --repo "$REPO" \
  --title "Epic: Coverage, Compliance & Risk Remediation" \
  --label "epic,priority:critical,component:testing" \
  --body "$(cat <<'BODY'
## Scope
Remediate all findings from Squad D (Coverage, Compliance & Risk) of the 2026-02-20 code audit.

**Source**: `docs/audit-findings/D1-test-coverage.md`, `docs/audit-findings/D2-compliance.md`, `docs/audit-findings/D3-dependencies.md`

## Finding Summary
- D1 (Test Coverage): 4 CRITICAL, 6 HIGH, 4 MEDIUM, 2 LOW (16 total)
- D2 (Compliance): 3 CRITICAL, 5 HIGH, 5 MEDIUM, 3 LOW (16 total)
- D3 (Dependencies): 0 CRITICAL, 1 HIGH, 4 MEDIUM, 3 LOW (8 total)
- **Total: 7 CRITICAL, 12 HIGH, 13 MEDIUM, 8 LOW = 40 findings**

## Key CRITICAL Issues
1. Evidence upload endpoint untested
2. Token blacklist untested
3. Admin routes entirely untested
4. Data retention logic untested
5. Multiple routes mutate without AuditLog
6. No GDPR data subject rights
7. LLM prompts/responses stored permanently
BODY
)" 2>&1 | grep -oE '[0-9]+$')

echo "Created Epic D: #$EPIC_D"

echo ""
echo "=== Creating Individual Issues ==="

# Helper function
create_issue() {
  local title="$1"
  local labels="$2"
  local body="$3"
  local epic="$4"

  local full_body="Part of epic #${epic}

${body}"

  local num=$(gh issue create --repo "$REPO" \
    --title "$title" \
    --label "$labels" \
    --body "$full_body" 2>&1 | grep -oE '[0-9]+$')
  echo "  Created: #$num - $title"
}

# ==================== SQUAD A: Security ====================
echo ""
echo "--- Squad A: Security Issues ---"

create_issue \
  "[CRITICAL] Enforce multi-tenancy isolation via require_engagement_access" \
  "task,priority:critical,component:security,component:backend" \
  "**Finding**: A1-01
**Files**: All 21 route files under \`src/api/routes/\`
**Description**: \`require_engagement_access()\` is defined in \`src/core/permissions.py:188\` but never called. ~130 endpoints across 21 route files allow any authenticated user to access any engagement's data.
**Fix**: Add \`Depends(require_engagement_access)\` to every route that takes an \`engagement_id\` parameter." \
  "$EPIC_A"

create_issue \
  "[CRITICAL] Fix MCP API key validation to use DB lookup" \
  "task,priority:critical,component:security,component:backend" \
  "**Finding**: A1-02
**Files**: \`src/mcp/auth.py:129-144\`, \`src/mcp/server.py:33-34\`
**Description**: \`verify_api_key()\` validates format only (\`kmflow_*.xxx\`), no DB lookup. Any string matching this pattern authenticates. The async \`validate_api_key()\` with DB validation exists but is unused.
**Fix**: Replace sync \`verify_api_key()\` with async \`validate_api_key()\` in MCP server auth." \
  "$EPIC_A"

create_issue \
  "[CRITICAL] Fix XXE vulnerabilities in XML parsers" \
  "task,priority:critical,component:security,component:backend" \
  "**Finding**: A2-02
**Files**: \`src/evidence/parsers/bpmn_parser.py:54\`, \`xes_parser.py:45\`, \`visio_parser.py:71\`
**Description**: Three XML parsers use \`lxml.etree.parse()\` with default settings (XXE enabled). The ARIS parser correctly uses \`defusedxml\`.
**Fix**: Use \`defusedxml.lxml.parse()\` or \`XMLParser(resolve_entities=False, no_network=True)\`." \
  "$EPIC_A"

create_issue \
  "[CRITICAL] Remove or restrict arbitrary Cypher query endpoint" \
  "task,priority:critical,component:security,component:backend" \
  "**Finding**: A2-01
**Files**: \`src/api/routes/graph.py:187-215\`
**Description**: \`POST /api/v1/graph/query\` accepts arbitrary Cypher queries with a bypassable keyword blocklist.
**Fix**: Remove endpoint or restrict to admin-only with allowlisted query patterns." \
  "$EPIC_A"

create_issue \
  "[CRITICAL] Add Redis authentication" \
  "task,priority:critical,component:security,component:infrastructure" \
  "**Finding**: A3-01
**Files**: \`docker-compose.yml:57-75\`, \`docker-compose.prod.yml\`, \`src/core/redis.py\`
**Description**: Redis has no \`requirepass\` in dev or prod compose files. Redis URL has no password component.
**Fix**: Add \`--requirepass\` to Redis command, update redis_url config." \
  "$EPIC_A"

create_issue \
  "[CRITICAL] Block default secrets in production" \
  "task,priority:critical,component:security,component:backend" \
  "**Finding**: A3-02
**Files**: \`src/core/config.py:61-67\`
**Description**: JWT and encryption keys have hardcoded defaults with no production startup validation. \`auth_dev_mode\` defaults to True.
**Fix**: Add model_validator to reject defaults when app_env==production. Default auth_dev_mode to False." \
  "$EPIC_A"

create_issue \
  "[HIGH] Fix JWT refresh token accepted as access token" \
  "task,priority:high,component:security,component:backend" \
  "**Finding**: A1-03
**Files**: \`src/core/auth.py:190-260\`
**Description**: \`get_current_user\` never checks the token \`type\` claim. Refresh tokens (7-day) work as access tokens.
**Fix**: Add \`if payload.get('type') != 'access': raise HTTPException(401)\` in get_current_user." \
  "$EPIC_A"

create_issue \
  "[HIGH] Fix user profile IDOR vulnerability" \
  "task,priority:high,component:security,component:backend" \
  "**Finding**: A1-04
**Files**: \`src/api/routes/users.py:159-173\`
**Description**: \`GET /api/v1/users/{user_id}\` allows any authenticated user to view any user's profile.
**Fix**: Add check that current_user.id == user_id or user is admin." \
  "$EPIC_A"

create_issue \
  "[HIGH] Fix WebSocket authentication gaps" \
  "task,priority:high,component:security,component:backend" \
  "**Finding**: A1-05
**Files**: \`src/api/routes/websocket.py:105-134\`
**Description**: WebSocket auth doesn't check token blacklist, engagement membership, or token type.
**Fix**: Extract user from token, check blacklist, verify engagement membership, validate token type." \
  "$EPIC_A"

create_issue \
  "[HIGH] Fix injection vectors: LLM prompt, SOQL, Cypher property keys" \
  "task,priority:high,component:security,component:backend" \
  "**Findings**: A2-03, A2-04, A2-05
**Files**: \`src/rag/copilot.py:93-97\`, \`src/integrations/salesforce.py:108,153\`, \`src/semantic/graph.py:175-176\`
**Description**: (1) User queries injected unsanitized into LLM prompts. (2) SOQL queries use f-string interpolation. (3) Neo4j property keys interpolated into Cypher.
**Fix**: (1) Add XML delimiters and sanitization. (2) Validate object_type/fields against allowlists. (3) Validate property keys with regex." \
  "$EPIC_A"

create_issue \
  "[HIGH] Harden CORS, Docker credentials, container security, HTTP headers" \
  "task,priority:high,component:security,component:infrastructure" \
  "**Findings**: A3-CORS-001, A3-DOCKER-001, A3-DOCKER-002, A3-HEADERS-001
**Files**: \`src/api/main.py:162-168\`, \`docker-compose.yml\`, \`Dockerfile.backend\`, \`src/api/middleware/security.py\`
**Description**: (1) CORS allows all methods/headers. (2) Hardcoded creds in docker-compose. (3) Container runs as root. (4) Missing HSTS/CSP headers.
**Fix**: Restrict CORS methods/headers. Use env var substitution for all creds. Add non-root user. Add HSTS+CSP+Permissions-Policy." \
  "$EPIC_A"

create_issue \
  "[MEDIUM] Fix remaining Squad A medium-severity findings" \
  "task,priority:medium,component:security" \
  "**Findings**: A1-MEDIUM (5), A2-MEDIUM (4), A3-MEDIUM (5) = 14 findings
Key items:
- Unauthenticated WebSocket status endpoint leaks engagement IDs
- Unauthenticated MCP info/tools endpoints
- Engagement member list missing access control
- auth_dev_mode defaults to True
- Admin key rotation leaks exception details
- Weak key derivation (SHA-256 without salt)
- Reflected XSS in Cloudflare worker login
- Rate limiter unbounded growth
- OpenAPI docs exposed in production
- Dev volume mounts writable
- Broad MIME allowlist (application/octet-stream)
- Magic fallback to client MIME type
- Visio parser zip entry path validation
- Cypher write blocklist bypass (related to CRITICAL endpoint removal)" \
  "$EPIC_A"

create_issue \
  "[LOW] Fix remaining Squad A low-severity findings" \
  "task,priority:low,component:security" \
  "**Findings**: A1-LOW (2), A2-LOW (2), A3-LOW (3) = 7 findings
Key items:
- Deprecated datetime.utcnow() in MCP auth
- PII in MCP auth logs
- Docker container security options (no-new-privileges, cap_drop)
- CIB7 Camunda no auth
- All service ports mapped to host
- Internal file paths in API responses
- Error detail leakage in responses" \
  "$EPIC_A"

# ==================== SQUAD B: Architecture ====================
echo ""
echo "--- Squad B: Architecture Issues ---"

create_issue \
  "[CRITICAL] Fix branched Alembic migration chain" \
  "task,priority:critical,component:backend" \
  "**Finding**: B2-01
**Files**: \`alembic/versions/005_*.py\`, \`alembic/versions/006_*.py\`
**Description**: Migrations 005 and 006 both have \`down_revision = '004'\`, creating a branched tree. \`alembic upgrade head\` fails on fresh DB.
**Fix**: Create a merge migration with \`down_revision = ('005', '006')\` or fix 006 to depend on 005." \
  "$EPIC_B"

create_issue \
  "[CRITICAL] Fix missing FK ondelete on 4 columns" \
  "task,priority:critical,component:backend" \
  "**Finding**: B2-02
**Files**: \`src/core/models.py:930-931, 948, 1484\`
**Description**: MetricReading.metric_id, MetricReading.engagement_id, Annotation.engagement_id, and AlternativeSuggestion.created_by lack \`ondelete\`.
**Fix**: Add \`ondelete='CASCADE'\` to the first three and \`ondelete='SET NULL'\` (with nullable) to created_by. Create migration." \
  "$EPIC_B"

create_issue \
  "[CRITICAL] Register slowapi rate limiter for auth endpoints" \
  "task,priority:critical,component:backend" \
  "**Finding**: B3-01
**Files**: \`src/api/main.py\`, \`src/api/routes/auth.py:40-41\`
**Description**: slowapi Limiter instance exists with decorators but \`app.state.limiter\` and \`SlowAPIMiddleware\` are never registered. Auth rate limiting silently fails.
**Fix**: Register slowapi state, middleware, and exception handler in main.py." \
  "$EPIC_B"

create_issue \
  "[HIGH] Fix schema/migration mismatches and orphan risks" \
  "task,priority:high,component:backend" \
  "**Findings**: B2-03, B2-04, B2-05
**Files**: \`alembic/versions/010_*.py\`, \`src/core/models.py\`
**Description**: (1) Migration 010 uses LargeBinary for embedding, ORM uses Vector(768). (2) Only 3 of 18+ child tables have ORM cascade from Engagement. (3) Migration 018 FK without ondelete.
**Fix**: Create migration to convert column type. Add cascade relationships. Fix FK." \
  "$EPIC_B"

create_issue \
  "[HIGH] Add pagination to 12+ unbounded list endpoints" \
  "task,priority:high,component:backend" \
  "**Findings**: B3-02, C3-04, C3-05
**Files**: Multiple route files (monitoring.py, simulations.py, engagements.py, tom.py, integrations.py, conformance.py, evidence.py)
**Description**: 12+ list endpoints use \`.all()\` with no LIMIT/OFFSET. Includes audit logs, scenarios, modifications, suggestions, etc.
**Fix**: Add \`limit: int = Query(default=20, ge=1, le=100)\` and \`offset: int = Query(default=0, ge=0)\` to all list endpoints." \
  "$EPIC_B"

create_issue \
  "[HIGH] Fix incorrect total count, DELETE semantics, permissions, response formats" \
  "task,priority:high,component:backend" \
  "**Findings**: B3-03 (patterns total), B3-04 (DELETE semantics), B3-05 (TOM write permissions), B3-06 (governance catalog format), B3-07 (health versioning)
**Files**: patterns.py, engagements.py, tom.py, metrics.py, regulatory.py, governance.py, health.py
**Description**: (1) list_patterns reports page size as total. (2) DELETE returns 200 with body. (3) Write ops use engagement:read. (4) Catalog returns raw list. (5) Health not versioned.
**Fix**: Separate count query. Fix DELETE to 204 or PATCH. Use write permissions. Add wrapper response. Version health endpoint." \
  "$EPIC_B"

create_issue \
  "[HIGH] Refactor god files: models.py (1717 lines), simulations.py (1309 lines)" \
  "story,priority:high,component:backend" \
  "**Findings**: B1-01, B1-02
**Files**: \`src/core/models.py\`, \`src/api/routes/simulations.py\`
**Description**: models.py has 76 classes. simulations.py has 27 inline schemas + business logic + rate limiter.
**Fix**: Split models into domain modules. Extract schemas and service layer from routes.
**Note**: This is a significant refactoring effort - track separately." \
  "$EPIC_B"

create_issue \
  "[MEDIUM] Fix remaining Squad B medium-severity findings" \
  "task,priority:medium,component:backend" \
  "**Findings**: B1-MEDIUM (6), B2-MEDIUM (4), B3-MEDIUM (5) = 15 findings
Key items: deferred imports coupling, missing service layer, schema coupling, frontend monolith, frontend god component, migration ondelete mismatch, 119 nullable columns, missing FK indexes, missing unique constraints, error message leakage, sync 202 status, rate limiter not shared, missing audit log pagination" \
  "$EPIC_B"

create_issue \
  "[LOW] Fix remaining Squad B low-severity findings" \
  "task,priority:low,component:backend" \
  "**Findings**: B1-LOW (3), B2-LOW (3), B3-LOW (3) = 9 findings
Key items: async-sync mix in storage, no DI for Neo4j, inconsistent schema returns, alembic hardcoded creds, pgvector dimension consistency, Neo4j read transactions, naming conventions, missing response models, Camunda route review" \
  "$EPIC_B"

# ==================== SQUAD C: Quality ====================
echo ""
echo "--- Squad C: Quality Issues ---"

create_issue \
  "[CRITICAL] Fix silent exception swallowing in builder and databricks" \
  "task,priority:critical,component:backend" \
  "**Finding**: C1-01
**Files**: \`src/semantic/builder.py:365,382,399\`, \`src/datalake/databricks_backend.py:227\`
**Description**: 4 locations catch Exception and immediately \`pass\` without logging. Silent data loss in knowledge graph.
**Fix**: Replace \`pass\` with \`logger.debug/warning\` for diagnostics." \
  "$EPIC_C"

create_issue \
  "[CRITICAL] Migrate JWT from localStorage to HttpOnly cookies" \
  "task,priority:critical,component:security,component:frontend" \
  "**Finding**: C2-01
**Files**: \`frontend/src/lib/api.ts:22\`, auth routes
**Description**: JWT stored in localStorage is XSS-accessible. Any XSS allows token theft.
**Fix**: Set token via HttpOnly cookie from server. Remove localStorage usage. Add credentials: include to fetch." \
  "$EPIC_C"

create_issue \
  "[CRITICAL] Fix N+1 query in batch validation endpoint" \
  "task,priority:critical,component:backend" \
  "**Finding**: C3-01
**Files**: \`src/api/routes/evidence.py:342\`
**Description**: batch_validate loops over evidence_ids with one SELECT per ID.
**Fix**: Use \`WHERE id IN (...)\` single query. Add max_items constraint on request schema." \
  "$EPIC_C"

create_issue \
  "[HIGH] Fix N+1 Neo4j queries and sequential entity extraction" \
  "task,priority:high,component:backend" \
  "**Findings**: C3-02, C3-03
**Files**: \`src/semantic/builder.py:147,175\`
**Description**: (1) One Neo4j session per node creation. (2) Entity extraction sequential per fragment.
**Fix**: Use UNWIND for batch node creation. Use asyncio.gather for concurrent extraction." \
  "$EPIC_C"

create_issue \
  "[HIGH] Fix unbounded graph queries and memory leak rate limiter" \
  "task,priority:high,component:backend" \
  "**Findings**: C3-04, C3-06
**Files**: \`src/semantic/graph.py:429\`, \`src/api/routes/simulations.py:56\`
**Description**: (1) get_engagement_subgraph fetches ALL nodes without LIMIT. (2) _llm_request_log unbounded dict.
**Fix**: Add pagination to subgraph query. Replace in-memory rate limiter with Redis-based or TTLCache." \
  "$EPIC_C"

create_issue \
  "[HIGH] Consolidate duplicate _log_audit and _verify_engagement functions" \
  "task,priority:high,component:backend" \
  "**Finding**: C1-07
**Files**: \`src/api/routes/tom.py:173\`, \`regulatory.py:173\`, \`simulations.py:239\`
**Description**: _log_audit copy-pasted across 3 files with slight variations. simulations.py version adds actor param not in others.
**Fix**: Extract to shared utility in \`src/core/audit.py\`. All routes import from there." \
  "$EPIC_C"

create_issue \
  "[HIGH] Add React ErrorBoundary and fix AnnotationPanel auth" \
  "task,priority:high,component:frontend" \
  "**Findings**: C2-02, C2-04
**Files**: \`frontend/src/app/layout.tsx\`, \`frontend/src/components/AnnotationPanel.tsx\`
**Description**: (1) No ErrorBoundary anywhere - render exceptions crash the entire app. (2) AnnotationPanel uses raw fetch without auth headers.
**Fix**: Add ErrorBoundary to root layout. Replace raw fetch with apiGet/apiPost/apiDelete." \
  "$EPIC_C"

create_issue \
  "[MEDIUM] Fix remaining Squad C medium-severity findings" \
  "task,priority:medium,component:backend" \
  "**Findings**: C1-MEDIUM (5), C2-MEDIUM (4), C3-MEDIUM (5) = 14 findings
Key items: deprecated utcnow, f-string logging, inline imports, duplicate sanitize_filename, duplicate _headers, accessibility gaps, simulations god component, stale closure bug, sequential embedding batches, file content buffered, no embedding service caching, no Neo4j session reuse, dashboard no caching" \
  "$EPIC_C"

create_issue \
  "[LOW] Fix remaining Squad C low-severity findings" \
  "task,priority:low,component:backend" \
  "**Findings**: C1-LOW (1), C2-LOW (3), C3-LOW (3) = 7 findings
Key items: print in non-CLI files, TODO in api.ts, inline styles, useDataLoader silent initial errors, vector string serialization, pool size config, pure-Python cosine similarity" \
  "$EPIC_C"

# ==================== SQUAD D: Coverage & Compliance ====================
echo ""
echo "--- Squad D: Coverage & Compliance Issues ---"

create_issue \
  "[CRITICAL] Add AuditLog entries to 7 route modules missing them" \
  "task,priority:critical,component:backend" \
  "**Finding**: D2-01
**Files**: users.py, monitoring.py, patterns.py, annotations.py, conformance.py, metrics.py, portal.py
**Description**: These route modules perform mutations without AuditLog database entries. Only app-level logging exists via middleware.
**Fix**: Add AuditLog entries for all state-mutating operations in these modules." \
  "$EPIC_D"

create_issue \
  "[CRITICAL] Implement GDPR data subject rights" \
  "task,priority:critical,component:backend" \
  "**Finding**: D2-02
**Files**: \`src/api/routes/users.py\`, new endpoints
**Description**: No DELETE user endpoint. No data export. No DSAR mechanism. No consent tracking.
**Fix**: Add DELETE /users/{id} (anonymize), GET /users/{id}/export, consent model." \
  "$EPIC_D"

create_issue \
  "[CRITICAL] Add retention policies for LLM data" \
  "task,priority:critical,component:backend" \
  "**Finding**: D2-03
**Files**: \`src/core/models.py\`, \`src/core/retention.py\`
**Description**: AlternativeSuggestion stores full LLM prompts/responses permanently. CopilotMessage stores queries indefinitely.
**Fix**: Add retention_days to models. Add cleanup job for expired LLM data." \
  "$EPIC_D"

create_issue \
  "[CRITICAL] Add tests for evidence upload, token blacklist, admin routes, retention" \
  "task,priority:critical,component:testing" \
  "**Findings**: D1-01, D1-02, D1-03, D1-04
**Files**: New test files in \`tests/\`
**Description**: (1) POST /evidence/upload has zero HTTP tests. (2) Token blacklist functions untested. (3) Admin routes entirely untested. (4) Data retention logic untested.
**Fix**: Create test files with comprehensive test coverage for each." \
  "$EPIC_D"

create_issue \
  "[HIGH] Fix audit middleware to persist to database" \
  "task,priority:high,component:backend" \
  "**Findings**: D2-04, D2-05
**Files**: \`src/api/middleware/audit.py\`, \`src/core/audit.py\`
**Description**: (1) Audit middleware only logs to app logger, not database. (2) Security events without engagement_id silently dropped.
**Fix**: Write audit records to DB. Make engagement_id nullable or create security_audit_logs table." \
  "$EPIC_D"

create_issue \
  "[HIGH] Fix retention cleanup to actually delete data" \
  "task,priority:high,component:backend" \
  "**Finding**: D2-06
**Files**: \`src/core/retention.py:44-61\`
**Description**: cleanup_expired_engagements only archives (status change), doesn't delete evidence. Docstring misleading.
**Fix**: Implement actual data deletion/anonymization. Fix docstring." \
  "$EPIC_D"

create_issue \
  "[HIGH] Generate Python lock file for deterministic builds" \
  "task,priority:high,component:infrastructure" \
  "**Finding**: D3-01
**Files**: \`pyproject.toml\`, new \`requirements.txt\` or \`poetry.lock\`
**Description**: No Python lock file exists. All deps use range-based versions.
**Fix**: Generate pinned requirements.txt via pip freeze. Add cryptography as explicit dep." \
  "$EPIC_D"

create_issue \
  "[HIGH] Add tests for WebSocket auth, audit middleware, rate limiter, monitoring" \
  "task,priority:high,component:testing" \
  "**Findings**: D1-05, D1-06, D1-07, D1-08
**Files**: New test files in \`tests/\`
**Description**: WebSocket authentication, audit logging middleware, per-user rate limiter, and monitoring worker/event pipeline are all untested.
**Fix**: Create test files covering auth bypass, middleware behavior, rate limit enforcement, and worker dispatch." \
  "$EPIC_D"

create_issue \
  "[HIGH] Add LLM output validation and fix PII logging" \
  "task,priority:high,component:backend" \
  "**Findings**: D2-07, D2-08
**Files**: \`src/rag/copilot.py\`, \`src/simulation/suggester.py\`, \`src/mcp/auth.py\`
**Description**: (1) LLM responses returned without content filtering. (2) MCP auth logs user IDs via f-strings.
**Fix**: Add basic output validation. Switch to lazy %s logging." \
  "$EPIC_D"

create_issue \
  "[MEDIUM] Fix remaining Squad D medium-severity findings" \
  "task,priority:medium,component:backend" \
  "**Findings**: D1-MEDIUM (4), D2-MEDIUM (5), D3-MEDIUM (4) = 13 findings
Key items: semantic bridges untested, integration connectors untested, trivial test assertions, MCP server untested, copilot messages no retention, data classification unenforced, system prompt unprotected, suggester hardcoded model, audit log immutability, frontend npm caret ranges, build-time deps in production, cryptography undeclared, suggester bypasses SDK" \
  "$EPIC_D"

create_issue \
  "[LOW] Fix remaining Squad D low-severity findings" \
  "task,priority:low,component:backend" \
  "**Findings**: D1-LOW (2), D2-LOW (3), D3-LOW (3) = 8 findings
Key items: superficial E2E tests, no coverage thresholds in CI, no DPA references, retention_days optional, incomplete PII detection, CI removed, minimatch override, aiofiles version cap" \
  "$EPIC_D"

echo ""
echo "=== Issue Creation Complete ==="
echo "Epics: A=#$EPIC_A, B=#$EPIC_B, C=#$EPIC_C, D=#$EPIC_D"
