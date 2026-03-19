# A1: Authorization & Authentication Audit

**Agent**: A1 (AuthZ Auditor)
**Date**: 2026-03-19
**Scope**: JWT authentication, RBAC enforcement, multi-tenancy isolation, MCP authentication
**Files Reviewed**: 78 route files, core auth/permissions/config/security modules, MCP auth

---

## Executive Summary

The KMFlow authorization layer is **well-implemented** with strong fundamentals: JWT token blacklisting with fail-closed Redis behavior, proper token type separation, bcrypt password hashing, HMAC-safe API key comparison, HttpOnly/Secure/SameSite cookie attributes, production startup secret validation (covering JWT, encryption, Postgres, Neo4j, watermark, auth_dev_mode, and debug), and comprehensive engagement membership checks (`require_engagement_access`) across 44+ route files. MCP tool handlers correctly verify engagement membership per-tool.

However, the audit identified **5 findings** across severity levels. The most significant issue is a set of POV and evidence routes that check permission-level authorization (e.g., `pov:read`) but skip engagement-scoped membership checks when accessed by `model_id` or `evidence_id` rather than `engagement_id`, enabling cross-tenant data access for any authenticated user with the correct role permissions.

**Security Score**: 8.0 / 10

---

## Findings

### [HIGH] IDOR: POV Model-ID Routes Skip Engagement Membership Check
**File**: `src/api/routes/pov.py:445-469`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/{model_id}", response_model=ProcessModelResponse)
async def get_process_model(
    model_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pov:read")),
) -> dict[str, Any]:
    result = await session.execute(select(ProcessModel).where(ProcessModel.id == model_uuid))
    model = result.scalar_one_or_none()
    return _model_to_response(model)
```
**Description**: Six POV endpoints that accept `model_id` as a path parameter (`get_process_model`, `get_process_elements`, `get_evidence_map`, `get_evidence_gaps`, `get_contradictions`, `get_bpmn_xml`) check only `require_permission("pov:read")` but do not call `_check_engagement_member()`. The POV module defines this helper and uses it on engagement-scoped routes (e.g., `/engagement/{engagement_id}/versions`), but model-ID-based routes skip it. Any authenticated user with `pov:read` (which includes `process_analyst`, `evidence_reviewer` via `engagement:read`, and `client_viewer`) can access process models from engagements they are not a member of by guessing or enumerating model UUIDs.
**Risk**: Cross-tenant data leakage. A `process_analyst` on Engagement A can read process models, BPMN XML, evidence maps, gaps, and contradictions from Engagement B by supplying the model UUID.
**Recommendation**: After fetching the model, call `await _check_engagement_member(session, user, model.engagement_id)` before returning data. This matches the pattern already used in `/engagement/{engagement_id}/latest-model` (line 703).

---

### [HIGH] IDOR: Evidence Detail and Mutation Routes Skip Engagement Membership Check
**File**: `src/api/routes/evidence.py:309-358,408-448,495-519`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id))
    evidence = result.scalar_one_or_none()
```
**Description**: Three evidence endpoints that look up by `evidence_id` (`get_evidence`, `update_validation_status`, `get_fragments`) check `require_permission` but do not verify engagement membership. The `catalog_evidence` endpoint correctly uses `Depends(require_engagement_access)`, but the ID-based routes skip this. Additionally, `list_evidence` accepts an optional `engagement_id` filter but does not verify membership for the provided engagement, allowing any authenticated user to enumerate all evidence across engagements by omitting the filter.
**Risk**: Cross-tenant data access and data integrity violation. An authenticated user with `evidence:read` can read evidence details and fragments from any engagement. A user with `evidence:update` can modify validation status on evidence they should not have access to.
**Recommendation**: After fetching the evidence item, call `await verify_engagement_member(session, user, evidence.engagement_id)` from `src/core/permissions.py` before returning or modifying data. For `list_evidence`, add engagement membership filtering via `get_accessible_engagement_ids()`.

---

### [MEDIUM] AUTHZ_BYPASS: Dev Mode Auto-Authenticates as Platform Admin Without Logging
**File**: `src/core/auth.py:311-322`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
if token is None:
    # Dev mode: auto-authenticate as the first platform_admin user
    if settings.auth_dev_mode:
        session_factory = request.app.state.db_session_factory
        async with session_factory() as session:
            result = await session.execute(
                select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)
            )
            dev_user = result.scalar_one_or_none()
        if dev_user is not None:
            logger.debug("Auth dev mode: auto-authenticated as %s", dev_user.email)
            return dev_user
```
**Description**: When `auth_dev_mode` is enabled and no token is provided, the system auto-authenticates as the first active `platform_admin` user. This grants full `*` permissions (wildcard) and bypasses engagement membership checks. The authentication event is logged at `DEBUG` level only, which most production logging configs would suppress. While `auth_dev_mode` defaults to `False` and the production validator blocks it, the `app_env` check uses string comparison (`"development"`) and the `auth_dev_mode` flag is independent -- it could be set to `True` while `app_env` is set to a non-standard value like `"local"` or `"testing"` that would not trigger the production guard.
**Risk**: If `auth_dev_mode` is accidentally enabled in a non-development environment (e.g., `APP_ENV=testing`), all unauthenticated requests get full platform admin access. The `DEBUG`-level logging means this would likely go unnoticed in standard log configs.
**Recommendation**: (1) Log dev mode auto-authentication at `WARNING` level, not `DEBUG`. (2) Consider tying `auth_dev_mode` directly to `app_env == "development"` rather than allowing it as an independent flag. (3) Add an explicit deny-list: if `app_env` is in `{"staging", "production", "prod"}`, hard-reject `auth_dev_mode=True` regardless of other settings.

---

### [MEDIUM] DEFAULT_CREDENTIALS: Hardcoded Default Credentials in Config with Env-Dependent Guard
**File**: `src/core/config.py:42-69`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
postgres_password: SecretStr = SecretStr("kmflow_dev_password")
neo4j_password: SecretStr = SecretStr("neo4j_dev_password")
jwt_secret_key: SecretStr = SecretStr("dev-secret-key-change-in-production")
encryption_key: SecretStr = SecretStr("dev-encryption-key-change-in-production")
watermark_signing_key: SecretStr = SecretStr("dev-watermark-key-change-in-production")
```
**Description**: Five sensitive credentials have hardcoded default values in source code. The `reject_default_secrets_in_production` validator blocks these in non-development environments, but the guard depends entirely on `app_env != "development"`. The `app_env` field itself defaults to `"development"` (line 33), meaning a deployment that fails to set `APP_ENV` will silently accept all default secrets. The credentials are visible in the public repository.
**Risk**: A deployment that omits or misconfigures `APP_ENV` runs with known, public credentials for all databases and cryptographic operations. The defense-in-depth principle suggests secrets should never have defaults.
**Recommendation**: Remove default values for all `SecretStr` fields and make them required (Pydantic will raise `ValidationError` if unset). Alternatively, use a sentinel like `SecretStr("")` and add a startup check that rejects empty secrets in all environments.

---

### [LOW] HARDCODED_PASSWORD: Default Password Parameter in Neo4j Validation Utility
**File**: `src/semantic/ontology/validate.py:95`
**Agent**: A1 (AuthZ Auditor)
**Evidence**:
```python
async def validate_neo4j(uri: str, user: str = "neo4j", password: str = "password") -> list[str]:
    """Check that a live Neo4j database conforms to the ontology."""
```
**Description**: The `validate_neo4j` utility function has a hardcoded default password parameter `"password"`. While this is a development/validation utility and not an API endpoint, it establishes a pattern where the default Neo4j password `"password"` could be accidentally used in non-development contexts if the function is called without explicit credentials.
**Risk**: Low -- this is a utility function, not an API endpoint. However, it could mask a misconfiguration where the actual Neo4j password is not passed, resulting in authentication failures or accidental use of default credentials.
**Recommendation**: Remove the default value for `password` to force explicit credential passing: `password: str` instead of `password: str = "password"`.

---

## Positive Findings (Controls Working Correctly)

The following security controls were reviewed and found to be properly implemented:

1. **MCP API Key Authentication** (`src/mcp/auth.py:59-102`): `validate_api_key()` performs a proper DB lookup by `key_id`, hashes the incoming raw key with SHA-256, and uses `hmac.compare_digest()` for timing-safe comparison. This is correctly implemented.

2. **MCP Engagement Membership Checks** (`src/mcp/server.py:157-174`): All 8 MCP tool handlers verify engagement membership by querying `EngagementMember` before returning data. The `user_id` from the authenticated API key is correctly passed through `_execute_tool` to each handler.

3. **Token Blacklisting** (`src/core/auth.py:151-162`): Redis-backed blacklist with fail-closed behavior (returns `True` / "blacklisted" when Redis is unavailable). This is a secure default.

4. **Token Type Enforcement** (`src/core/auth.py:331-336`): Access token validation rejects refresh tokens and vice versa, preventing token confusion attacks.

5. **JWT Key Rotation** (`src/core/config.py:180-191`): Supports comma-separated verification keys via `jwt_verification_keys` property, enabling zero-downtime key rotation.

6. **Cookie Security** (`src/core/auth.py:195-275`): HttpOnly, Secure, SameSite=Lax (access) / Strict (refresh), path-restricted refresh cookie to `/api/v1/auth/refresh`. Well-implemented browser session security.

7. **Production Secret Validation** (`src/core/config.py:220-250`): Startup validator blocks non-development environments from running with default secrets. Covers JWT, encryption, Postgres, Neo4j, watermark, auth_dev_mode, and debug flag.

8. **Rate Limiting on Auth Endpoints** (`src/api/routes/auth.py`): Login limited to 5/min, refresh to 10/min via slowapi.

9. **Engagement Access Control** (`src/core/permissions.py:200-241`): `require_engagement_access` is actively used across 44+ route files with proper DB-backed membership checks and platform admin bypass.

10. **RBAC Permission Matrix** (`src/core/permissions.py:27-103`): Well-defined 5-tier role hierarchy (platform_admin, engagement_lead, process_analyst, evidence_reviewer, client_viewer) with granular permissions. Platform admin wildcard (`*`) is appropriate for the highest privilege level.

11. **Conflict Resolution Routes** (`src/api/routes/conflicts.py:100-108`): Properly secured with `require_engagement_access` on read endpoints and `require_permission("governance:write")` on mutation endpoints.

12. **Health Endpoint** (`src/api/routes/health.py`): Intentionally unauthenticated -- correct for load balancer and orchestrator health probes.

13. **Deployment Capabilities** (`src/api/routes/deployment.py`): Unauthenticated but returns only feature flags (LLM availability, data residency mode), not sensitive data. Acceptable for frontend pre-auth feature detection.

---

## Security Checklist Results

| Check | Status | Details |
|-------|--------|---------|
| No hardcoded production secrets | PASS (with caveat) | Defaults exist but blocked by production validator |
| JWT expiration enforced | PASS | 30min access, 7-day refresh |
| Token blacklisting | PASS | Redis-backed, fail-closed |
| RBAC on all routes | PASS | All 78 route files have auth dependencies |
| Engagement isolation (HTTP) | PARTIAL | Engagement-ID routes good; model-ID/evidence-ID routes skip check |
| Engagement isolation (MCP) | PASS | All 8 tool handlers verify membership |
| Auth dev mode guarded | PASS (with caveat) | Disabled by default, blocked in production; bypassed by non-standard env names |
| Cookie security | PASS | HttpOnly, Secure, SameSite, path-restricted |
| Rate limiting on auth | PASS | 5/min login, 10/min refresh |
| Key rotation support | PASS | Multi-key verification |
| Production startup validation | PASS | Covers all 5 secret keys + auth_dev_mode + debug |

---

## Risk Assessment

| Severity | Count | Action Required |
|----------|-------|-----------------|
| CRITICAL | 0 | -- |
| HIGH | 2 | Must fix before production deployment |
| MEDIUM | 2 | Should fix; document rationale if deferred |
| LOW | 1 | Informational; fix at convenience |
