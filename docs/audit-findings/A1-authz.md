# A1: Authorization & Authentication Audit

**Agent**: A1 (AuthZ Auditor)
**Date**: 2026-03-20
**Cycle**: 7
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication, CSRF protection

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 2 |
| MEDIUM   | 4 |
| LOW      | 5 |
| **Total** | **12** |

## Lessons Learned Counts

1. **Routes missing `response_model=`**: ~55 routes (across assumptions, survey_claims, survey_sessions, transformation_templates, replay, governance export, raci export, decisions, cost_modeling, sensitivity, regulatory overlay/compliance/ungoverned, assessment_matrix, reports, scenario_comparison, evidence_coverage, suggestion_feedback, scenario_simulation, admin, ws/status, tom export, copilot stream, evidence download, seed_lists, portal upload)
2. **ID routes missing engagement access checks**: 4 routes in `graph.py` (`/build`, `/traverse/{node_id}`, `/search`, `/{engagement_id}/bridges/run`) have `require_permission` but no `require_engagement_access`
3. **Broad `except Exception` without justification comment**: ~20 handlers across non-WebSocket route files lack explicit justification (validation.py, pipeline_quality.py, graph.py, engagements.py, auth.py, tom.py, reports.py, semantic.py, regulatory.py, scenario_simulation.py, integrations.py, copilot.py)

---

## Findings

### [CRITICAL] AUTH-BYPASS: Dev mode auto-authenticates as platform_admin without token

**File**: `src/core/auth.py:386-403`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
if token is None:
    # Dev mode: auto-authenticate as the first platform_admin user
    if settings.auth_dev_mode:
        if settings.app_env not in ("development", "testing"):
            logger.critical(...)
            raise HTTPException(status_code=503, detail="Server misconfiguration")
        session_factory = request.app.state.db_session_factory
        async with session_factory() as session:
            result = await session.execute(
                select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)
            )
            dev_user = result.scalar_one_or_none()
        if dev_user is not None:
            logger.debug("Auth dev mode: auto-authenticated as user %s", dev_user.id)
            return dev_user
```
**Description**: When `auth_dev_mode=True`, any request without a token is auto-authenticated as the first `platform_admin` user. While guarded by `app_env not in ("development", "testing")` and the `reject_default_secrets_in_production` validator in `config.py:237-271`, the defense is still based on environment variable correctness. The logging level is DEBUG (line 402), meaning auto-auth events are invisible in default logging configurations. The `get_websocket_user` function (line 489) has the SAME dev mode fallback but LACKS the `app_env` guard entirely (see HIGH finding below).
**Risk**: If `APP_ENV=development` and `DEBUG=true` leak into a staging/production deployment, all endpoints become unauthenticated with admin privileges.
**Recommendation**: (1) Raise logging to WARN for every auto-auth invocation. (2) Bind dev mode to `127.0.0.1` only. (3) Add the `app_env` guard to `get_websocket_user` (see next finding).

**Mitigations present**:
- `reject_default_secrets_in_production` validator blocks startup with default secrets in non-development
- `validate_dev_mode_requires_debug` validator requires `DEBUG=true`
- `app_env` check in `get_current_user` (but missing in `get_websocket_user`)

---

### [HIGH] WS-DEV-MODE-NO-ENV-GUARD: WebSocket dev mode lacks app_env environment check

**File**: `src/core/auth.py:487-499`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def get_websocket_user(websocket: WebSocket, token: str | None = None) -> User | None:
    # ...
    if jwt_token is None:
        # Dev mode: return first active admin
        if settings.auth_dev_mode:
            session_factory = websocket.app.state.db_session_factory
            async with session_factory() as session:
                result = await session.execute(
                    select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)
                )
                dev_user = result.scalar_one_or_none()
            if dev_user is not None:
                logger.debug("WS auth dev mode: auto-authenticated as user %s", dev_user.id)
                return dev_user
        return None
```

Compare with `get_current_user` at line 388 which has:
```python
if settings.app_env not in ("development", "testing"):
    logger.critical("AUTH_DEV_MODE is enabled in %s environment — refusing...")
    raise HTTPException(status_code=503, detail="Server misconfiguration")
```
**Description**: `get_current_user` (HTTP) checks `app_env not in ("development", "testing")` before allowing dev-mode auto-auth. `get_websocket_user` (WebSocket) does NOT perform this check. If `auth_dev_mode` is accidentally enabled in a non-development environment, HTTP requests would be blocked by the `app_env` guard, but WebSocket connections would silently auto-authenticate as `platform_admin`.
**Risk**: WebSocket auth bypass in misconfigured environments where HTTP auth is properly guarded.
**Recommendation**: Add the same `app_env` check to `get_websocket_user` that exists in `get_current_user`.

---

### [HIGH] GRAPH-ROUTES-MISSING-ENGAGEMENT-ACCESS: Four graph routes lack engagement membership checks

**File**: `src/api/routes/graph.py:138-177, 181-212, 215-248, 390-425`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# /build — engagement_id from request body, no engagement access check
@router.post("/build", response_model=BuildResponse, ...)
async def build_graph(
    payload: BuildRequest,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:

# /traverse/{node_id} — no engagement scoping at all
@router.get("/traverse/{node_id}", ...)
async def traverse_graph(
    node_id: str,
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:

# /search — optional engagement_id, no access check when provided
@router.get("/search", ...)
async def semantic_search(
    engagement_id: UUID | None = None,
    user: User = Depends(require_permission("engagement:read")),
) -> list[dict[str, Any]]:

# /{engagement_id}/bridges/run — has engagement_id path param but no require_engagement_access
@router.post("/{engagement_id}/bridges/run", ...)
async def run_bridges(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
```

Compared to properly protected routes in the same file:
```python
# These correctly use BOTH permission AND engagement access checks
@router.get("/{engagement_id}/stats", ...)
async def get_graph_stats(
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),  # <-- present
)

@router.get("/{engagement_id}/subgraph", ...)
@router.get("/{engagement_id}/export/cytoscape", ...)
```
**Description**: Four routes in `graph.py` check `require_permission("engagement:read")` but do not verify engagement membership via `require_engagement_access`. The `/traverse` endpoint accepts arbitrary node IDs with no engagement scoping, allowing cross-engagement graph traversal. The `/build` endpoint takes `engagement_id` from the request body without membership verification. The `/bridges/run` endpoint has `engagement_id` as a path parameter but lacks the dependency. The `/search` endpoint accepts an optional `engagement_id` without verifying membership.
**Risk**: Any user with `engagement:read` permission (process_analyst, evidence_reviewer) can traverse, search, build, or run bridges on engagements they are not members of — cross-tenant data access.
**Recommendation**: Add `_engagement_user: User = Depends(require_engagement_access)` to `/build`, `/bridges/run`. For `/traverse`, require an engagement_id parameter and add the check. For `/search`, add membership verification when `engagement_id` is provided.

---

### [MEDIUM] TOKEN-BLACKLIST-FAIL-OPEN: Logout does not verify blacklisting succeeded

**File**: `src/core/auth.py:166-178`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def blacklist_token(request: Request, token: str, expires_in: int = 1800) -> None:
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(f"token:blacklist:{token}", expires_in, "1")
    except (ConnectionError, OSError, _aioredis.RedisError) as exc:
        logger.warning("Token blacklist write failed — token may remain valid: %s", exc)
```
**Description**: The `blacklist_token` function silently swallows Redis errors. `is_token_blacklisted` fails closed (returns `True` when Redis is down), but tokens "blacklisted" during an outage become valid once Redis recovers.
**Risk**: During Redis outage windows, logout operations silently fail. Tokens remain usable after the user believes they logged out.
**Recommendation**: Return blacklist success/failure status to the caller. Consider returning a warning to the client on logout if blacklisting fails.

---

### [MEDIUM] WEBSOCKET-TOKEN-IN-QUERY-PARAM: JWT exposed in URL for WebSocket connections

**File**: `src/api/routes/websocket.py` (WebSocket endpoints accept `token` query param)
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def monitoring_websocket(
    websocket: WebSocket,
    engagement_id: str,
    token: str | None = Query(default=None),
) -> None:
```
**Description**: WebSocket endpoints accept JWT tokens as query parameters. Query parameters are logged by web servers, proxies, and CDNs, and appear in browser history.
**Risk**: JWT tokens in server access logs, proxy logs, and browser history. Token theft from log aggregation systems.
**Recommendation**: Document cookie-based auth as the preferred WebSocket method. Consider deprecating the query parameter option.

---

### [MEDIUM] MCP-RATE-LIMIT-IN-MEMORY: MCP API key rate limiting uses process-local dict

**File**: `src/mcp/auth.py:27-29`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
_FAILED_ATTEMPTS: dict[str, tuple[int, float]] = {}
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes
```
**Description**: MCP API key brute-force protection uses a process-local dictionary. In multi-worker deployments, each worker maintains its own counter.
**Risk**: Rate limiting bypass — attacker gets `N * 5` attempts per 5-minute window where N is the worker count.
**Recommendation**: Move rate limiting to Redis (consistent with auth route rate limiting via slowapi).

---

### [MEDIUM] ROLE-CLAIM-NOT-REVALIDATED: JWT contains stale role claim

**File**: `src/api/routes/auth.py:247-252` and `src/core/auth.py:448`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Token creation includes role claim
claims = {
    "sub": str(user.id),
    "email": user.email,
    "name": user.name,
    "role": user.role.value,  # <-- embedded at login time
}
```
**Description**: The JWT contains a `role` claim set at login time. While `get_current_user` fetches the current role from the DB (correct), the JWT role claim could mislead downstream code or API consumers who decode the token.
**Risk**: Low in current implementation, but JWT role claim could diverge from DB role after a role change.
**Recommendation**: Either remove the `role` claim from JWTs or add a code comment clarifying the DB role is authoritative.

---

### [LOW] BROAD-EXCEPT-WITHOUT-JUSTIFICATION: Several except Exception blocks lack justification

**File**: Multiple files
**Agent**: A1 (AuthZ Auditor)
**Evidence**: The following `except Exception` blocks lack "Intentionally broad" justification comments:
- `src/api/routes/validation.py:680, 697`
- `src/api/routes/pipeline_quality.py:416, 421, 426, 434, 439`
- `src/api/routes/graph.py:272, 286`
- `src/api/routes/engagements.py:332`
- `src/api/routes/auth.py:56, 104, 119`
- `src/api/routes/tom.py:1739, 1750, 1761`
- `src/api/routes/reports.py:229`
- `src/api/routes/semantic.py:367`
- `src/api/routes/regulatory.py:283`
- `src/api/routes/scenario_simulation.py:205`
- `src/api/routes/integrations.py:105`

**Description**: ~20 broad exception handlers in non-WebSocket code lack justification comments.
**Risk**: Broad exception handling can mask bugs and security issues.
**Recommendation**: Add brief justification comments explaining why broad handling is necessary.

---

### [LOW] ROUTES-MISSING-RESPONSE-MODEL: ~55 route handlers lack response_model

**File**: Multiple (see Lessons Learned section)
**Agent**: A1 (AuthZ Auditor)
**Description**: Approximately 55 route handlers across the codebase use `-> dict[str, Any]` returns without `response_model=` in the decorator. FastAPI will not strip unexpected fields from the response.
**Risk**: Unintentional data exposure through unfiltered response dicts.
**Recommendation**: Add Pydantic `response_model` to all route handlers, especially those handling sensitive data.

---

### [LOW] ENGAGEMENT-ACCESS-PATTERNS: Three different engagement access patterns create inconsistency

**File**: `src/core/permissions.py:202, 244, 282`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
# Pattern 1: FastAPI dependency (path param)
async def require_engagement_access(engagement_id: UUID, ...) -> User:
# Pattern 2: Session-based with RLS context
async def verify_engagement_member(session: AsyncSession, ...) -> None:
# Pattern 3: Plain async function
async def check_engagement_access(engagement_id: UUID, ...) -> None:
```
**Description**: Three functions serve similar purposes with different signatures and behaviors. `verify_engagement_member` sets RLS context; the others do not. Routes using `require_engagement_access` do not get RLS context set.
**Risk**: Developers may choose the wrong function, leading to inconsistent RLS enforcement.
**Recommendation**: Consolidate patterns. Consider having `require_engagement_access` also set RLS context.

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
**Description**: Any authenticated user can enumerate all engagement IDs with active WebSocket connections, even engagements they are not a member of.
**Risk**: Information disclosure — engagement ID enumeration across tenants.
**Recommendation**: Restrict to platform admins or filter by user's engagement memberships.

---

### [LOW] JWT-ALGORITHM-HS256: Symmetric JWT algorithm limits microservices scalability

**File**: `src/core/config.py:66`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
jwt_algorithm: str = "HS256"
```
**Description**: HS256 requires the signing secret to be shared with all services that verify tokens. Acceptable for monolithic deployment but limits microservices scaling.
**Risk**: Compromise of any service holding the JWT secret allows token forgery.
**Recommendation**: Consider migrating to RS256 for multi-service deployments. HS256 is acceptable for current monolithic architecture.

---

## Cycle 7 Corrections from Cycle 6

### Previous HIGH finding "CSRF-COOKIE-NOT-CRYPTOGRAPHICALLY-BOUND" — **RETRACTED**

The cycle 6 audit incorrectly stated the CSRF token was `secrets.token_urlsafe(32)` with no server-side binding. The actual code at `src/core/auth.py:254-256` calls `generate_csrf_token(access_token)` from `src/api/middleware/csrf.py:86-94`, which computes `HMAC-SHA256(jwt_secret, access_token)`. The CSRF token IS cryptographically bound to the session via HMAC. Both `auth.py:344` (verify_csrf_token dependency) and `csrf.py:58-60` (CSRFMiddleware) validate by recomputing the HMAC and using `hmac.compare_digest`. This finding is removed.

### Previous HIGH finding "ADMIN-ROUTES-NO-RESPONSE-MODEL" — **DOWNGRADED to LOW**

Admin endpoints at `src/api/routes/admin.py:45,63` DO have `response_model=RetentionCleanupResponse` and `response_model=KeyRotationResponse` respectively. The cycle 6 evidence was incorrect. This is folded into the general LOW finding about routes missing response_model.

---

## Security Posture Assessment

**Overall Score**: 7.5/10

**Strengths**:
- Comprehensive RBAC with 5 roles and fine-grained permission matrix (27+ distinct permissions)
- Token blacklisting with fail-closed behavior on Redis unavailability
- Refresh token rotation on use (old token blacklisted)
- Rate limiting on auth endpoints (IP-based via slowapi + per-email lockout via Redis)
- CSRF double-submit cookie pattern with HMAC-SHA256 session binding + SameSite=Lax
- Dev mode requires DEBUG=true and is blocked in non-development environments (HTTP only)
- MCP API key validation uses DB-backed SHA256 hash comparison with HMAC timing-safe comparison
- MCP API key rate limiting with per-key-id lockout (5 attempts / 5 min)
- IDOR prevention on user profile endpoints
- Engagement membership checks on most engagement-scoped routes
- JWT key rotation support via `jwt_verification_keys` list
- Production startup blocked when default secrets are present

**Areas for Improvement**:
- WebSocket dev mode lacks the app_env guard present in HTTP auth
- Four graph routes missing engagement membership checks (cross-tenant risk)
- MCP rate limiting should use Redis for multi-worker consistency
- Logout should handle Redis failures more explicitly
- Response models should be added to ~55 routes
- WebSocket token-in-URL pattern should be deprecated
- Dev mode auto-auth logging should be WARN level, not DEBUG
