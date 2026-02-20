# A1: Authorization & Authentication Audit Findings

**Auditor**: A1 (AuthZ Auditor)
**Date**: 2026-02-20
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 4     |
| MEDIUM   | 5     |
| LOW      | 2     |
| **Total** | **13** |

---

## CRITICAL Findings

### [CRITICAL] MULTI-TENANCY: `require_engagement_access` defined but never used

**File**: `src/core/permissions.py:188`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# src/core/permissions.py:188-227 — the function is defined:
async def require_engagement_access(
    engagement_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that checks engagement membership."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return user
    # ... checks EngagementMember table ...
```
```
# grep result — only match is the definition itself:
src/core/permissions.py:188:async def require_engagement_access(
```

**Description**: The `require_engagement_access` dependency is implemented in `permissions.py` but is never imported or used by any route file. All 26 route modules use only `require_permission` or `require_role`, which check the user's global role but do NOT verify that the user is a member of the specific engagement being accessed.

This means a `process_analyst` with `engagement:read` permission can read ALL engagements, evidence, monitoring data, dashboards, etc. across the entire platform -- not just the engagements they are assigned to.

Similarly, `get_accessible_engagement_ids` and `filter_by_engagement_access` (defined in `src/core/security.py`) are never called from any route.

**Risk**: Complete multi-tenancy bypass. Any authenticated user can access any engagement's data regardless of membership. This is the most severe security finding in this audit.

**Recommendation**: Add `Depends(require_engagement_access)` to every route that takes an `engagement_id` parameter. This affects routes in: `engagements.py`, `evidence.py`, `dashboard.py`, `monitoring.py`, `graph.py`, `pov.py`, `tom.py`, `copilot.py`, `portal.py`, `shelf_requests.py`, `conformance.py`, `reports.py`, `regulatory.py`, `simulations.py`, `lineage.py`, `annotations.py`, `camunda.py`, `metrics.py`, `integrations.py`, and `patterns.py`.

---

### [CRITICAL] MCP-AUTH: `verify_api_key()` validates format only, no DB lookup

**File**: `src/mcp/auth.py:129-144`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
def verify_api_key(api_key: str) -> dict[str, Any] | None:
    """Synchronous API key verification (backward-compatible).
    ...skips DB lookup.
    """
    if "." not in api_key:
        return None
    key_id, _raw = api_key.split(".", 1)
    if not key_id.startswith("kmflow_"):
        return None
    # Return basic client info — full validation happens in the async path
    return {"key_id": key_id, "client_name": "mcp_client"}
```
```python
# src/mcp/server.py:33-34 — this is what the MCP server actually calls:
api_key = auth[7:]
client = verify_api_key(api_key)
```

**Description**: The MCP server's `_verify_mcp_auth` dependency calls the synchronous `verify_api_key()` which only checks that the key starts with `kmflow_` and contains a dot separator. It does NOT validate the secret portion against the database. Any string matching `kmflow_XXXX.anything` will authenticate successfully. The async `validate_api_key()` that performs actual DB-backed validation exists but is never used in the server.

Additionally, MCP tool handlers have no engagement-level access control -- once authenticated with any key format, a client can query any engagement's data.

**Risk**: Full MCP endpoint bypass. An attacker can forge API keys trivially. Combined with the multi-tenancy gap, this provides unauthenticated access to all engagement data via MCP tools.

**Recommendation**:
1. Replace `verify_api_key()` call in `_verify_mcp_auth` with the async `validate_api_key()` using a database session
2. Add engagement-scoped access control to MCP tool handlers
3. Remove or deprecate the sync `verify_api_key()` function

---

## HIGH Findings

### [HIGH] JWT: Refresh tokens accepted as access tokens

**File**: `src/core/auth.py:190-260`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# create_access_token sets type claim:
to_encode.update({"exp": expire, "type": "access"})   # line 79

# create_refresh_token sets type claim:
to_encode.update({"exp": expire, "type": "refresh"})   # line 103

# get_current_user NEVER checks the "type" claim:
async def get_current_user(...) -> User:
    token = credentials.credentials
    payload = decode_token(token, settings)
    # checks blacklist, extracts "sub" — but never checks payload["type"]
```

**Description**: Both access and refresh tokens include a `type` claim ("access" or "refresh"), but `get_current_user` never validates that the presented token is an access token. A refresh token (valid for 7 days) can be used as a bearer token to access any protected endpoint, effectively making the 30-minute access token expiry meaningless.

Note: The `/api/v1/auth/refresh` endpoint correctly checks `decoded.get("type") != "refresh"`, but the inverse check is missing in `get_current_user`.

**Risk**: Token expiry bypass. If a refresh token is leaked, it provides 7 days of API access instead of 30 minutes. Negates the security benefit of short-lived access tokens.

**Recommendation**: Add `if payload.get("type") != "access": raise HTTPException(401)` in `get_current_user` after `decode_token`.

---

### [HIGH] SECRETS: Default JWT secret in config

**File**: `src/core/config.py:61`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
jwt_secret_key: str = "dev-secret-key-change-in-production"
encryption_key: str = "dev-encryption-key-change-in-production"
```

**Description**: The JWT signing key and encryption key have hardcoded default values. If the application starts without setting `JWT_SECRET_KEY` and `ENCRYPTION_KEY` environment variables, all tokens are signed with a publicly known key. There is no startup validation to prevent the application from running with these defaults in non-development environments.

**Risk**: In production, if environment variables are misconfigured, any attacker who reads the source code (or this audit) can forge valid JWT tokens and decrypt all stored credentials.

**Recommendation**:
1. Add a startup check: if `app_env != "development"` and `jwt_secret_key` contains "dev-secret-key", raise a fatal error
2. Consider using Pydantic `SecretStr` for these fields to prevent accidental logging
3. Remove the default values entirely and require explicit configuration

---

### [HIGH] IDOR: Users endpoint allows any authenticated user to view any user's profile

**File**: `src/api/routes/users.py:159-173`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),  # only checks authentication
) -> User:
    """Get a user by ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    # No check: current_user.id == user_id or current_user is admin
```

**Description**: The `GET /api/v1/users/{user_id}` endpoint requires only authentication (via `get_current_user`) but does NOT check whether the requesting user is the target user or a platform admin. Any authenticated user can enumerate and view the profile of any other user. While the returned data (email, name, role, is_active) is not highly sensitive, this is an IDOR pattern that should be locked down.

**Risk**: User enumeration and information disclosure. A `client_viewer` can view admin user profiles, discover other users' roles, and identify active accounts.

**Recommendation**: Either restrict to admins only (like list/create/update) or add a check that `current_user.id == user_id or has_role_level(current_user, UserRole.PLATFORM_ADMIN)`.

---

### [HIGH] WEBSOCKET: WebSocket authentication does not check engagement access or token blacklist

**File**: `src/api/routes/websocket.py:105-134`
**Agent**: A1 (AuthZ Auditor)
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
        decode_token(token, settings)  # Only validates JWT signature + expiry
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    # No blacklist check, no engagement membership check
    await manager.connect(websocket, engagement_id)
```

**Description**: WebSocket authentication calls `decode_token()` which verifies the JWT signature and expiry, but:
1. Does NOT check the token blacklist (a revoked/logged-out token still works)
2. Does NOT verify the user is a member of the engagement
3. Does NOT extract or use the user identity at all

This applies to both `/ws/monitoring/{engagement_id}` and `/ws/alerts/{engagement_id}`.

**Risk**: A logged-out user or a user from a different engagement can subscribe to real-time monitoring events for any engagement. Combined with the token type issue, a refresh token could be used for long-lived WebSocket connections.

**Recommendation**:
1. Extract user ID from the decoded payload and check blacklist
2. Verify engagement membership
3. Validate token type is "access"

---

## MEDIUM Findings

### [MEDIUM] AUTHZ: Unauthenticated WebSocket status endpoint leaks engagement IDs

**File**: `src/api/routes/websocket.py:260-266`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/api/v1/ws/status")
async def websocket_status() -> dict[str, Any]:
    """Get WebSocket connection status."""
    return {
        "active_connections": manager.active_connections,
        "engagement_ids": manager.get_engagement_ids(),
    }
```

**Description**: The `/api/v1/ws/status` endpoint has no authentication dependency. It returns the list of active engagement IDs that have WebSocket connections. This is an information disclosure that reveals which engagements are actively being monitored.

**Risk**: Unauthenticated users can discover active engagement UUIDs, which can be used to target other endpoints.

**Recommendation**: Add `Depends(get_current_user)` and restrict to platform admins.

---

### [MEDIUM] AUTHZ: Unauthenticated MCP endpoints expose tool definitions

**File**: `src/mcp/server.py:43-51, 114-117`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/info", response_model=MCPServerInfo)
async def server_info() -> dict[str, Any]:
    """Get MCP server information and available tools."""
    return {"name": "kmflow", "version": "0.1.0", ...}

@router.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    """List available MCP tools."""
    return TOOL_DEFINITIONS
```

**Description**: The `/mcp/info` and `/mcp/tools` endpoints do not require authentication. They expose the full list of MCP tool definitions including names, descriptions, and parameter schemas, giving attackers a detailed map of the attack surface.

**Risk**: Information disclosure aids reconnaissance. An attacker learns exactly which tools and parameters are available before needing to forge an API key.

**Recommendation**: Add `Depends(_verify_mcp_auth)` to these endpoints.

---

### [MEDIUM] AUTHZ: List engagement members has no access control beyond authentication

**File**: `src/api/routes/users.py:305-321`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/api/v1/engagements/{engagement_id}/members", response_model=list[MemberResponse])
async def list_engagement_members(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),  # only authentication
) -> list[EngagementMember]:
    """List all members of an engagement."""
    # No permission check, no engagement membership check
```

**Description**: Any authenticated user can list the members of any engagement. This exposes which users belong to which engagement, including their user IDs. Combined with the IDOR in the user profile endpoint, this allows full user enumeration per engagement.

**Risk**: Information disclosure of engagement team composition. A `client_viewer` from Engagement A can discover the full team list of Engagement B.

**Recommendation**: Add `require_engagement_access` dependency or at minimum `require_permission("engagement:read")`.

---

### [MEDIUM] JWT: `auth_dev_mode` defaults to True

**File**: `src/core/config.py:66`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
auth_dev_mode: bool = True  # Allow local dev tokens
```
```python
# src/api/routes/auth.py:99 — token endpoint checks this flag:
if not settings.auth_dev_mode:
    raise HTTPException(status_code=403, detail="Dev-mode token endpoint is disabled")
```

**Description**: The `auth_dev_mode` flag defaults to `True`, enabling the email+password token endpoint. If `AUTH_DEV_MODE` is not explicitly set to `False` in production, attackers can obtain tokens via the dev login endpoint using any seeded user credentials. Combined with the default JWT secret, this is a full authentication bypass path.

**Risk**: In production with misconfigured environment, the dev-mode token endpoint is exposed, allowing password-based authentication that may bypass the intended OIDC flow.

**Recommendation**: Default `auth_dev_mode` to `False`. Add a startup warning if `auth_dev_mode` is `True` and `app_env` is not `development`.

---

### [MEDIUM] ADMIN: Key rotation error response leaks internal exception details

**File**: `src/api/routes/admin.py:96-99`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
except Exception as e:
    await session.rollback()
    logger.error("Key rotation failed after %d credentials, rolled back: %s", rotated, e)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Key rotation failed and was rolled back. {rotated} credentials were NOT persisted. Error: {e}",
    ) from e
```

**Description**: The key rotation endpoint includes the raw exception message in the HTTP response. While the endpoint is restricted to platform admins, internal error details (which may include database errors, encryption key issues, or file paths) should not be returned to clients.

**Risk**: Information disclosure of internal implementation details to admin users, which could aid further attack if an admin account is compromised.

**Recommendation**: Log the full error server-side and return a generic message: "Key rotation failed and was rolled back. Check server logs for details."

---

## LOW Findings

### [LOW] MCP-AUTH: Deprecated `datetime.utcnow()` usage

**File**: `src/mcp/auth.py:93`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
key_record.last_used_at = datetime.utcnow()
```

**Description**: `datetime.utcnow()` is deprecated in Python 3.12+ in favor of `datetime.now(UTC)`. The rest of the codebase (e.g., `src/core/auth.py:78`) correctly uses `datetime.now(UTC)`. This inconsistency is minor but could cause issues if timezone-aware comparisons are introduced later.

**Risk**: Timezone-naive datetime stored in a field that may be compared with timezone-aware datetimes, potentially causing comparison errors.

**Recommendation**: Replace with `datetime.now(UTC)` for consistency.

---

### [LOW] LOGGING: MCP auth logs key_id on validation -- acceptable but monitor for PII

**File**: `src/mcp/auth.py:54, 83, 89, 96`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
logger.info(f"Generated API key {key_id} for user {user_id}, client {client_name}")
logger.warning(f"API key {key_id} not found or inactive")
logger.warning(f"API key {key_id} hash mismatch")
logger.info(f"Validated API key {key_id} for user {key_record.user_id}")
```

**Description**: The MCP auth module logs key_id values (the non-secret prefix, e.g., `kmflow_abcdef01`), user UUIDs, and client names. While key_ids are not secret (they are analogous to usernames), logging user UUIDs alongside client names could create PII in logs that may need to be handled under data retention policies.

**Risk**: Low. The secret portion of the API key is never logged. However, user_id + client_name in logs could be considered PII under GDPR.

**Recommendation**: Review log retention policies. Consider structured logging with redaction capabilities for PII fields.

---

## Engagement Access Control Gap Analysis

The following table shows which route files handle engagement-scoped data but do NOT use `require_engagement_access`:

| Route File | Has `engagement_id` param | Uses `require_engagement_access` | Risk |
|---|---|---|---|
| `engagements.py` | Yes (6 endpoints) | No | Users can CRUD any engagement |
| `evidence.py` | Yes (upload, list) | No | Users can upload/view evidence for any engagement |
| `dashboard.py` | Yes (3 endpoints) | No | Users can view any engagement dashboard |
| `monitoring.py` | Yes (12+ endpoints) | No | Users can manage monitoring for any engagement |
| `graph.py` | Yes (6 endpoints) | No | Users can query/build graph for any engagement |
| `pov.py` | Yes (7 endpoints) | No | Users can generate/view POV for any engagement |
| `tom.py` | Yes (20+ endpoints) | No | Users can view TOM data for any engagement |
| `copilot.py` | Yes (2 endpoints) | No | Users can query copilot for any engagement |
| `portal.py` | Yes (5 endpoints) | No | Clients can view any engagement portal |
| `shelf_requests.py` | Yes (6 endpoints) | No | Users can manage shelf requests for any engagement |
| `conformance.py` | Yes (4 endpoints) | No | Users can check conformance for any engagement |
| `reports.py` | Yes (4 endpoints) | No | Users can generate reports for any engagement |
| `regulatory.py` | Yes (11 endpoints) | No | Users can view regulatory data for any engagement |
| `simulations.py` | Yes (16+ endpoints) | No | Users can run simulations for any engagement |
| `lineage.py` | Yes (2 endpoints) | No | Users can view lineage for any engagement |
| `annotations.py` | Yes (5 endpoints) | No | Users can CRUD annotations for any engagement |
| `camunda.py` | Yes (6 endpoints) | No | Users can deploy/manage processes for any engagement |
| `metrics.py` | Yes (7 endpoints) | No | Users can manage metrics for any engagement |
| `integrations.py` | Yes (10 endpoints) | No | Users can manage integrations for any engagement |
| `governance.py` | Yes (multiple) | No | Users can manage governance for any engagement |
| `websocket.py` | Yes (2 WS endpoints) | No | Users can subscribe to events for any engagement |

**Total affected endpoints**: ~130+ across 21 route files.

---

## Security Score

**Overall AuthZ Security Score: 3/10**

The platform has well-designed authentication infrastructure (JWT with rotation, bcrypt hashing, token blacklisting, rate limiting) but critically lacks enforcement of engagement-level authorization. The RBAC system only gates access by role (what actions a user can perform) but not by scope (which engagements they can access). This is a fundamental multi-tenancy isolation failure that must be addressed before production deployment.
