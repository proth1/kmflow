# A1: Authorization & Authentication Audit

**Agent**: A1 (AuthZ Auditor)
**Date**: 2026-03-20
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication, CSRF protection

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 3 |
| MEDIUM   | 4 |
| LOW      | 5 |
| **Total** | **13** |

## Lessons Learned Counts

1. **Routes missing `response_model=`**: ~55 routes (across assumptions, survey_claims, survey_sessions, transformation_templates, replay, governance export, raci export, decisions, cost_modeling, sensitivity, regulatory overlay/compliance/ungoverned, assessment_matrix, reports, scenario_comparison, evidence_coverage, suggestion_feedback, scenario_simulation, admin, ws/status, tom export, copilot stream, evidence download, seed_lists, portal upload)
2. **ID routes missing engagement access checks**: 0 significant gaps (most engagement-scoped routes use `require_engagement_access` or manual membership checks)
3. **Broad `except Exception` without justification comment**: 28 total across route files; 23 have justification comments ("Intentionally broad" or contextual logging), 5 lack explicit justification (validation.py:680, validation.py:697, pipeline_quality.py:416/421/426/434/439, graph.py:272/286, engagements.py:332, auth.py:56/104/119, tom.py:1739/1750/1761, reports.py:229, semantic.py:367, regulatory.py:283, scenario_simulation.py:205, integrations.py:105, copilot.py:198)

---

## Findings

### [CRITICAL] AUTH-BYPASS: Dev mode auto-authenticates as platform_admin without token

**File**: `src/core/auth.py:372-382`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Dev mode: auto-authenticate as the first platform_admin user
if settings.auth_dev_mode:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)
        )
        dev_user = result.scalar_one_or_none()
```
**Description**: When `auth_dev_mode=True`, any request without a token is auto-authenticated as the first `platform_admin` user in the database. This grants full administrative access with zero authentication. While dev mode requires `DEBUG=true` and is blocked in non-development environments by the `reject_default_secrets_in_production` validator (`src/core/config.py:237`), a misconfigured deployment could expose the entire system.
**Risk**: If `APP_ENV=development` and `DEBUG=true` leak into a staging/production deployment, all endpoints become unauthenticated with admin privileges.
**Recommendation**: Add an additional safeguard: bind dev mode to an explicit allowlist of IP addresses (e.g., `127.0.0.1` only) or require a dev-mode header. Log a WARN-level message on every auto-auth invocation (currently DEBUG level at line 381).

---

### [HIGH] TOKEN-BLACKLIST-FAIL-OPEN: Logout does not verify blacklisting succeeded

**File**: `src/api/routes/auth.py:486-492`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Blacklist the access token
await blacklist_token(request, token)

# Also blacklist the refresh token if present (prevents reuse after logout)
refresh_token_value = request.cookies.get(REFRESH_COOKIE_NAME)
if refresh_token_value:
    await blacklist_token(request, refresh_token_value, expires_in=settings.jwt_refresh_token_expire_minutes * 60)
```
And in `src/core/auth.py:166-178`:
```python
async def blacklist_token(request: Request, token: str, expires_in: int = 1800) -> None:
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(f"token:blacklist:{token}", expires_in, "1")
    except (ConnectionError, OSError, _aioredis.RedisError):
        logger.warning("Redis unavailable for token blacklisting")
```
**Description**: The `blacklist_token` function silently swallows Redis connection errors. When Redis is unavailable during logout, the user receives a success response ("Logged out") but the token remains valid. The `is_token_blacklisted` function correctly fails closed (returns `True` when Redis is down), but this creates an inconsistency: tokens blacklisted during a Redis outage will appear valid once Redis recovers.
**Risk**: During Redis outage windows, logout operations silently fail. Tokens remain usable after the user believes they logged out. If Redis was briefly down and comes back, previously "logged-out" tokens are still valid.
**Recommendation**: Either (a) return a warning to the client that logout may not have fully completed, or (b) raise an error prompting retry, or (c) keep a local fallback blacklist.

---

### [HIGH] CSRF-COOKIE-NOT-CRYPTOGRAPHICALLY-BOUND: CSRF token has no server-side binding

**File**: `src/core/auth.py:252-253` and `src/api/middleware/csrf.py:58`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# In auth.py — cookie set on login
csrf_token = secrets.token_urlsafe(32)
response.set_cookie(key=CSRF_COOKIE_NAME, value=csrf_token, httponly=False, ...)

# In csrf.py — validation
if not hmac.compare_digest(csrf_cookie, csrf_header):
    return Response(content='{"detail":"CSRF token mismatch"}', status_code=403, ...)
```
**Description**: The CSRF implementation uses the double-submit cookie pattern, where the same random value is placed in both a cookie and a header. The server only checks that the cookie value matches the header value. There is no server-side HMAC or session binding. An attacker who can set a cookie on the target domain (e.g., via a subdomain XSS or cookie injection) can set both the cookie and the header to matching values and bypass CSRF protection entirely.
**Risk**: Cookie injection on the same domain or any subdomain of `cookie_domain` defeats CSRF protection for all mutation endpoints.
**Recommendation**: Sign the CSRF cookie value with a server-side secret (e.g., HMAC with the session token or user ID). On validation, verify the HMAC signature rather than just comparing raw values. This prevents an attacker from forging a valid cookie+header pair.

---

### [HIGH] ADMIN-ROUTES-NO-RESPONSE-MODEL: Admin endpoints lack response_model filtering

**File**: `src/api/routes/admin.py:26`, `src/api/routes/admin.py:63`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.post("/retention-cleanup")
async def run_retention_cleanup(
    user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    ...
) -> dict[str, Any]:

@router.post("/rotate-encryption-key")
async def rotate_encryption_key(
    user: User = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    ...
) -> dict[str, Any]:
```
**Description**: Admin endpoints return `dict[str, Any]` without a `response_model`. While these are admin-only routes, they return engagement names and IDs in the retention cleanup response. Without `response_model` filtering, any internal fields accidentally added to the response dict will be serialized to the client, potentially leaking sensitive internal state.
**Risk**: Data leakage through unfiltered response dictionaries on sensitive admin operations.
**Recommendation**: Define Pydantic response models for both admin endpoints to enforce explicit field allowlisting.

---

### [MEDIUM] WEBSOCKET-TOKEN-IN-QUERY-PARAM: JWT exposed in URL for WebSocket connections

**File**: `src/api/routes/websocket.py:153`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.websocket("/ws/monitoring/{engagement_id}")
async def monitoring_websocket(
    websocket: WebSocket,
    engagement_id: str,
    token: str | None = Query(default=None),
) -> None:
```
**Description**: WebSocket endpoints accept JWT tokens as query parameters (`?token=<jwt>`). Query parameters are logged by web servers, proxies, and CDNs, and may appear in browser history. While the endpoint also supports cookie-based auth, the query parameter option creates a token exposure risk.
**Risk**: JWT tokens in server access logs, proxy logs, and browser history. Token theft from log aggregation systems.
**Recommendation**: Document that cookie-based auth is the preferred WebSocket authentication method. Consider deprecating the query parameter option, or at minimum ensure reverse proxies are configured to strip token parameters from access logs.

---

### [MEDIUM] MCP-RATE-LIMIT-IN-MEMORY: MCP API key rate limiting uses process-local dict

**File**: `src/mcp/auth.py:27-29`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Per-key-id rate limiting for failed validation attempts.
# key_id -> (fail_count, window_start_epoch)
_FAILED_ATTEMPTS: dict[str, tuple[int, float]] = {}
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes
```
**Description**: The MCP API key rate limiting uses a process-local Python dictionary. In a multi-worker deployment (multiple uvicorn workers behind a load balancer), each worker maintains its own counter. An attacker can distribute brute-force attempts across workers, effectively multiplying the attempt limit by the number of workers.
**Risk**: Rate limiting bypass in multi-worker deployments. An attacker gets `N * 5` attempts per 5-minute window where N is the worker count.
**Recommendation**: Move rate limiting to Redis (consistent with the auth route pattern in `src/api/routes/auth.py` which uses Redis-backed rate limiting via slowapi).

---

### [MEDIUM] ROLE-CLAIM-NOT-REVALIDATED: JWT role claim not checked against DB on each request

**File**: `src/core/auth.py:350-444`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def get_current_user(...) -> User:
    # ...decode token, extract user_id...
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    # User role is read from DB here, which is correct
```
**Description**: The `get_current_user` function fetches the user from the database on every request, which correctly reflects the current role. However, the JWT token itself contains a `role` claim (set at login time in `src/api/routes/auth.py:250-252`). If any downstream code reads the role from the JWT payload instead of the User object, a role change would not take effect until the token expires.
**Risk**: Low in current implementation since `get_current_user` fetches from DB. However, JWT `role` claim could mislead future developers into using the stale claim.
**Recommendation**: Either (a) remove the `role` claim from JWTs (since it's always re-fetched from DB), or (b) add a code comment clarifying that the JWT role is informational only and the DB role is authoritative.

---

### [MEDIUM] REFRESH-COOKIE-PATH-MISMATCH: Refresh cookie path may not cover /refresh/cookie endpoint

**File**: `src/core/auth.py:193`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
```
And the cookie-based refresh endpoint is at:
```python
# src/api/routes/auth.py:382
@router.post("/refresh/cookie", response_model=RefreshCookieResponse)
```
Which resolves to `/api/v1/auth/refresh/cookie`.
**Description**: The refresh cookie is path-restricted to `/api/v1/auth/refresh`. The cookie-based refresh endpoint is at `/api/v1/auth/refresh/cookie`. Since cookie path matching is prefix-based, `/api/v1/auth/refresh` does cover `/api/v1/auth/refresh/cookie`. This is correct but fragile — if the endpoint were moved to a sibling path (e.g., `/api/v1/auth/cookie-refresh`), the cookie would silently stop being sent.
**Risk**: Low currently (path prefix matching works), but fragile to refactoring.
**Recommendation**: Add a comment documenting the path prefix dependency, or use a more explicit path like `/api/v1/auth/refresh` with a query parameter to distinguish body vs cookie mode.

---

### [LOW] BROAD-EXCEPT-WITHOUT-JUSTIFICATION: Several except Exception blocks lack justification

**File**: Multiple files (see list below)
**Agent**: A1 (AuthZ Auditor)
**Evidence**: The following `except Exception` blocks lack the "Intentionally broad" justification comment:
- `src/api/routes/validation.py:680` — background task failure
- `src/api/routes/validation.py:697` — sentinel write failure
- `src/api/routes/pipeline_quality.py:416,421,426,434,439` — dashboard partial failures
- `src/api/routes/graph.py:272,286` — Redis cache failures
- `src/api/routes/engagements.py:332` — graph cleanup failure
- `src/api/routes/auth.py:56,104,119` — settings/lockout failures
- `src/api/routes/tom.py:1739,1750,1761` — background scoring failures
- `src/api/routes/reports.py:229` — report generation failure
- `src/api/routes/semantic.py:367` — label query failure
- `src/api/routes/regulatory.py:283` — Neo4j cleanup failure
- `src/api/routes/scenario_simulation.py:205` — simulation failure
- `src/api/routes/integrations.py:105` — decryption fallback

**Description**: While many broad exception handlers in WebSocket code have "Intentionally broad" comments (good practice), approximately 20 handlers in non-WebSocket code lack justification.
**Risk**: Broad exception handling can mask bugs and security issues. Without justification, it's unclear whether these are intentional fail-safe patterns or oversight.
**Recommendation**: Add a brief justification comment to each broad exception handler explaining why it's necessary (e.g., "fail-open for dashboard partial render" or "background task must not crash worker").

---

### [LOW] ROUTES-MISSING-RESPONSE-MODEL: ~55 route handlers lack response_model

**File**: Multiple (see Lessons Learned section above)
**Agent**: A1 (AuthZ Auditor)
**Description**: Approximately 55 route handlers across the codebase use `-> dict[str, Any]` returns without `response_model=` in the decorator. This means FastAPI will not strip unexpected fields from the response, potentially leaking internal data.
**Risk**: Unintentional data exposure through unfiltered response dicts.
**Recommendation**: Add Pydantic `response_model` to all route handlers, especially those handling sensitive data (governance export, evidence download, GDPR exports, admin endpoints).

---

### [LOW] ENGAGEMENT-ACCESS-REQUIRE-VS-CHECK: Two different engagement access patterns create inconsistency

**File**: `src/core/permissions.py:202` and `src/core/permissions.py:282`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Pattern 1: FastAPI dependency (path param)
async def require_engagement_access(engagement_id: UUID, request: Request, user: User = Depends(get_current_user)) -> User:

# Pattern 2: Plain async function (for non-path-param usage)
async def check_engagement_access(engagement_id: UUID, request: Request, user: User) -> None:

# Pattern 3: Session-based with RLS context setting
async def verify_engagement_member(session: AsyncSession, user: User, engagement_id: UUID) -> None:
```
**Description**: Three different functions serve similar purposes with slightly different signatures and behaviors. `verify_engagement_member` also sets RLS context, while the other two do not. Routes that use `require_engagement_access` do not get RLS context set automatically.
**Risk**: Developers may choose the wrong function, leading to inconsistent RLS enforcement.
**Recommendation**: Consolidate to fewer patterns and document when each should be used. Consider having `require_engagement_access` also set RLS context.

---

### [LOW] WEBSOCKET-STATUS-EXPOSES-ENGAGEMENT-IDS: WebSocket status endpoint leaks engagement IDs

**File**: `src/api/routes/websocket.py:410-418`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/api/v1/ws/status")
async def websocket_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "active_connections": manager.active_connections,
        "engagement_ids": manager.get_engagement_ids(),
    }
```
**Description**: The WebSocket status endpoint returns all engagement IDs with active WebSocket connections. Any authenticated user can call this endpoint and discover which engagements are currently being actively monitored. There is no role check or engagement membership filtering.
**Risk**: Information disclosure — any authenticated user can enumerate active engagement IDs, even if they are not a member of those engagements.
**Recommendation**: Either restrict this endpoint to platform admins, or filter the returned engagement IDs to only those the requesting user has access to.

---

### [LOW] JWT-ALGORITHM-HARDCODED-HS256: HS256 symmetric algorithm used for JWT signing

**File**: `src/core/config.py:66`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
jwt_algorithm: str = "HS256"
```
**Description**: The platform uses HS256 (HMAC-SHA256) for JWT signing, which is a symmetric algorithm. All services that need to verify tokens must share the same secret key. In a microservices architecture, this means the signing key is distributed to every service, increasing the attack surface.
**Risk**: Compromise of any service that holds the JWT secret allows token forgery for any user/role.
**Recommendation**: For a multi-service deployment, consider migrating to RS256 (asymmetric) so that only the auth service holds the private key while other services verify with the public key. HS256 is acceptable for a monolithic deployment.

---

## Security Posture Assessment

**Overall Score**: 7/10

**Strengths**:
- Comprehensive RBAC with 5 roles and fine-grained permission matrix
- Token blacklisting with fail-closed behavior on Redis unavailability
- Refresh token rotation on use (old token blacklisted)
- Rate limiting on auth endpoints (IP-based + per-email lockout)
- CSRF double-submit cookie pattern with SameSite=Lax baseline
- Dev mode requires DEBUG=true and is blocked in non-development environments
- IDOR prevention on user profile endpoints
- Engagement membership checks on most engagement-scoped routes
- MCP API key validation uses DB-backed hash comparison with HMAC timing-safe comparison and per-key rate limiting

**Areas for Improvement**:
- CSRF cookie should be cryptographically bound to the session
- Dev mode auto-auth should have additional safeguards (IP restriction, WARN-level logging)
- MCP rate limiting should use Redis for multi-worker consistency
- Logout should handle Redis failures more explicitly
- Response models should be added to all routes for data filtering
- WebSocket token-in-URL pattern should be deprecated
