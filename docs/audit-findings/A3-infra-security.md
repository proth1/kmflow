# A3: Infrastructure Security Audit Findings (2026-03-19 Re-Audit)

**Auditor**: A3 (Infrastructure Security Auditor)
**Date**: 2026-03-19
**Scope**: Docker configuration, Cloudflare worker, Redis/Neo4j authentication, secrets management, CORS, encryption
**Type**: Re-audit following prior audits on 2026-02-20 and 2026-02-26

## Remediation Status from Prior Audits

| Prior Finding | Status | Notes |
|---|---|---|
| SECRETS-001: Redis no auth | **REMEDIATED** | `--requirepass` in dev compose (line 72); `${REDIS_PASSWORD:?}` enforced in prod overlay (line 57) |
| SECRETS-002: Default secrets accepted in prod | **REMEDIATED** | `reject_default_secrets_in_production` model_validator in config.py (line 221) |
| SECRETS-003: Fields not using SecretStr | **REMEDIATED** | All five fields (`postgres_password`, `neo4j_password`, `jwt_secret_key`, `encryption_key`, `watermark_signing_key`) now use `SecretStr` (config.py lines 42, 50, 63, 69, 70) |
| CORS-001: Wildcard methods/headers | **REMEDIATED** | Explicit method and header lists in main.py (lines 284-285) |
| DOCKER-001: Hardcoded creds in init script | **REMEDIATED** | Init script uses env vars (`$KMFLOW_DB_PASSWORD`, `$CAMUNDA_DB_PASSWORD`) |
| DOCKER-002: Backend runs as root | **REMEDIATED** | Multi-stage Dockerfile with `appuser` non-root user |
| DOCKER-004: Backend volume mounts not read-only | **REMEDIATED** | Backend mounts now have `:ro` flag (docker-compose.yml lines 223-226) |
| HEADERS-001: Missing HSTS/CSP | **REMEDIATED** | Full security header suite in `SecurityHeadersMiddleware` |
| CRYPTO-001: Weak SHA-256 KDF | **REMEDIATED** | Replaced with PBKDF2 (600,000 iterations) |
| WORKER-001: Reflected XSS | **REMEDIATED** | `escapeHtml()` applied to all dynamic values |
| WORKER-002: Hardcoded Descope project ID | **REMEDIATED** | JWKS URL and issuer now derived from `env.DESCOPE_PROJECT_ID` (index.ts lines 300-302, 314) |
| RATELIMIT-001: Unbounded memory | **REMEDIATED** | Periodic pruning and max-tracked-clients cap added |
| DOCKER-003: OpenAPI exposed unconditionally | **REMEDIATED** | Conditional on `settings.debug` (main.py line 266) |

## Summary (Current State)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
| MEDIUM   | 3     |
| LOW      | 3     |
| **Total**| **7** |

---

## HIGH Findings

### [HIGH] NETWORK-001: Production Overlay Missing Overrides for CIB7 and MinIO

**File**: `docker-compose.prod.yml` (absence of CIB7/MinIO overrides)
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:104-105 (CIB7 -- exposed with no auth override)
    ports:
      - "${CIB7_PORT:-8081}:8080"

# docker-compose.yml:133-135 (MinIO -- exposed with default creds)
    ports:
      - "${MINIO_PORT:-9002}:9000"
      - "${MINIO_CONSOLE_PORT:-9003}:9001"
```
The production overlay (`docker-compose.prod.yml`) sets `ports: []` for postgres (line 12), neo4j (line 37), and redis (line 58), but has **no entries** for `cib7`, `minio`, or `mailpit`. These services inherit the dev compose host port mappings in production.
**Description**: CIB7's REST API at `/engine-rest` allows unauthenticated process deployment and task completion. The `bpm-platform.xml` enables `authorizationEnabled=true` for the engine but does not configure HTTP-level authentication on the REST API endpoint. MinIO console on port 9003 provides a web UI accessible with default credentials (`kmflow-dev` / `kmflow-dev-secret`). Mailpit should not exist in production at all. The production overlay successfully hardens core data services but leaves these three services exposed.
**Risk**: An attacker with network access to the production host could deploy arbitrary BPMN processes, complete tasks, or access object storage contents. CIB7 unauthenticated access is the most severe -- it allows full workflow manipulation.
**Recommendation**: Add CIB7, MinIO, and Mailpit to `docker-compose.prod.yml` with `ports: []`. Use Docker Compose profiles to exclude Mailpit from production entirely. Configure CIB7 basic authentication or restrict network access. Override MinIO credentials in the production overlay using `${MINIO_ROOT_USER:?}` / `${MINIO_ROOT_PASSWORD:?}`.

---

## MEDIUM Findings

### [MEDIUM] CRYPTO-002: PBKDF2 Salt Derived Deterministically from Secret

**File**: `src/core/encryption.py:37-43`
**Agent**: A3 (Infrastructure Security Auditor)
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
**Description**: The PBKDF2 key derivation uses a salt that is deterministically computed from the secret itself (`sha256(secret)[:16]`). This is an improvement over the legacy fixed salt (`_LEGACY_FIXED_SALT = b"kmflow-fernet-key-derivation-v1"`), but it means the salt is not independent of the password -- two deployments with the same encryption key will produce identical derived keys. Standard PBKDF2 practice recommends a random salt stored alongside the derived key. However, the 600,000 iteration count substantially raises the cost of brute-force attacks.
**Risk**: If an attacker obtains the derived Fernet key from one deployment, it is valid in any other deployment using the same input secret. The deterministic salt also permits targeted precomputation (though 600K iterations makes this expensive). The practical risk is moderate given that production encryption keys should be high-entropy (enforced by `reject_default_secrets_in_production`).
**Recommendation**: Generate a random salt at first deployment and store it as a separate configuration value (e.g., `ENCRYPTION_SALT`). Alternatively, accept the current design as a conscious trade-off, documented in a security decision record.

---

### [MEDIUM] NETWORK-002: Neo4j and PostgreSQL Use Unencrypted Connections

**File**: `src/core/config.py:48` and `src/core/neo4j.py:29-32`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
# config.py:48
neo4j_uri: str = "bolt://localhost:7687"

# neo4j.py:29-32
driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
)
```
And for PostgreSQL (`config.py:212-214`):
```python
self.database_url = (
    f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
    f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
)
```
**Description**: Both Neo4j (`bolt://`) and PostgreSQL (`postgresql+asyncpg://`) connections use unencrypted transport. The encrypted alternatives are `bolt+s://` for Neo4j and `?ssl=require` for PostgreSQL. Within a single-host Docker bridge network, unencrypted connections are acceptable. In multi-host production deployments, credentials and query data traverse the network in plaintext.
**Risk**: Credentials and query data can be intercepted via network sniffing if any segment between application and database is compromised.
**Recommendation**: For production, enforce TLS: use `bolt+s://` for Neo4j and append `?ssl=require` to the PostgreSQL connection string. Override URIs in `docker-compose.prod.yml` environment variables.

---

### [MEDIUM] CONFIG-002: Redis URL Fallback Omits Password

**File**: `src/core/config.py:216-217`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
```
Compare with the PostgreSQL URL builder which includes credentials (lines 212-214):
```python
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
```
**Description**: When `REDIS_URL` is not explicitly set in the environment, the derived fallback URL omits the password. The `.env` file and Docker compose backend environment both set `REDIS_URL` with a password, and the production overlay requires `${REDIS_PASSWORD:?}`. However, a partial configuration (setting `REDIS_HOST`/`REDIS_PORT` without `REDIS_URL` or a `redis_password` field) would silently connect without authentication.
**Risk**: A developer running the backend locally with incomplete `.env` configuration could inadvertently connect to Redis without authentication. In production, this is mitigated by the explicit `REDIS_URL` in the overlay.
**Recommendation**: Add a `redis_password` field to Settings (as `SecretStr`) and include it in the derived URL: `f"redis://:{self.redis_password.get_secret_value()}@{self.redis_host}:{self.redis_port}/0"`. This matches the PostgreSQL pattern.

---

## LOW Findings

### [LOW] DOCKER-005: Frontend-Dev Volume Mounts Lack Read-Only Flag

**File**: `docker-compose.yml:294-297`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
  frontend-dev:
    profiles: ["dev"]
    # ...
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
      - ./frontend/next.config.js:/app/next.config.js
```
The backend service correctly uses `:ro` (lines 223-226):
```yaml
    volumes:
      - ./src:/app/src:ro
      - ./scripts:/app/scripts:ro
```
**Description**: The `frontend-dev` service mounts host directories with default read-write access. While this service is gated behind the `dev` profile and is only used for local development with hot reload, a compromised container could modify host source files. The backend service has already been updated with `:ro` flags; the frontend-dev service should follow the same pattern.
**Risk**: Low -- only affects local development and requires container compromise. Hot reload may require write access for `.next` cache, which can be handled with a separate tmpfs mount.
**Recommendation**: Add `:ro` to source mounts and use a tmpfs volume for Next.js cache: `- ./frontend/src:/app/src:ro`. If hot reload breaks, add `tmpfs: /app/.next` to the service.

---

### [LOW] DOCKER-006: AUTH_DEV_MODE Not Explicitly Disabled in Production Overlay

**File**: `docker-compose.prod.yml:78-80` and `docker-compose.yml:217`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:217 (dev compose enables auth bypass)
      AUTH_DEV_MODE: "true"
      COOKIE_SECURE: "false"

# docker-compose.prod.yml:78-80 (prod overlay does NOT override these)
  backend:
    environment:
      APP_ENV: production
      DEBUG: "false"
      LOG_LEVEL: WARNING
```
**Description**: The production overlay sets `APP_ENV: production` and `DEBUG: "false"` but does not explicitly set `AUTH_DEV_MODE: "false"` or `COOKIE_SECURE: "true"`. The config.py defaults (`auth_dev_mode: bool = False`, `cookie_secure: bool = True`) provide the correct values, and the `reject_default_secrets_in_production` validator will fail startup if `auth_dev_mode` is true in non-development mode. However, defense-in-depth recommends explicit overrides in the production configuration.
**Risk**: Low -- the validator catch is reliable. Explicit overrides improve operational clarity and make the security posture visible during configuration review.
**Recommendation**: Add `AUTH_DEV_MODE: "false"` and `COOKIE_SECURE: "true"` to the backend environment in `docker-compose.prod.yml`.

---

### [LOW] DOCKER-007: PostgreSQL Superuser Password Not Enforced in Production Overlay

**File**: `docker-compose.yml:12` and `docker-compose.prod.yml:9-11`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:12 (superuser password with weak default)
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}

# docker-compose.prod.yml:9-11 (enforces app password, not superuser)
      POSTGRES_DB: ${POSTGRES_DB:?Set POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER:?Set POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
```
**Description**: The production overlay requires `POSTGRES_PASSWORD` (which maps to the superuser password in the container's `POSTGRES_PASSWORD` env var), but the variable name collision between the dev compose (`POSTGRES_SUPERUSER_PASSWORD`) and the prod overlay (`POSTGRES_PASSWORD`) creates ambiguity. In `docker-compose.yml`, the `POSTGRES_PASSWORD` env var is set from `${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}`, while in prod it is set from `${POSTGRES_PASSWORD:?}`. The prod overlay correctly requires a non-empty value, but operators must understand which shell variable maps to which container variable.
**Risk**: Low -- production overlay does enforce a non-empty superuser password. The variable naming asymmetry could cause confusion during deployment.
**Recommendation**: Align variable naming between dev and prod compose files. Use `POSTGRES_SUPERUSER_PASSWORD` consistently with `${POSTGRES_SUPERUSER_PASSWORD:?Set POSTGRES_SUPERUSER_PASSWORD}` in the production overlay.

---

## Security Posture Assessment

**Overall Risk Level**: MEDIUM-LOW

### Improvements Since Prior Audit (2026-02-26)

1. **SecretStr migration complete**: All five credential fields (`postgres_password`, `neo4j_password`, `jwt_secret_key`, `encryption_key`, `watermark_signing_key`) now use `SecretStr` type, preventing accidental exposure through logging or serialization.
2. **Backend volume mounts now read-only**: `docker-compose.yml` lines 223-226 use `:ro` flag.
3. **Worker Descope project ID dynamic**: JWKS URL and issuer derived from `env.DESCOPE_PROJECT_ID` at request time (index.ts lines 300-302, 314).
4. **XSS remediated**: `escapeHtml()` applied to all user-controlled values in the Cloudflare Worker login page.
5. **Init script credentials remediated**: `docker/init-scripts/00-create-databases.sh` uses environment variables.

### Positive Findings

- `.env` file is properly listed in `.gitignore` (line 26) and NOT tracked in git
- `reject_default_secrets_in_production` model validator blocks startup with dev keys outside development (config.py lines 221-250)
- CORS uses explicit origin list, specific HTTP methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`), and named headers (`Authorization`, `Content-Type`, `X-Request-ID`, `Accept`) (main.py lines 282-286)
- Full security header suite: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`, CSP, `Permissions-Policy`, conditional HSTS (security.py lines 59-73)
- All Docker services use `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]`
- Container resource limits (memory, CPU) set in both dev and prod compose files
- Redis authentication enforced via `--requirepass` in both environments
- PBKDF2 with 600,000 iterations for encryption key derivation
- Rate limiting at two layers: custom `RateLimitMiddleware` (per-IP, Redis-backed Lua script) and `slowapi` (per-endpoint decorators)
- Rate limiter correctly does NOT trust `X-Forwarded-For` header (security.py lines 120-127)
- Cookie security: `HttpOnly`, `Secure` (default True), `SameSite=Lax` for session, `SameSite=Strict` for refresh
- Database cross-access properly revoked in init script (lines 35-39)
- OpenAPI docs disabled when `debug=False` (main.py lines 266-267)
- Generic error handler does not leak internal details to clients (main.py lines 469-476)
- Cloudflare Worker cookies set with `HttpOnly; Secure; SameSite=Lax` (index.ts lines 279, 282, 397, 457, 460)
- Worker uses `jose` v6 with proper issuer validation via `jwtVerify` (index.ts lines 313-315)
- Email authorization checked server-side before OTP delivery and after verification (index.ts lines 370, 447)
- No pickle, eval, or unsafe deserialization patterns found
- No `dangerouslySetInnerHTML` in frontend React components
- CIB7 engine has `authorizationEnabled=true` (bpm-platform.xml line 17)
- PostgreSQL database isolation: `REVOKE ALL` between kmflow and camunda databases (init script lines 35-39)

### Remaining Risks

1. **Production overlay gaps** (HIGH) for CIB7 and MinIO port exposure is the most significant remaining issue -- unauthenticated CIB7 REST API in production would allow workflow manipulation.
2. **Unencrypted database connections** (MEDIUM) acceptable for single-host Docker but must be addressed for multi-host production.
3. **Deterministic PBKDF2 salt** (MEDIUM) is a theoretical weakness mitigated by high iteration count and production secret enforcement.
4. **Redis URL fallback without password** (MEDIUM) could cause silent unauthenticated connections with partial configuration.

### Security Score

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Secrets Management | 9 | 10 | SecretStr on all credential fields; startup validation; minor Redis URL gap |
| Container Security | 8 | 10 | Hardened services; prod overlay gaps for CIB7/MinIO/Mailpit |
| Network Security | 7 | 10 | Prod overlay good for core services; unencrypted DB connections; CIB7/MinIO gaps |
| Authentication | 9 | 10 | JWT rotation, blacklisting, fail-closed, cookie security, rate limiting |
| Encryption | 8 | 10 | PBKDF2 KDF with 600K iterations; deterministic salt is minor concern |
| CORS/Headers | 10 | 10 | Explicit origins, methods, headers; full security header suite including conditional HSTS |
| Input Validation | 9 | 10 | Parameterized queries; XSS remediated in CF worker |
| Audit/Logging | 9 | 10 | Comprehensive audit middleware; no sensitive data in responses |
| **Overall** | **8.6** | **10** | Improved from 8.3 (prior audit) due to SecretStr migration, read-only mounts, and dynamic Descope config |
