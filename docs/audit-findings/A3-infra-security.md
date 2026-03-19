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
| CORS-001: Wildcard methods/headers | **REMEDIATED** | Explicit method and header lists in main.py (lines 283-285) |
| DOCKER-001: Hardcoded creds in init script | **REMEDIATED** | Init script now uses env vars (`$KMFLOW_DB_PASSWORD`, `$CAMUNDA_DB_PASSWORD`) via shell substitution |
| DOCKER-002: Backend runs as root | **REMEDIATED** | Multi-stage Dockerfile with `appuser` non-root user |
| HEADERS-001: Missing HSTS/CSP | **REMEDIATED** | Full security header suite in `SecurityHeadersMiddleware` |
| CRYPTO-001: Weak SHA-256 KDF | **REMEDIATED** | Replaced with PBKDF2 (600,000 iterations) |
| WORKER-001: Reflected XSS | **REMEDIATED** | `escapeHtml()` now applied to all dynamic values (error, pendingEmail, redirect, email) |
| RATELIMIT-001: Unbounded memory | **REMEDIATED** | Periodic pruning and max-tracked-clients cap added |
| DOCKER-003: OpenAPI exposed unconditionally | **REMEDIATED** | Conditional on `settings.debug` (main.py line 266) |

## Summary (Current State)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
| MEDIUM   | 4     |
| LOW      | 4     |
| **Total**| **9** |

---

## HIGH Findings

### [HIGH] SECRETS-003: Sensitive Config Fields Not Using SecretStr

**File**: `src/core/config.py:42-70`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
postgres_password: str = "kmflow_dev_password"
neo4j_password: str = "neo4j_dev_password"
jwt_secret_key: str = "dev-secret-key-change-in-production"
encryption_key: str = "dev-encryption-key-change-in-production"
watermark_signing_key: str = "dev-watermark-key-change-in-production"
```
Compare with the Databricks token which correctly uses `SecretStr` (line 125):
```python
databricks_token: SecretStr = SecretStr("")
```
**Description**: Five security-critical fields -- database passwords, JWT signing key, encryption key, and watermark signing key -- are stored as plain `str` types in the Settings model. Pydantic's `SecretStr` type prevents these values from appearing in string representations, `repr()` output, JSON serialization, and log messages. The `databricks_token` field already demonstrates the correct pattern within the same file. Without `SecretStr`, calling `settings.model_dump()`, printing settings in debug output, or including settings in error traces will expose these secrets in plaintext. This is elevated from MEDIUM to HIGH because the `Value Error` exception handler in `main.py` (line 460-467) includes `str(exc)` in the response body, and the `reject_default_secrets_in_production` validator raises `ValueError` with the secret field names listed -- while this does not leak the values themselves, the code path demonstrates that Settings objects can surface in exception flows.
**Risk**: Accidental exposure of secrets in application logs, debug output, error traces, or monitoring systems. If a developer or log aggregation system captures the settings object (e.g., `logger.debug("Settings: %s", settings)`), all passwords and keys are written in cleartext.
**Recommendation**: Change `postgres_password`, `neo4j_password`, `jwt_secret_key`, `encryption_key`, and `watermark_signing_key` fields to `SecretStr` type. Update all code that reads these values to call `.get_secret_value()`. This matches the existing pattern used for `databricks_token`.

---

## MEDIUM Findings

### [MEDIUM] DOCKER-004: Source Code Volume Mounts Without Read-Only Flag

**File**: `docker-compose.yml:222-225`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
    volumes:
      - ./src:/app/src
      - ./scripts:/app/scripts
      - ./alembic:/app/alembic
      - ./alembic.ini:/app/alembic.ini
```
The frontend-dev service has the same pattern (lines 294-297):
```yaml
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
      - ./frontend/next.config.js:/app/next.config.js
```
**Description**: The development compose file mounts host source code directories into the backend and frontend-dev containers with default read-write access. The production overlay (`docker-compose.prod.yml:94,116`) correctly sets `volumes: []`, but a container compromise in the development environment could modify source code on the host filesystem. This finding was present in prior audits and remains unresolved.
**Risk**: A compromised development container could inject backdoors into source code that persist across container restarts and could be unknowingly committed to version control.
**Recommendation**: Append `:ro` to all source code volume mounts: `./src:/app/src:ro`. If hot-reload requires write access (e.g., for `__pycache__`), add a separate tmpfs mount for cache directories.

---

### [MEDIUM] CRYPTO-002: PBKDF2 Uses Fixed Application-Level Salt

**File**: `src/core/encryption.py:29-34`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            b"kmflow-fernet-key-derivation-v1",  # Fixed application-level salt
            iterations=600_000,
        )
        return base64.urlsafe_b64encode(derived)
```
**Description**: The PBKDF2 key derivation function uses a fixed, publicly visible salt that is identical for all deployments. While PBKDF2 with 600,000 iterations is a significant improvement over the previous raw SHA-256, the fixed salt means that two deployments using the same encryption key will derive identical Fernet keys. The salt is committed to source code and is therefore not secret.
**Risk**: If an attacker obtains the derived key from one deployment, they can use it to decrypt data in any other deployment that uses the same input secret. The fixed salt also allows precomputed tables specific to this application. However, the 600,000 iterations make brute-force expensive, so this is moderate risk.
**Recommendation**: Derive a per-deployment salt from a deployment-specific identifier (e.g., a random value generated at first deployment and stored alongside the encryption key). Alternatively, accept the fixed salt as a trade-off given that the encryption key should be high-entropy in production (enforced by `reject_default_secrets_in_production`).

---

### [MEDIUM] NETWORK-003: Neo4j and PostgreSQL Use Unencrypted Connections

**File**: `src/core/config.py:48` and `src/core/neo4j.py:29-32`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
# config.py:48
neo4j_uri: str = "bolt://localhost:7687"

# neo4j.py:29-32
driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)
```
And for PostgreSQL (`config.py:211-214`):
```python
self.database_url = (
    f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
    f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
)
```
**Description**: Both the Neo4j connection (`bolt://`) and PostgreSQL connection (`postgresql+asyncpg://`) use unencrypted transport protocols. The encrypted alternatives are `bolt+s://` for Neo4j and `postgresql+asyncpg://...?ssl=require` for PostgreSQL. Within a Docker bridge network on the same host, unencrypted connections are acceptable for development. In production deployments where services may span hosts or networks, credentials are transmitted in plaintext.
**Risk**: Credentials and query data transmitted between the application and databases can be intercepted via network sniffing if any network segment is compromised.
**Recommendation**: For production deployments, enforce TLS on database connections. Use `bolt+s://` for Neo4j and add `?ssl=require` to the PostgreSQL connection string. Override connection URIs in `docker-compose.prod.yml`.

---

### [MEDIUM] NETWORK-004: Production Overlay Missing Overrides for CIB7, MinIO, and Mailpit

**File**: `docker-compose.prod.yml` (absence of CIB7/MinIO/Mailpit overrides)
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
The production overlay sets `ports: []` for postgres (line 12), neo4j (line 37), and redis (line 58), but does not override port mappings for CIB7, MinIO, or Mailpit:
```yaml
# docker-compose.yml:104-105 (CIB7)
    ports:
      - "${CIB7_PORT:-8081}:8080"

# docker-compose.yml:133-135 (MinIO)
    ports:
      - "${MINIO_PORT:-9002}:9000"
      - "${MINIO_CONSOLE_PORT:-9003}:9001"
```
**Description**: The production overlay successfully removes host port mappings for core data services but does not address CIB7 (unauthenticated BPMN engine REST API), MinIO (object storage with console UI), or Mailpit (development email server). CIB7's REST API at `/engine-rest` allows unauthenticated process deployment and task completion. MinIO console on port 9003 provides a web UI accessible with default credentials. Mailpit should not exist in production at all.
**Risk**: In production, exposed CIB7 allows unauthorized workflow manipulation. MinIO console exposure could grant object storage access. Mailpit silently swallows production emails.
**Recommendation**: Add CIB7 and MinIO to the production overlay with `ports: []`. Remove Mailpit from production via Docker Compose profiles. Configure CIB7 basic authentication.

---

## LOW Findings

### [LOW] CONFIG-001: Redis URL Built Without Password When REDIS_URL Not Set

**File**: `src/core/config.py:216-217`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
```
Compare with the database URL builder which includes the password (lines 211-214):
```python
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
```
**Description**: When `REDIS_URL` is not explicitly set, the derived URL omits the password component. The `.env` file does set `REDIS_URL` with a password, and the Docker backend environment also sets it. However, if someone runs the backend with a partial `.env`, the derived URL will omit the password, causing silent authentication failure or connection to an unauthenticated Redis.
**Risk**: Low -- only affects local development with incomplete configuration. The production overlay enforces `REDIS_PASSWORD` via `${REDIS_PASSWORD:?}`.
**Recommendation**: Add a `redis_password` field to Settings and include it in the derived URL: `f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"`.

---

### [LOW] WORKER-002: Descope Project ID Hardcoded in Source Code

**File**: `infrastructure/cloudflare-workers/presentation-auth/src/index.ts:299-300`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```typescript
const DESCOPE_JWKS_URL = 'https://api.descope.com/P39ERvEl6A8ec0DKtrKBvzM4Ue5V/.well-known/jwks.json';
const JWKS = createRemoteJWKSet(new URL(DESCOPE_JWKS_URL));
```
And the issuer check at line 309:
```typescript
      issuer: 'https://api.descope.com/v1/apps/P39ERvEl6A8ec0DKtrKBvzM4Ue5V',
```
**Description**: The Descope project ID is hardcoded in the JWKS URL and issuer validation string rather than derived from the `DESCOPE_PROJECT_ID` environment variable that is already available via `env.DESCOPE_PROJECT_ID`. While Descope project IDs are semi-public, hardcoding them reduces portability and places the ID in committed source.
**Risk**: Low direct risk. Assists reconnaissance and reduces portability across Descope projects.
**Recommendation**: Derive the JWKS URL and issuer from the environment variable. Note: `createRemoteJWKSet` is called at module scope (outside the fetch handler), so the URL must be constructed in a way compatible with module initialization, or lazily initialized on first request.

---

### [LOW] DOCKER-006: AUTH_DEV_MODE Enabled in Docker Compose Backend

**File**: `docker-compose.yml:217`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
      AUTH_DEV_MODE: "true"
      COOKIE_SECURE: "false"
      POSTGRES_SUPERUSER_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}
```
And the dev admin seeding triggered by this flag (`main.py:146-165`):
```python
    if settings.auth_dev_mode:
        # ... seeds admin@kmflow.dev with platform_admin role
        dev_user = User(
            id=uuid.uuid4(),
            email="admin@kmflow.dev",
            name="Dev Admin",
            role="platform_admin",
            is_active=True,
        )
```
**Description**: The development compose file enables `AUTH_DEV_MODE=true` and `COOKIE_SECURE=false`. This is expected for local development and the production overlay correctly sets `APP_ENV: production` and `DEBUG: "false"` (line 79-80), which triggers `reject_default_secrets_in_production` if `auth_dev_mode` is still true. However, the production overlay does not explicitly set `AUTH_DEV_MODE: "false"` or `COOKIE_SECURE: "true"` -- it relies on the config.py defaults (`auth_dev_mode: bool = False`, `cookie_secure: bool = True`).
**Risk**: Low. The defense-in-depth provided by the validator is sound, but explicitly overriding these flags in the production overlay would make the security posture more visible.
**Recommendation**: Add explicit `AUTH_DEV_MODE: "false"` and `COOKIE_SECURE: "true"` to `docker-compose.prod.yml` for defense-in-depth and operational clarity.

---

### [LOW] DOCKER-007: Superuser Password Fallback in Docker Compose

**File**: `docker-compose.yml:12`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}
      KMFLOW_DB_PASSWORD: ${POSTGRES_PASSWORD:-kmflow_dev_password}
```
**Description**: The PostgreSQL container's superuser password uses `${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}` with a weak default. While this is standard for development, the production overlay (`docker-compose.prod.yml:11`) requires `${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}` but this overrides the application user password, not the superuser password. The superuser password is not explicitly overridden in the production overlay, meaning it inherits the dev default unless `POSTGRES_SUPERUSER_PASSWORD` is set in the environment.
**Risk**: Low -- production deployments should use managed database services or set all environment variables. But the asymmetry between enforced and defaulted passwords could lead to oversight.
**Recommendation**: Add `POSTGRES_SUPERUSER_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:?Set POSTGRES_SUPERUSER_PASSWORD}` to the production overlay.

---

## Security Posture Assessment

**Overall Risk Level**: MEDIUM-LOW (improved from MEDIUM in prior audit)

### Improvements Since Prior Audit (2026-02-26)

1. **XSS remediated**: The reflected XSS vulnerability in the Cloudflare Worker login page (previously HIGH) has been fixed. `escapeHtml()` is now applied to all user-controlled values: `error`, `pendingEmail`, `redirect`, and `email`.
2. **Init script hardcoded credentials remediated**: `docker/init-scripts/00-create-databases.sh` now uses `${KMFLOW_DB_PASSWORD:-...}` and `${CAMUNDA_DB_PASSWORD:-...}` environment variables instead of hardcoded SQL passwords.

### Positive Findings

- `.env` files are properly listed in `.gitignore` (line 26)
- `reject_default_secrets_in_production` model validator blocks startup with dev keys in non-development environments (config.py line 221-247)
- CORS configuration uses explicit origin list, specific methods, and named headers (main.py lines 282-286)
- Full security header suite: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy`, `Cache-Control: no-store`, CSP, `Permissions-Policy`, and conditional HSTS (security.py lines 59-72)
- All Docker services have `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]`
- Container resource limits set in both dev and prod compose files
- Redis authentication enforced in both environments
- PBKDF2 with 600,000 iterations for encryption key derivation
- Rate limiting present at two layers: custom `RateLimitMiddleware` (per-IP) and `slowapi` (per-endpoint)
- Rate limiter correctly does NOT trust `X-Forwarded-For` header (security.py lines 118-125)
- RAG retrieval uses parameterized queries via SQLAlchemy `text()` with named params (retrieval.py lines 193-213)
- Cookie security: `HttpOnly`, `Secure` (default True), `SameSite=Lax` for session, `SameSite=Strict` for refresh
- Database cross-access revoked in init script (lines 35-39)
- `auth_dev_mode` defaults to `False` (config.py line 68)
- OpenAPI docs disabled when `debug=False` (main.py line 266-267)
- Generic error handler does not leak internal details to clients (main.py lines 469-476)
- No pickle, eval, or unsafe deserialization patterns found
- No `dangerouslySetInnerHTML` in frontend React components
- MCP API keys stored as hashed values, not plaintext (auth.py line 141: `key_hash`)

### Remaining Risks

1. **SecretStr migration** (HIGH) is the most significant remaining issue -- secrets can leak through logging, serialization, or error traces.
2. **Unencrypted database connections** (MEDIUM) acceptable for single-host Docker but must be addressed before multi-host production.
3. **Fixed PBKDF2 salt** (MEDIUM) is a theoretical weakness mitigated by high iteration count and production secret enforcement.
4. **Production overlay gaps** (MEDIUM) for CIB7, MinIO, and Mailpit port exposure.

### Security Score

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Secrets Management | 7 | 10 | Strong startup validation; SecretStr gap and superuser default remain |
| Container Security | 8 | 10 | Good hardening across all services; dev volume mounts still read-write |
| Network Security | 7 | 10 | Prod overlay good for core services; CIB7/MinIO/Mailpit gaps |
| Authentication | 9 | 10 | JWT rotation, blacklisting, fail-closed, cookie security, rate limiting |
| Encryption | 8 | 10 | PBKDF2 KDF with 600k iterations; fixed salt is a minor issue |
| CORS/Headers | 9 | 10 | Explicit origins, methods, headers; full security header suite |
| Input Validation | 9 | 10 | Parameterized queries; XSS now remediated in CF worker |
| Audit/Logging | 9 | 10 | Comprehensive audit middleware; no sensitive data in responses |
| **Overall** | **8.3** | **10** | Improved from 7.9 (prior audit) due to XSS and init script remediation |
