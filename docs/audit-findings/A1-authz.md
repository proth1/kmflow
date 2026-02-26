# A1: Authorization & Authentication Re-Audit Findings

**Auditor**: A1 (AuthZ Auditor)
**Date**: 2026-02-26 (Re-audit after Phase 0-2 remediation)
**Previous Audit**: 2026-02-20
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication

## Executive Summary

Significant security improvements have been made since the 2026-02-20 audit. Both
CRITICAL findings are resolved. The `require_engagement_access` dependency is now
deployed across 16 route files covering high-value endpoints (dashboard, portal,
reports, lineage, graph stats/subgraph/export, copilot history, engagement CRUD,
user membership, governance export/compliance, monitoring stats, simulation ranking,
and TOM alignment/maturity/roadmap). The MCP server now uses DB-backed API key
validation with HMAC constant-time comparison. JWT token type validation is enforced
in `get_current_user`. The `auth_dev_mode` default is now `False`.

However, the remediation was **selective** rather than comprehensive. Many
engagement-scoped endpoints still lack the `require_engagement_access` dependency,
creating a "Swiss cheese" pattern where some endpoints enforce multi-tenancy
isolation and others do not.

## Summary

| Severity | Count | Change from 2026-02-20 |
|----------|-------|------------------------|
| CRITICAL | 0     | -2 (both resolved)     |
| HIGH     | 2     | -2                     |
| MEDIUM   | 5     |  0                     |
| LOW      | 3     | +1                     |
| **Total** | **10** | **-3**              |

---

## Resolved Findings (from 2026-02-20)

The following findings from the original audit are confirmed **RESOLVED**:

### [RESOLVED] CRITICAL: MCP `verify_api_key()` validates format only, no DB lookup
- **Resolution**: The synchronous `verify_api_key()` stub has been removed from `src/mcp/auth.py`. The MCP server (`src/mcp/server.py:25-42`) now calls `validate_api_key()` which performs DB lookup, SHA256 hashing, and `hmac.compare_digest` comparison.
- **Evidence**: `src/mcp/server.py:36` -- `client = await validate_api_key(session, api_key)`
- **Verified**: `src/mcp/auth.py` contains only the async `validate_api_key`, `generate_api_key`, `revoke_api_key`, and `list_api_keys` functions. No sync stub remains.

### [RESOLVED] CRITICAL: `require_engagement_access` defined but never used
- **Resolution**: `require_engagement_access` is now imported and used as a FastAPI `Depends()` in 16 route files across approximately 35 endpoints.
- **Evidence**: grep confirms `_engagement_user: User = Depends(require_engagement_access)` in: `engagements.py`, `users.py`, `dashboard.py`, `portal.py`, `reports.py`, `lineage.py`, `graph.py`, `copilot.py`, `monitoring.py`, `simulations.py`, `tom.py`, `regulatory.py`, `governance.py`, `metrics.py`, `annotations.py`.
- **Caveat**: Coverage is incomplete -- see HIGH finding H-01 below.

### [RESOLVED] HIGH: JWT refresh tokens accepted as access tokens
- **Resolution**: `src/core/auth.py:323-329` -- `get_current_user` now checks `if payload.get("type") != "access"` and raises 401.
- **Evidence**: Lines 323-329 of `src/core/auth.py`.

### [RESOLVED] HIGH: Default JWT secret in config without production guard
- **Resolution**: `src/core/config.py:203-215` adds `reject_default_secrets_in_production` model validator. Also checks `auth_dev_mode` must be `False` in non-development environments. Raises `ValueError` (fatal) if defaults are detected.
- **Evidence**: `if has_default_jwt or has_default_enc or self.auth_dev_mode: raise ValueError(...)`.

### [RESOLVED] HIGH: IDOR in user profile endpoint
- **Resolution**: `src/api/routes/users.py:178` now checks `if not has_role_level(current_user, UserRole.PLATFORM_ADMIN) and current_user.id != user_id`.
- **Evidence**: Non-admin users can only view their own profile.

### [RESOLVED] HIGH: WebSocket authentication lacks engagement membership and blacklist
- **Resolution**: Both WebSocket endpoints (`monitoring_websocket`, `alerts_websocket`) now validate token type (`payload.get("type") != "access"`), check token blacklist (`is_token_blacklisted`), and verify engagement membership (`_check_engagement_membership`). Connection limits enforced.
- **Evidence**: `src/api/routes/websocket.py:162-213` (monitoring), `258-310` (alerts).

### [RESOLVED] MEDIUM: Unauthenticated WebSocket status endpoint
- **Resolution**: `src/api/routes/websocket.py:349-356` now has `current_user: User = Depends(get_current_user)`.
- **Evidence**: Endpoint requires authentication.

### [RESOLVED] MEDIUM: Unauthenticated MCP endpoints expose tool definitions
- **Resolution**: Both `/mcp/info` and `/mcp/tools` now include `client: dict[str, Any] = Depends(_verify_mcp_auth)`.
- **Evidence**: `src/mcp/server.py:47` and `src/mcp/server.py:120`.

### [RESOLVED] MEDIUM: List engagement members has no access control
- **Resolution**: `src/api/routes/users.py:355` now includes `_engagement_user: User = Depends(require_engagement_access)`.
- **Evidence**: Engagement membership is verified.

### [RESOLVED] MEDIUM: `auth_dev_mode` defaults to True
- **Resolution**: `src/core/config.py:68` now has `auth_dev_mode: bool = False`.
- **Evidence**: Default is `False`. Production validator also blocks `auth_dev_mode=True` in non-dev.

### [RESOLVED] MEDIUM: Admin key rotation error response leaks exception details
- **Resolution**: `src/api/routes/admin.py:97-98` now returns a generic message without the raw exception: `"Key rotation failed and was rolled back. {rotated} credentials were NOT persisted."`.
- **Evidence**: The `Error: {e}` suffix has been removed.

---

## Current Findings

### HIGH

#### [H-01] MULTI-TENANCY: Incomplete engagement access enforcement across routes

**File**: Multiple route files (see table below)
**Agent**: A1 (AuthZ Auditor)

**Description**: While `require_engagement_access` has been added to many endpoints,
a significant number of engagement-scoped endpoints still lack this dependency. The
pattern is "Swiss cheese" -- some endpoints in a module are protected and others are
not. An attacker who discovers an unprotected endpoint can bypass multi-tenancy
isolation for that specific operation.

The following table lists route files and endpoints that accept an `engagement_id`
parameter (in path, query, or request body) but do NOT enforce
`require_engagement_access`:

| Route File | Unprotected Endpoints | Protected Endpoints |
|---|---|---|
| `evidence.py` | `upload_evidence`, `get_evidence`, `list_evidence`, `update_validation_status`, `batch_validate`, `get_fragments` (6 total) | None |
| `monitoring.py` | `create_monitoring_job`, `list_monitoring_jobs`, `get_monitoring_job`, `activate_monitoring_job`, `pause_monitoring_job`, `stop_monitoring_job`, `update_monitoring_job`, `create_baseline`, `list_baselines`, `list_deviations`, `get_deviation`, `list_alerts`, `get_alert`, `alert_action` (14 total) | `get_monitoring_stats` (1) |
| `simulations.py` | `create_scenario`, `list_scenarios`, `get_scenario`, `run_scenario`, `add_modification`, `list_modifications`, `remove_modification`, `get_coverage`, `compare_scenarios`, `get_results`, `get_epistemic_plan`, `get_financial_impact`, `create_suggestion`, `list_suggestions`, `update_suggestion_disposition`, all financial assumption endpoints (16+ total) | `rank_scenarios` (1) |
| `pov.py` | `trigger_pov_generation`, `get_job_status`, all model retrieval endpoints (7 total) | None |
| `conformance.py` | All endpoints: `create_reference_model`, `check_conformance`, `get_conformance_result`, `list_conformance_results`, `compare_conformance_runs` (5 total) | None |
| `integrations.py` | All endpoints: `list_connections`, `create_connection`, `get_connection`, `update_connection`, `delete_connection`, `test_connection`, `sync_connection`, `get_field_mapping`, `update_field_mapping`, `list_connector_types` (10 total) | None |
| `shelf_requests.py` | All endpoints: `create_shelf_request`, `list_shelf_requests`, `get_shelf_request`, `get_shelf_request_status`, `update_shelf_request`, `submit_evidence_intake` (6 total) | None |
| `annotations.py` | `create_annotation`, `get_annotation`, `update_annotation`, `delete_annotation` (4 total) | `list_annotations` (1) |
| `regulatory.py` | `create_policy`, `list_policies`, `get_policy`, `create_control`, `list_controls`, `get_control`, `create_regulation`, `list_regulations`, `update_regulation` (9 total) | `build_governance_overlay`, `get_compliance_state`, `get_ungoverned_processes` (3) |
| `metrics.py` | `record_reading` (1) | `list_readings`, `get_metric_summary` (2) |
| `graph.py` | `build_graph`, `traverse_graph`, `semantic_search` (3) | `get_graph_stats`, `get_engagement_subgraph`, `export_cytoscape` (3) |
| `copilot.py` | `copilot_chat`, `copilot_chat_stream` (2) | `get_chat_history` (1) |
| `tom.py` | TOM CRUD (create, list, get, update, delete), gap CRUD, best practices, benchmarks (14+ total) | `get_alignment`, `get_maturity`, `prioritize_gaps`, `get_conformance_summary`, `get_roadmap`, `get_benchmarks` (6) |
| `governance.py` | Catalog CRUD, policy evaluation, SLA check, alerting (8+ total) | Export, migration, alert check, health (4) |
| `camunda.py` | All 6 endpoints | None |
| `taskmining.py` | All endpoints | None |

**Total unprotected endpoints**: ~110+ across 16 route files.

**Evidence**:
```python
# src/api/routes/evidence.py:131-139 — upload_evidence
@router.post("/upload", ...)
async def upload_evidence(
    ...
    engagement_id: UUID = Form(...),
    user: User = Depends(require_permission("evidence:create")),
    # MISSING: _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
```

```python
# src/api/routes/monitoring.py:222-227 — create_monitoring_job
@router.post("/jobs", ...)
async def create_monitoring_job(
    payload: MonitoringJobCreate,  # payload.engagement_id
    user: User = Depends(require_permission("monitoring:configure")),
    # MISSING: _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
```

**Risk**: A user with appropriate role permissions (e.g., `process_analyst` with
`evidence:create`) can upload evidence to, query data from, or modify resources in
ANY engagement, not just engagements they are members of. This defeats the
multi-tenancy isolation model.

**Recommendation**: Add `_engagement_user: User = Depends(require_engagement_access)`
to every endpoint that operates on engagement-scoped data. For endpoints that receive
`engagement_id` in the request body rather than the URL path, extract it and pass it
to the dependency. Prioritize: evidence (data exfiltration), monitoring (operational
data), simulations (business-sensitive), and integrations (may contain credentials).

---

#### [H-02] MULTI-TENANCY: `list_engagements` returns all engagements to any authenticated user

**File**: `src/api/routes/engagements.py:159-200`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/api/routes/engagements.py:159-200
@router.get("/", response_model=EngagementList)
async def list_engagements(
    ...
    user: User = Depends(require_permission("engagement:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    query = select(Engagement)  # No filtering by user membership
    ...
```

**Description**: The `list_engagements` endpoint returns all engagements in the
system to any user with `engagement:read` permission. Since every role from
`client_viewer` upward has `engagement:read`, every authenticated user can see
the names, clients, business areas, and statuses of ALL engagements in the platform.

Note that individual engagement endpoints (`get_engagement`, `update_engagement`,
`archive_engagement`, `get_dashboard`, `get_audit_logs`) DO enforce
`require_engagement_access`, but this listing endpoint reveals the existence and
metadata of all engagements.

**Risk**: Information disclosure of all engagement metadata. A `client_viewer`
from Client A can discover that the platform also serves Client B, see their
engagement names and business areas, and potentially infer competitive intelligence.

**Recommendation**: Use `filter_by_engagement_access()` from `src/core/security.py`
to scope the query to only engagements the user is a member of (platform admins
bypass). This helper already exists but is not called.

---

### MEDIUM

#### [M-01] PERMISSIONS: Taskmining permissions not defined in ROLE_PERMISSIONS matrix

**File**: `src/core/permissions.py:25-89`, `src/api/routes/taskmining.py`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/api/routes/taskmining.py:150 — uses "taskmining:write"
current_user: User = Depends(require_permission("taskmining:write")),

# src/api/routes/taskmining.py:194 — uses "taskmining:admin"
current_user: User = Depends(require_permission("taskmining:admin")),

# src/api/routes/taskmining.py:239 — uses "taskmining:read"
current_user: User = Depends(require_permission("taskmining:read")),
```
```python
# src/core/permissions.py:25-89 — ROLE_PERMISSIONS
# NONE of these permissions appear in any role:
# "taskmining:write" — not listed
# "taskmining:read" — not listed
# "taskmining:admin" — not listed
```

**Description**: The taskmining route module uses three permissions
(`taskmining:write`, `taskmining:read`, `taskmining:admin`) that do not exist in
the `ROLE_PERMISSIONS` matrix. Only `platform_admin` (which has wildcard `*`)
can access these endpoints. All other roles -- including `engagement_lead` -- will
receive 403 Forbidden.

This may be intentional (taskmining is a new feature gated to admins) or it may be
an oversight where the permissions were added to routes but not to the matrix.

**Risk**: If taskmining is intended to be used by non-admin roles, those users
are silently blocked. If intentional, this is not documented anywhere.

**Recommendation**: Either (a) add taskmining permissions to appropriate roles in
`ROLE_PERMISSIONS` (e.g., `engagement_lead` gets `taskmining:write` and
`taskmining:read`), or (b) add a code comment documenting that admin-only access
is intentional.

---

#### [M-02] CSRF: Cookie-based login lacks CSRF token protection

**File**: `src/api/routes/auth.py:221-274`, `src/core/auth.py:194-240`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/core/auth.py:221-226 — Access cookie uses SameSite=Lax
response.set_cookie(
    key=ACCESS_COOKIE_NAME,
    value=access_token,
    httponly=True,
    secure=secure,
    samesite="lax",  # Lax provides baseline CSRF protection but not complete
    ...
)
```

**Description**: The cookie-based authentication (Issue #156) relies on
`SameSite=Lax` as the sole CSRF protection mechanism. While `Lax` prevents
cookies from being sent on cross-origin POST requests initiated by forms or
JavaScript, it does NOT prevent:
1. Top-level GET navigations (the cookie IS sent on cross-site links)
2. Attacks that use same-site subdomains if the cookie domain is set broadly
3. Older browsers that do not support SameSite

No CSRF token is generated or validated on state-changing POST/PATCH/DELETE requests.

**Risk**: If an attacker can place content on a same-site subdomain (e.g., via a
compromised widget or user-generated content), they can perform state-changing
actions using the victim's cookies. The risk is MEDIUM because the primary API
clients use bearer tokens (not cookies) and SameSite=Lax provides adequate
protection for most cross-origin scenarios.

**Recommendation**: Implement a double-submit cookie CSRF token pattern. On login,
set a non-HttpOnly CSRF cookie. Require state-changing requests to include the
CSRF token in a custom header (e.g., `X-CSRF-Token`). The server validates that
the header matches the cookie.

---

#### [M-03] INFO-DISCLOSURE: Health endpoint exposes service topology without authentication

**File**: `src/api/routes/health.py:18-89`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/api/routes/health.py:18-19
@router.get("/api/v1/health")
async def health_check(request: Request) -> dict[str, Any]:
    # No authentication dependency
```

Returns:
```json
{
  "status": "degraded",
  "services": {
    "postgres": "up",
    "neo4j": "up",
    "redis": "down",
    "camunda": "down"
  },
  "version": "0.1.0"
}
```

**Description**: The health endpoint has no authentication and reveals which
backing services are deployed (PostgreSQL, Neo4j, Redis, Camunda), their
up/down status, and the application version. This information aids reconnaissance.

**Risk**: An attacker learns the exact technology stack and can identify which
services are degraded (potential attack targets). However, this is a standard
pattern for health checks used by load balancers and monitoring systems.

**Recommendation**: Split into two endpoints:
1. `/health` -- unauthenticated, returns only `{"status": "healthy"}` for load balancers
2. `/api/v1/admin/health` -- admin-only, returns full service details

---

#### [M-04] MCP: Tool execution errors leak internal exception details

**File**: `src/mcp/server.py:86-93`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/mcp/server.py:86-93
except Exception as e:
    logger.exception("MCP tool execution failed: %s", tool_name)
    return {
        "request_id": payload.request_id,
        "tool_name": tool_name,
        "success": False,
        "error": str(e),  # Raw exception string returned to client
    }
```

Also in the SSE streaming endpoint (`src/mcp/server.py:111`):
```python
yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
```

**Description**: When an MCP tool execution fails, the raw Python exception
message is returned to the client. This may contain database connection strings,
file paths, SQL query fragments, or other internal details.

**Risk**: Information disclosure to authenticated MCP clients. The risk is limited
because MCP clients are API-key authenticated, but a compromised key could be used
to probe for internal information via intentionally malformed tool calls.

**Recommendation**: Return a generic error message and log the full exception
server-side. Use a correlation ID so admins can match the client error to the
server log entry.

---

#### [M-05] MCP: No engagement-scoped access control on tool execution

**File**: `src/mcp/server.py:126-152`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# src/mcp/server.py:135-152 — _execute_tool dispatches directly
if tool_name == "get_engagement":
    return await _tool_get_engagement(session_factory, args)
elif tool_name == "list_evidence":
    return await _tool_list_evidence(session_factory, args)
# ... all tools execute without engagement membership check
```

**Description**: Once an MCP API key is validated, the client can call any tool
for any engagement. The `validate_api_key()` function returns a `user_id` in
the client info, but this user_id is never checked against engagement membership.
A valid API key can query engagement data, evidence, process models, gaps,
monitoring status, deviations, patterns, and run simulations for ANY engagement.

**Risk**: Cross-tenant data access via MCP. If an API key is issued to a user
for one engagement, they can use the MCP tools to access data from all engagements.

**Recommendation**: Extract `engagement_id` from tool arguments, look up the
`user_id` from the validated API key, and check `EngagementMember` table before
executing the tool. Platform admin keys can bypass this check.

---

### LOW

#### [L-01] LOGGING: User ID logged alongside client name in MCP auth

**File**: `src/mcp/auth.py:54, 83, 89, 96`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
logger.info("Generated API key %s for user %s, client %s", key_id, user_id, client_name)
logger.info("Validated API key %s for user %s", key_id, key_record.user_id)
```

**Description**: User UUIDs and client names are logged in MCP auth operations.
While key_ids are not secret, the combination of user_id + client_name could be
considered PII under GDPR log retention requirements.

**Risk**: Low. The secret portion of the API key is never logged. Log retention
policies should account for PII in these entries.

**Recommendation**: Review log retention policies. Consider structured logging
with redaction capabilities for PII fields.

---

#### [L-02] PASSWORD: Minimum password length is 8 characters

**File**: `src/api/routes/users.py:45`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
class UserCreate(BaseModel):
    password: str | None = Field(None, min_length=8)
```

**Description**: The minimum password length is 8 characters with no complexity
requirements (no uppercase, lowercase, digit, or special character rules). NIST
SP 800-63B recommends a minimum of 8 characters but also recommends checking
passwords against known breach databases and allowing up to 64 characters.

**Risk**: Low. The primary authentication mechanism is OIDC (not passwords). The
password field is used only in dev mode and for initial admin bootstrapping. In
production, `auth_dev_mode=False` disables the password-based `/token` endpoint
(though the `/login` endpoint remains active).

**Recommendation**: Add password complexity validation or integrate a breach
database check (e.g., HIBP). Consider whether the `/login` endpoint should also
be gated by `auth_dev_mode` if it is not intended for production use.

---

#### [L-03] COOKIE: `/login` endpoint not gated by `auth_dev_mode`

**File**: `src/api/routes/auth.py:221-274`
**Agent**: A1 (AuthZ Auditor)

**Evidence**:
```python
# /token IS gated:
@router.post("/token", ...)
async def get_token(...):
    if not settings.auth_dev_mode:
        raise HTTPException(status_code=403, detail="Dev-mode token endpoint is disabled")

# /login is NOT gated:
@router.post("/login", ...)
async def login(...):
    # No auth_dev_mode check — always available
```

**Description**: The `/api/v1/auth/token` endpoint (which returns raw JWT tokens)
is gated behind `auth_dev_mode`. The `/api/v1/auth/login` endpoint (cookie-based
auth, Issue #156) is always available, even in production. Both endpoints accept
email + password and authenticate the user against the database.

This is likely by design (the login endpoint is the production cookie-based auth
for browser clients), but it means password-based authentication is always active
regardless of `auth_dev_mode`.

**Risk**: Low. If the production deployment is intended to use OIDC exclusively,
the password-based login endpoint provides an alternative authentication path that
might not be monitored or expected.

**Recommendation**: Document whether `/login` is intended for production use. If
not, gate it behind `auth_dev_mode` like `/token`. If yes, ensure password-based
auth has appropriate monitoring and rate limiting (currently rate-limited to
5/minute, which is adequate).

---

## Engagement Access Control Status Matrix

The following table summarizes the current state of `require_engagement_access`
deployment across all route files that handle engagement-scoped data:

| Route File | Total Endpoints | Protected | Unprotected | Coverage |
|---|---|---|---|---|
| `engagements.py` | 7 | 5 | 2 (create, list) | 71% |
| `evidence.py` | 6 | 0 | 6 | 0% |
| `monitoring.py` | 15 | 1 | 14 | 7% |
| `simulations.py` | 17+ | 1 | 16+ | 6% |
| `pov.py` | 7 | 0 | 7 | 0% |
| `conformance.py` | 5 | 0 | 5 | 0% |
| `integrations.py` | 10 | 0 | 10 | 0% |
| `shelf_requests.py` | 6 | 0 | 6 | 0% |
| `annotations.py` | 5 | 1 | 4 | 20% |
| `regulatory.py` | 12 | 3 | 9 | 25% |
| `metrics.py` | 6 | 2 | 4 | 33% |
| `graph.py` | 6 | 3 | 3 | 50% |
| `copilot.py` | 3 | 1 | 2 | 33% |
| `tom.py` | 20+ | 6 | 14+ | 30% |
| `governance.py` | 12+ | 4 | 8+ | 33% |
| `camunda.py` | 6 | 0 | 6 | 0% |
| `taskmining.py` | 11 | 0 | 11 | 0% |
| `dashboard.py` | 3 | 3 | 0 | 100% |
| `portal.py` | 5 | 5 | 0 | 100% |
| `reports.py` | 4 | 4 | 0 | 100% |
| `lineage.py` | 2 | 2 | 0 | 100% |
| `users.py` (membership) | 3 | 3 | 0 | 100% |
| **Totals** | **~171** | **~44** | **~127** | **~26%** |

---

## Security Score

**Overall AuthZ Security Score: 6/10** (up from 3/10 on 2026-02-20)

### Improvements Since Last Audit (+3 points)
- JWT token type validation in `get_current_user` (+1)
- MCP DB-backed API key validation with HMAC (+1)
- `require_engagement_access` deployed to high-value endpoints (+0.5)
- WebSocket full auth (type check, blacklist, membership) (+0.5)
- Production secret validator blocks default keys (+0.5)
- `auth_dev_mode` defaults to `False` (+0.25)
- IDOR fixed in user profile endpoint (+0.25)

### Remaining Gaps (-4 points)
- ~74% of engagement-scoped endpoints still lack multi-tenancy enforcement (-2)
- MCP tools have no engagement-level access control (-0.5)
- No CSRF token protection for cookie-based auth (-0.5)
- Evidence routes (core data) completely unprotected for engagement access (-0.5)
- Taskmining permissions not in role matrix (-0.25)
- Health endpoint information disclosure (-0.25)

### Priority Remediation Order
1. **Evidence routes** -- These protect the core data asset. Add `require_engagement_access` to all 6 endpoints.
2. **Monitoring routes** -- Operational data with 14 unprotected endpoints. Add `require_engagement_access`.
3. **Simulation routes** -- Business-sensitive what-if analysis. Add `require_engagement_access`.
4. **Integration routes** -- May contain API keys in config. Add `require_engagement_access`.
5. **List engagements** -- Use `filter_by_engagement_access()` to scope the query.
6. **POV, conformance, shelf requests** -- Complete remaining modules.
7. **MCP engagement scoping** -- Add membership check to tool execution.
