# A1: Authorization & Authentication Audit

**Agent**: A1 (AuthZ Auditor)
**Date**: 2026-03-19
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication
**Files Reviewed**: 80+ route files, core auth/permissions/config/security modules, MCP auth

---

## Executive Summary

The KMFlow authorization layer is **substantially sound** with several well-implemented controls: JWT token blacklisting (fail-closed on Redis unavailability), proper token type separation (access vs. refresh), bcrypt password hashing, HMAC-safe API key comparison, cookie-based auth with HttpOnly/Secure/SameSite attributes, and a production startup validator that blocks default secrets. However, the audit identified **5 findings** across severity levels that require attention, most notably unauthenticated route files and a missing production guard for the watermark signing key.

**Security Score**: 7.5 / 10

---

## Findings

### [HIGH] MISSING_AUTH: Conflict Resolution Routes Entirely Unauthenticated
**File**: `src/api/routes/conflicts.py:99-364`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get(
    "/engagements/{engagement_id}/conflicts",
    response_model=ConflictListResponse,
    summary="List conflicts for an engagement",
)
async def list_conflicts(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
```
**Description**: All 5 endpoints in `conflicts.py` (list, resolve, assign, escalate, escalation-check) lack any authentication or authorization dependency. No `get_current_user`, `require_permission`, `require_role`, or `require_engagement_access` is imported or used. Any unauthenticated caller can read, resolve, assign, and escalate conflict objects across all engagements.
**Risk**: An unauthenticated attacker can enumerate engagement conflicts (information disclosure), resolve conflicts without authorization (data integrity violation), and trigger mass escalations (denial of service to engagement leads).
**Recommendation**: Add `Depends(require_engagement_access)` to the engagement-scoped endpoints and `Depends(require_permission("governance:write"))` to mutation endpoints (resolve, assign, escalate). The escalation-check endpoint should require `require_role(UserRole.PLATFORM_ADMIN)` since it operates across all engagements.

---

### [HIGH] MISSING_AUTHZ: MCP Tool Handlers Bypass Engagement-Level Authorization
**File**: `src/mcp/server.py:155-329`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def _tool_get_engagement(session_factory: Any, args: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID
    from sqlalchemy import func, select
    from src.core.models import Engagement, EvidenceItem
    eid = UUID(args["engagement_id"])
    async with session_factory() as session:
        result = await session.execute(select(Engagement).where(Engagement.id == eid))
```
**Description**: While MCP endpoints properly authenticate the API key via `_verify_mcp_auth` (DB lookup + HMAC hash comparison -- this is correctly implemented), the authenticated client info (`client` dict containing `user_id`) is never passed to the tool handler functions. All 8 tool handlers (`_tool_get_engagement`, `_tool_list_evidence`, `_tool_get_process_model`, `_tool_get_gaps`, `_tool_get_monitoring_status`, `_tool_get_deviations`, `_tool_search_patterns`, `_tool_run_simulation`) accept any `engagement_id` without verifying the API key's user has membership in that engagement.
**Risk**: Any valid MCP API key holder can access data from any engagement, violating multi-tenant isolation. A compromised or malicious MCP client can enumerate all engagement data platform-wide.
**Recommendation**: Pass the `client["user_id"]` into each tool handler and verify engagement membership using `get_accessible_engagement_ids()` from `src/core/security.py` before querying data. Alternatively, add an engagement-scoping wrapper that filters queries based on the authenticated user's membership.

---

### [MEDIUM] DEFAULT_SECRET: Watermark Signing Key Not Validated in Production Startup Guard
**File**: `src/core/config.py:70,220-247`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
    watermark_signing_key: str = "dev-watermark-key-change-in-production"

    @model_validator(mode="after")
    def reject_default_secrets_in_production(self) -> Settings:
        """Block startup when default development secrets are present outside development."""
        if self.app_env == "development":
            return self
        has_default_jwt = "dev-secret-key" in self.jwt_secret_key
        has_default_enc = "dev-encryption-key" in self.encryption_key
```
**Description**: The production startup validator (`reject_default_secrets_in_production`) checks `jwt_secret_key`, `encryption_key`, `postgres_password`, `neo4j_password`, `auth_dev_mode`, and `debug` -- but does NOT check `watermark_signing_key`. The default value `"dev-watermark-key-change-in-production"` would be silently accepted in staging/production. The watermark signing key is used for document watermarking (ABAC obligation enforcement), meaning forged watermarks would be possible with the known default key.
**Risk**: An attacker who knows the default watermark key (it is in the public source code) could forge or strip document watermarks in non-development environments, undermining audit trail integrity.
**Recommendation**: Add `has_default_watermark = "dev-watermark-key" in self.watermark_signing_key` to the production validator alongside the existing checks.

---

### [MEDIUM] DEFAULT_SECRET: Hardcoded Development Credentials in Config Defaults
**File**: `src/core/config.py:42-70`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
    postgres_password: str = "kmflow_dev_password"
    neo4j_password: str = "neo4j_dev_password"
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    encryption_key: str = "dev-encryption-key-change-in-production"
    watermark_signing_key: str = "dev-watermark-key-change-in-production"
```
**Description**: Multiple development credentials are hardcoded as default values in the Settings class. While the `reject_default_secrets_in_production` validator mitigates this for non-development environments, the defaults are visible in source control and could be used if `APP_ENV` is misconfigured or left as `"development"` in a non-dev deployment.
**Risk**: If a deployment accidentally runs with `APP_ENV=development` (the default), all default credentials are silently accepted. The validator only fires for non-development environments. A misconfigured staging or production deployment would use known, public credentials.
**Recommendation**: Consider requiring all secret values to be explicitly set via environment variables (no defaults) and fail startup if they are missing, regardless of `APP_ENV`. Alternatively, add a warning log at startup when running in development mode with default secrets.

---

### [LOW] MISSING_AUTH: Deployment Capabilities Endpoint Unauthenticated
**File**: `src/api/routes/deployment.py:19-26`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """Return deployment capabilities.

    Used by the frontend to determine which features are available
    in this deployment (cloud vs. on-prem vs. air-gapped).
    """
    return get_deployment_capabilities()
```
**Description**: The deployment capabilities endpoint is unauthenticated. While this endpoint returns feature flags rather than sensitive data, it exposes deployment topology information (cloud vs. on-prem vs. air-gapped, which features are enabled) to unauthenticated callers.
**Risk**: Information disclosure of deployment architecture to unauthenticated users. Low severity because the data is feature flags, not credentials or PII, but it aids reconnaissance.
**Recommendation**: Add `Depends(get_current_user)` to require authentication, or accept the risk if the frontend needs this before login.

---

## Positive Findings (Controls Working Correctly)

The following security controls were reviewed and found to be properly implemented:

1. **MCP API Key Authentication** (`src/mcp/auth.py:59-102`): Despite the pre-identified concern, `validate_api_key()` performs a proper DB lookup by `key_id`, hashes the incoming raw key with SHA-256, and uses `hmac.compare_digest()` for timing-safe comparison. This is correctly implemented.

2. **Token Blacklisting** (`src/core/auth.py:151-162`): Redis-backed blacklist with fail-closed behavior (returns `True` / "blacklisted" when Redis is unavailable). This is a secure default.

3. **Token Type Enforcement** (`src/core/auth.py:331-336`): Access token validation rejects refresh tokens and vice versa, preventing token confusion attacks.

4. **JWT Key Rotation** (`src/core/config.py:180-191`): Supports comma-separated verification keys via `jwt_verification_keys` property, enabling zero-downtime key rotation.

5. **Cookie Security** (`src/core/auth.py:195-275`): HttpOnly, Secure, SameSite=Lax (access) / Strict (refresh), path-restricted refresh cookie. Well-implemented browser session security.

6. **Production Secret Validation** (`src/core/config.py:220-247`): Startup validator blocks non-development environments from running with default secrets. Covers JWT, encryption, Postgres, Neo4j, auth_dev_mode, and debug flag.

7. **Rate Limiting on Auth Endpoints** (`src/api/routes/auth.py:116-117,172`): Login limited to 5/min, refresh to 10/min via slowapi.

8. **Engagement Access Control** (`src/core/permissions.py:200-239`): `require_engagement_access` is actively used across 44 route files with proper DB-backed membership checks.

9. **RBAC Permission Matrix** (`src/core/permissions.py:25-101`): Well-defined 5-tier role hierarchy with granular permissions. Platform admin wildcard (`*`) is appropriate for the highest privilege level.

10. **Health Endpoint** (`src/api/routes/health.py`): Intentionally unauthenticated -- this is correct for health checks (load balancers, orchestrators need unauthenticated access).

---

## Security Checklist Results

| Check | Status | Details |
|-------|--------|---------|
| No hardcoded production secrets | PASS (with caveat) | Defaults exist but blocked by production validator |
| JWT expiration enforced | PASS | 30min access, 7-day refresh |
| Token blacklisting | PASS | Redis-backed, fail-closed |
| RBAC on all routes | FAIL | `conflicts.py` has 5 unprotected endpoints |
| Engagement isolation | PARTIAL | HTTP routes good, MCP tools bypass isolation |
| Auth dev mode guarded | PASS | Disabled by default, blocked in production |
| Cookie security | PASS | HttpOnly, Secure, SameSite, path-restricted |
| Rate limiting on auth | PASS | 5/min login, 10/min refresh |
| Key rotation support | PASS | Multi-key verification |
| Production startup validation | PARTIAL | Missing watermark key check |

---

## Risk Assessment

| Severity | Count | Action Required |
|----------|-------|-----------------|
| CRITICAL | 0 | -- |
| HIGH | 2 | Must fix before production deployment |
| MEDIUM | 2 | Should fix; document rationale if deferred |
| LOW | 1 | Informational; fix at convenience |
