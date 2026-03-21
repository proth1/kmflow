# A3: Infrastructure Security Audit Findings (2026-03-20 Cycle 7 Re-Audit)

**Auditor**: security-reviewer (A3 Infrastructure Security)
**Date**: 2026-03-20
**Scope**: Docker configuration, secrets management, CORS, encryption, TLS, HSTS, cookie security, network segmentation, Dockerfiles
**Type**: Cycle 7 re-audit following prior audits on 2026-02-20, 2026-02-26, 2026-03-19, and 2026-03-20

## Remediation Status from Prior Audits

| Prior Finding | Status | Notes |
|---|---|---|
| SECRETS-001: Redis no auth | **REMEDIATED** | `--requirepass` in dev compose (line 72); `${REDIS_PASSWORD:?}` enforced in prod overlay (line 66) |
| SECRETS-002: Default secrets accepted in prod | **REMEDIATED** | `reject_default_secrets_in_production` model_validator in config.py (line 238) |
| SECRETS-003: Fields not using SecretStr | **REMEDIATED** | All five fields (`postgres_password`, `neo4j_password`, `jwt_secret_key`, `encryption_key`, `watermark_signing_key`) now use `SecretStr` (config.py lines 42, 50, 64, 70, 71) |
| CORS-001: Wildcard methods/headers | **REMEDIATED** | Explicit method and header lists in main.py (lines 277-278) |
| DOCKER-001: Hardcoded creds in init script | **REMEDIATED** | Init script uses env vars (`$KMFLOW_DB_PASSWORD`, `$CAMUNDA_DB_PASSWORD`) via `00-create-databases.sh` lines 11-12 |
| DOCKER-002: Backend runs as root | **REMEDIATED** | Multi-stage Dockerfile with `appuser` non-root user (Dockerfile.backend lines 33, 48) |
| DOCKER-003: OpenAPI exposed unconditionally | **REMEDIATED** | Conditional on `settings.debug` (main.py lines 490-491) |
| DOCKER-004: Backend volume mounts not read-only | **REMEDIATED** | Backend mounts now have `:ro` flag (docker-compose.yml lines 225-228) |
| DOCKER-005: Frontend-dev mounts not read-only | **REMEDIATED** | Frontend-dev mounts now have `:ro` flag (docker-compose.yml lines 297-299) |
| DOCKER-008: Frontend runs as root | **REMEDIATED** | Frontend Dockerfile `runner` stage now creates `nextjs` user (UID 1001) and uses `USER nextjs` (frontend/Dockerfile lines 30-34) |
| HEADERS-001: Missing HSTS/CSP | **REMEDIATED** | Full security header suite in `SecurityHeadersMiddleware` (security.py lines 60-74) |
| CRYPTO-001: Weak SHA-256 KDF | **REMEDIATED** | Replaced with PBKDF2 (600,000 iterations) in encryption.py lines 51-56 |
| WORKER-001: Reflected XSS | **REMEDIATED** | `escapeHtml()` applied to all dynamic values |
| WORKER-002: Hardcoded Descope project ID | **REMEDIATED** | JWKS URL and issuer now derived from `env.DESCOPE_PROJECT_ID` |
| RATELIMIT-001: Unbounded memory | **REMEDIATED** | Periodic pruning and max-tracked-clients cap added |
| DOCKER-006: AUTH_DEV_MODE/COOKIE_SECURE not in prod overlay | **REMEDIATED** | Explicitly set in docker-compose.prod.yml lines 92-94 (`AUTH_DEV_MODE: "false"`, `COOKIE_SECURE: "true"`, `ENABLE_HSTS: "true"`) |

## Summary (Current State)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
| MEDIUM   | 3     |
| LOW      | 2     |
| **Total**| **6** |

---

## HIGH Findings

### [HIGH] NETWORK-001: CIB7 REST API Lacks HTTP Authentication in Production

**File**: `docker-compose.prod.yml:146-156` and `docker/cib7/bpm-platform.xml`
**Agent**: security-reviewer (A3)
**Evidence**:
```yaml
# docker-compose.prod.yml:146-156 (CIB7 prod overrides)
  cib7:
    environment:
      CAMUNDA_USER: ${CAMUNDA_USER:?Set CAMUNDA_USER}
      CAMUNDA_PASSWORD: ${CAMUNDA_PASSWORD:?Set CAMUNDA_PASSWORD}
    ports: []  # No host port exposure
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    networks:
      - backend-net
```
```python
# src/api/main.py:193-198 (CIB7 client connects without auth)
    cib7_url = os.environ.get("CIB7_URL", "http://localhost:8080/engine-rest")
    camunda_client = CamundaClient(
        cib7_url,
        auth_user=settings.camunda_user,
        auth_password=settings.camunda_password.get_secret_value() if settings.camunda_password else None,
    )
```
```yaml
# docker-compose.yml:210-211 (dev compose sets empty CIB7 auth)
      CAMUNDA_USER: ${CAMUNDA_USER:-}
      CAMUNDA_PASSWORD: ${CAMUNDA_PASSWORD:-}
```
**Description**: The prod overlay requires `CAMUNDA_USER` and `CAMUNDA_PASSWORD` env vars (lines 148-149), and `bpm-platform.xml` has `authorizationEnabled=true` (line 17). However, CIB7's REST API authentication depends on the CIB7 runtime's own filter chain configuration, which is not visible in the mounted config. The backend `CamundaClient` passes credentials if configured (main.py lines 196-198), but the CIB7 container image `cibseven/cibseven:run-2.1.0` may not enforce HTTP basic auth on `/engine-rest` by default. In the dev compose, `CAMUNDA_USER` and `CAMUNDA_PASSWORD` default to empty strings (lines 210-211), leaving the REST API unauthenticated. If an attacker reaches `backend-net` in production, the CIB7 REST API at `/engine-rest` allows deploying arbitrary BPMN processes, completing tasks, and querying process data.
**Risk**: Process manipulation and data exfiltration for any attacker with network access to CIB7. Mitigated by `ports: []` in prod (no host exposure) and network isolation to `backend-net`, but not fully mitigated against lateral movement from a compromised backend container.
**Recommendation**: (1) Verify CIB7 image enforces HTTP basic auth on `/engine-rest` when `CAMUNDA_USER`/`CAMUNDA_PASSWORD` are set. (2) If not natively supported, deploy an nginx sidecar or add a reverse proxy with basic auth in front of CIB7. (3) Document the CIB7 auth model in a security decision record.

---

## MEDIUM Findings

### [MEDIUM] CRYPTO-002: PBKDF2 Salt Derived Deterministically from Secret

**File**: `src/core/encryption.py:50`
**Agent**: security-reviewer (A3)
**Evidence**:
```python
        salt = _LEGACY_FIXED_SALT if legacy_salt else hashlib.sha256(secret.encode()).digest()[:16]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            salt,
            iterations=600_000,
        )
```
**Description**: The PBKDF2 key derivation uses a salt deterministically computed from the secret itself (`sha256(secret)[:16]`). Standard practice recommends a random salt stored alongside the derived key. Two deployments with the same encryption key produce identical derived keys. The code comments (lines 36-44) acknowledge this as a known limitation -- changing the salt derivation would break decryption of existing ciphertext. The 600,000 iteration count and production secret enforcement substantially mitigate brute-force risk.
**Risk**: Moderate. If an attacker obtains the derived Fernet key from one deployment, it is valid in any other deployment using the same input secret.
**Recommendation**: For new deployments, generate a random salt and store it as `ENCRYPTION_SALT` env var. Existing deployments should document this as an accepted risk in a security decision record.

---

### [MEDIUM] NETWORK-002: Default Dev Database Connections Use Unencrypted Transport

**File**: `src/core/config.py:48` (Neo4j) and `src/core/config.py:221-225` (PostgreSQL)
**Agent**: security-reviewer (A3)
**Evidence**:
```python
# config.py:48 -- default Neo4j URI uses unencrypted bolt://
neo4j_uri: str = "bolt://localhost:7687"

# config.py:221-225 -- derived PostgreSQL URL has no SSL parameter
self.database_url = (
    f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
    f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
)
```
Production overlay (`docker-compose.prod.yml:96-98`) correctly uses encrypted connections:
```yaml
DATABASE_URL: "postgresql+asyncpg://...?ssl=require"
NEO4J_URI: "bolt+s://neo4j:7687"
REDIS_URL: "rediss://..."
```
**Description**: Default config uses unencrypted `bolt://` for Neo4j and `postgresql+asyncpg://` without SSL for PostgreSQL. Production overlay correctly overrides with encrypted variants. Within a single-host Docker bridge network, unencrypted connections are acceptable for development. The risk is for multi-host deployments where defaults could be accidentally used.
**Risk**: Credentials and query data traverse the network in plaintext if production doesn't override defaults. The prod overlay mitigates this for the standard deployment path.
**Recommendation**: Consider adding a validation check in `reject_default_secrets_in_production` that flags unencrypted database URIs when `APP_ENV != development`.

---

### [MEDIUM] CONFIG-002: Redis URL Fallback Omits Password

**File**: `src/core/config.py:227`
**Agent**: security-reviewer (A3)
**Evidence**:
```python
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
```
Compare with the PostgreSQL URL builder which includes credentials (lines 221-225):
```python
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
```
**Description**: When `REDIS_URL` is not explicitly set, the derived fallback URL omits the password. The `.env` file and Docker compose backend environment both set `REDIS_URL` with a password, and the production overlay requires `${REDIS_PASSWORD:?}`. However, partial configuration (setting `REDIS_HOST`/`REDIS_PORT` without `REDIS_URL`) silently connects without authentication.
**Risk**: A developer with incomplete `.env` configuration could inadvertently bypass Redis authentication. Production is mitigated by explicit `REDIS_URL` in the overlay.
**Recommendation**: Include `redis_password` in the derived URL builder: `f"redis://:{self.redis_password.get_secret_value()}@{self.redis_host}:{self.redis_port}/0"`. This matches the PostgreSQL pattern.

---

## LOW Findings

### [LOW] DOCKER-007: PostgreSQL Superuser Password Variable Naming Asymmetry

**File**: `docker-compose.yml:12` and `docker-compose.prod.yml:17-19`
**Agent**: security-reviewer (A3)
**Evidence**:
```yaml
# docker-compose.yml:12 (uses POSTGRES_SUPERUSER_PASSWORD shell var)
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}

# docker-compose.prod.yml:17-19 (uses POSTGRES_PASSWORD shell var)
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
```
**Description**: The dev compose uses `POSTGRES_SUPERUSER_PASSWORD` shell variable while the prod overlay uses `POSTGRES_PASSWORD` shell variable, both mapping to the container's `POSTGRES_PASSWORD` env var. The prod overlay correctly requires a non-empty value via `:?` syntax.
**Risk**: Low -- variable naming asymmetry could cause operator confusion during deployment, but production enforcement is sound.
**Recommendation**: Align variable naming between dev and prod compose files for clarity.

---

### [LOW] SEED-001: Hardcoded Superuser Credentials in seed_demo.py

**File**: `scripts/seed_demo.py` and `docker/backend-entrypoint.sh:11`
**Agent**: security-reviewer (A3)
**Evidence**:
```shell
# backend-entrypoint.sh:11
export SEED_DB_URL="postgresql+asyncpg://postgres:${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-kmflow}"
```
```shell
# backend-entrypoint.sh:19 (credentials cleared after seeding)
unset SEED_DB_URL SEED_NEO4J_URI SEED_NEO4J_USER SEED_NEO4J_PASSWORD POSTGRES_SUPERUSER_PASSWORD
```
**Description**: The backend entrypoint and seed script contain hardcoded fallback database URLs with the superuser password `postgres_dev`. This is used only for local development seeding when `AUTH_DEV_MODE=true`, and the entrypoint correctly clears superuser credentials after seeding (line 19). The seed script is not invoked in production (`AUTH_DEV_MODE` is `false`).
**Risk**: Low -- the hardcoded password matches the dev default in docker-compose.yml. Not accessible in production.
**Recommendation**: Consider replacing the hardcoded fallback with a required env var check that errors instead of defaulting.

---

## Security Posture Assessment

**Overall Risk Level**: MEDIUM-LOW

### Changes Since Prior Cycle (2026-03-20 earlier cycle)

1. **DOCKER-008 (Frontend runs as root) is now REMEDIATED**: The frontend Dockerfile `runner` stage creates a `nextjs` user (UID 1001, GID 1001) and switches to it via `USER nextjs` (frontend/Dockerfile lines 30-34). This was the prior cycle's main HIGH finding.
2. **DOCKER-005 (Frontend-dev mounts) is now REMEDIATED**: All three frontend-dev volume mounts now include `:ro` flag (docker-compose.yml lines 297-299).
3. **DOCKER-006 (AUTH_DEV_MODE/COOKIE_SECURE) is now REMEDIATED**: Both are explicitly set in the prod overlay (docker-compose.prod.yml lines 92-94).
4. **Finding count reduced**: From 9 (0C/2H/3M/4L) to 6 (0C/1H/3M/2L).

### Positive Findings (Verified)

**Secrets Management**
- `.env` file is in `.gitignore` (line 26) and NOT tracked by git
- `ENCRYPTION_KEY` and `WATERMARK_SIGNING_KEY` are NOT present in `.env`
- `reject_default_secrets_in_production` model validator blocks startup with dev keys outside development (config.py lines 238-271)
- `validate_dev_mode_requires_debug` validator prevents accidental auth bypass (config.py lines 231-234)
- All credential fields use `SecretStr` (config.py lines 42, 50, 64, 70, 71)

**Container Security**
- All services use `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]` in docker-compose.yml
- Container resource limits (memory, CPU) set in both dev and prod compose
- Backend Dockerfile: non-root `appuser` user, pinned Python 3.12.11-slim, multi-stage build, `--require-hashes` for pip install
- Frontend Dockerfile: non-root `nextjs` user (UID 1001), pinned node:20.19-alpine, multi-stage build
- Backend volumes mounted read-only (`:ro`) in dev compose
- Frontend-dev volumes mounted read-only (`:ro`) in dev compose
- Production overlay: `volumes: []` override removes all bind mounts

**Network Security**
- Production overlay: three-tier network segmentation (`frontend-net`, `backend-net`, `data-net`)
- Production overlay: `ports: []` for all data services (postgres, neo4j, redis, cib7, minio)
- Production overlay: TLS enforced on all connections (`?ssl=require`, `bolt+s://`, `rediss://`)
- Mailpit disabled in production via `profiles: [never]`

**Authentication & Authorization**
- JWT key rotation support via `jwt_secret_keys` comma-separated list (config.py line 65)
- Token blacklisting via Redis with fail-closed behavior (auth.py lines 152-163)
- Rate limiting at two layers: custom `RateLimitMiddleware` (per-IP, Redis-backed Lua script) and `slowapi` (per-endpoint)
- Rate limiter correctly does NOT trust `X-Forwarded-For` header (security.py lines 122-128)
- CSRF double-submit cookie pattern with HMAC-SHA256 binding (csrf.py + auth.py)
- Auth dev mode guarded: requires `DEBUG=true` (config.py line 233), refuses to run in non-dev/test envs (auth.py lines 388-394)

**Cookie Security**
- Access token: `HttpOnly=true`, `Secure` defaults true, `SameSite=Lax`, `path=/`
- Refresh token: `HttpOnly=true`, `Secure` defaults true, `SameSite=Strict`, `path=/api/v1/auth/refresh`
- CSRF cookie: `HttpOnly=false` (by design -- JS readable), `Secure`, `SameSite=Lax`
- Production overlay sets `COOKIE_SECURE: "true"` explicitly

**Security Headers** (security.py lines 60-74)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Cache-Control: no-store`
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (conditional on `enable_hsts`)

**CORS** (main.py lines 273-278)
- Explicit origin list (no wildcards)
- Explicit HTTP methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
- Named allowed headers: Authorization, Content-Type, X-Request-ID, Accept, X-CSRF-Token
- `allow_credentials=True` paired with specific origins (not `*`)

**Encryption**
- PBKDF2 with 600,000 iterations for key derivation (encryption.py lines 51-56)
- Key rotation support with fallback to previous key (encryption.py lines 69-76, 108-114)
- Legacy salt fallback for backward compatibility (encryption.py lines 97-106)
- `re_encrypt_value()` utility for key rotation migration (encryption.py lines 129-137)

**Database Security**
- Cross-database access revoked: `REVOKE ALL ON DATABASE kmflow FROM camunda, PUBLIC` (init script lines 35-36)
- BYPASSRLS documented and intentional for platform_admin RLS bypass (init script lines 17-18)
- Backend entrypoint clears superuser credentials after seeding (backend-entrypoint.sh line 19)
- OpenAPI/ReDoc docs disabled when `debug=False` (main.py lines 490-491)
- Generic error handler does not leak internal details (main.py lines 473-479)

### Remaining Risks

1. **CIB7 REST API auth gap** (HIGH) -- The prod overlay requires `CAMUNDA_USER`/`CAMUNDA_PASSWORD` env vars, but it is unclear whether the CIB7 runtime enforces HTTP basic auth on `/engine-rest`. Network isolation to `backend-net` and `ports: []` provide partial mitigation.
2. **Deterministic PBKDF2 salt** (MEDIUM) -- Accepted trade-off documented in code comments and `docs/audit-lessons-learned.md`.
3. **Unencrypted default database URIs** (MEDIUM) -- Prod overlay correctly overrides with TLS. Risk is for non-standard deployment paths.
4. **Redis URL fallback without password** (MEDIUM) -- Could cause silent unauthenticated connections with incomplete config.

### Security Score

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Secrets Management | 9 | 10 | SecretStr on all credential fields; startup validation; minor Redis URL gap |
| Container Security | 9 | 10 | Both backend and frontend now run as non-root; all services hardened; prod overlay removes bind mounts |
| Network Security | 8.5 | 10 | Three-tier segmentation in prod; TLS enforced; CIB7 REST auth gap remains |
| Authentication | 9 | 10 | JWT rotation, blacklisting, fail-closed, cookie security, CSRF, dual-layer rate limiting |
| Encryption | 8 | 10 | PBKDF2 KDF with 600K iterations; deterministic salt is documented trade-off |
| CORS/Headers | 10 | 10 | Explicit origins, methods, headers; full security header suite including conditional HSTS and CSP |
| Cookie Security | 10 | 10 | HttpOnly, Secure (default true), SameSite Lax/Strict, path-restricted refresh, CSRF double-submit |
| Audit/Logging | 9 | 10 | Comprehensive audit middleware; no sensitive data in responses; request ID tracking |
| **Overall** | **8.8** | **10** | Improved from 8.4 due to frontend non-root user fix and frontend-dev mount fixes |
