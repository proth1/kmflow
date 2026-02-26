# A3: Infrastructure Security Audit Findings (Re-Audit)

**Auditor**: A3 (Infrastructure Security Auditor)
**Date**: 2026-02-26
**Scope**: Docker configuration, Cloudflare worker, Redis/Neo4j authentication, secrets management, CORS, encryption
**Type**: Re-audit after Phase 0-2 remediation

## Remediation Status from Original Audit (2026-02-20)

| Original Finding | Status | Notes |
|---|---|---|
| SECRETS-001: Redis no auth | **REMEDIATED** | `--requirepass` added to dev compose; `${REDIS_PASSWORD:?}` enforced in prod overlay |
| SECRETS-002: Default secrets accepted in prod | **REMEDIATED** | `reject_default_secrets_in_production` model_validator added to config.py |
| CORS-001: Wildcard methods/headers | **REMEDIATED** | Explicit method and header lists now in main.py |
| DOCKER-001: Hardcoded Camunda/MinIO creds | **PARTIALLY REMEDIATED** | Camunda/MinIO now use `${VAR:-default}` pattern in dev compose, but Postgres root still hardcoded |
| DOCKER-002: Backend runs as root | **REMEDIATED** | Multi-stage Dockerfile with `appuser` non-root user |
| HEADERS-001: Missing HSTS/CSP | **REMEDIATED** | HSTS (non-debug only), CSP, and Permissions-Policy headers added |
| CRYPTO-001: Weak SHA-256 KDF | **REMEDIATED** | Replaced with PBKDF2 (600,000 iterations) |
| WORKER-001: Reflected XSS | **NOT REMEDIATED** | Error parameter still rendered unescaped |
| RATELIMIT-001: Unbounded memory | **REMEDIATED** | Periodic pruning and max-tracked-clients cap added |
| DOCKER-003: OpenAPI exposed unconditionally | **REMEDIATED** | Conditional on `settings.debug` |
| DOCKER-004: Source code mounts without :ro | **NOT REMEDIATED** | Still read-write in dev compose |
| DOCKER-005: No container security options | **REMEDIATED** | `no-new-privileges` and `cap_drop: ALL` added to all services |
| NETWORK-001: CIB7 no auth | **NOT REMEDIATED** | Still unauthenticated |
| NETWORK-002: All ports mapped to host | **PARTIALLY REMEDIATED** | Prod overlay sets `ports: []` for postgres, neo4j, redis; CIB7/MinIO/Mailpit still exposed |

## Summary (Current State)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 2     |
| MEDIUM   | 4     |
| LOW      | 4     |
| **Total**| **10**|

---

## HIGH Findings

### [HIGH] DOCKER-001: Hardcoded Credentials in Docker Init Script and Compose Defaults

**File**: `docker/init-scripts/00-create-databases.sql:6-7`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```sql
-- Create users with dedicated passwords
CREATE USER kmflow WITH PASSWORD 'kmflow_dev_password';
CREATE USER camunda WITH PASSWORD 'camunda_dev';
```
**Description**: The PostgreSQL initialization script contains hardcoded plaintext passwords for both the `kmflow` and `camunda` database users. This script is mounted into the container via `docker-compose.yml:16` (`./docker/init-scripts:/docker-entrypoint-initdb.d`). Additionally, the top-level `docker-compose.yml:12` still hardcodes the PostgreSQL superuser password as `POSTGRES_PASSWORD: postgres_dev` rather than using environment variable substitution. The production overlay (`docker-compose.prod.yml:19`) points to a different init script path (`./scripts/init-db.sql:ro`), but the dev init script with hardcoded credentials is committed to version control.
**Risk**: Anyone with repository read access knows valid database credentials. If the dev compose is used outside a strictly local context (e.g., a staging environment), these credentials provide immediate database access. The init script runs only on first container startup, but the credentials persist in the database.
**Recommendation**: Replace hardcoded passwords in `00-create-databases.sql` with environment variable references using psql `\set` or shell variable expansion in the entrypoint. Use `${POSTGRES_PASSWORD:-postgres_dev}` substitution pattern in `docker-compose.yml:12` as already done for Neo4j and Redis. Create a separate production init script that reads credentials from environment variables.

---

### [HIGH] WORKER-001: Reflected XSS in Cloudflare Worker Login Page (Unresolved)

**File**: `infrastructure/cloudflare-workers/presentation-auth/src/index.ts:628`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```typescript
${error ? `<div class="error">${error}</div>` : ''}
```
And the source of the `error` variable at line 469:
```typescript
const error = url.searchParams.get('error') || '';
```
And the `pendingEmail` interpolation at line 647:
```typescript
<span class="email">${pendingEmail}</span>
```
**Description**: This finding was identified in the original audit and remains unresolved. The `error` parameter is read directly from the URL query string and interpolated into HTML without any escaping. An attacker can craft a malicious URL such as `https://kmflow.agentic-innovations.com/auth/login?error=<img src=x onerror=alert(document.cookie)>` to execute arbitrary JavaScript. The `pendingEmail` value (line 647) originates from the `PENDING_EMAIL` cookie which is set server-side via `encodeURIComponent`, but the `email` parameter in `renderUnauthorizedPage` (line 188) is also rendered without escaping: `<span class="email">${email}</span>`.
**Risk**: Reflected XSS on the authentication page allows an attacker to execute JavaScript in the user's browser session. This could be used to intercept OTP codes as they are entered, redirect users to phishing pages, or exfiltrate session data. Although session cookies are HttpOnly (preventing direct cookie theft via `document.cookie`), the attacker can still manipulate the DOM to capture form inputs including the OTP code.
**Recommendation**: Create an `escapeHtml()` utility function and apply it to all dynamically interpolated values:
```typescript
function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
}
```
Apply to: `error` (line 628), `pendingEmail` (line 647), `email` (line 188), and `redirect` in form hidden inputs.

---

## MEDIUM Findings

### [MEDIUM] SECRETS-003: Sensitive Config Fields Not Using SecretStr

**File**: `src/core/config.py:42-69`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
postgres_password: str = "kmflow_dev_password"
neo4j_password: str = "neo4j_dev_password"
jwt_secret_key: str = "dev-secret-key-change-in-production"
encryption_key: str = "dev-encryption-key-change-in-production"
```
Compare with the Databricks token which correctly uses `SecretStr` (line 124):
```python
databricks_token: SecretStr = SecretStr("")
```
**Description**: Database passwords, the JWT signing key, and the encryption key are stored as plain `str` types in the Settings model. Pydantic's `SecretStr` type prevents these values from appearing in string representations, `repr()` output, JSON serialization, and log messages. The `databricks_token` field already demonstrates the correct pattern. Without `SecretStr`, calling `settings.dict()`, printing settings in debug output, or including settings in error traces will expose these secrets in plaintext.
**Risk**: Accidental exposure of secrets in application logs, debug output, or error traces. If a developer logs the settings object (e.g., `logger.debug("Settings: %s", settings)`), all passwords and keys are written to the log in cleartext.
**Recommendation**: Change `postgres_password`, `neo4j_password`, `jwt_secret_key`, and `encryption_key` fields to `SecretStr` type. Update all code that reads these values to call `.get_secret_value()`. This matches the existing pattern used for `databricks_token`.

---

### [MEDIUM] DOCKER-004: Source Code Volume Mounts Without Read-Only Flag (Unresolved)

**File**: `docker-compose.yml:208-210`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
    volumes:
      - ./src:/app/src
      - ./alembic:/app/alembic
      - ./alembic.ini:/app/alembic.ini
```
**Description**: This finding was identified in the original audit and remains unresolved. The development compose file mounts host source code directories into the backend container with default read-write access. While the production overlay (`docker-compose.prod.yml:94`) correctly sets `volumes: []`, a container compromise in the development environment could modify source code on the host filesystem. The frontend container has the same pattern (lines 249-250): `./frontend/src:/app/src` and `./frontend/public:/app/public`.
**Risk**: A compromised development container could inject backdoors into source code that persist across container restarts and could be unknowingly committed to version control.
**Recommendation**: Append `:ro` to all source code volume mounts: `./src:/app/src:ro`. If hot-reload requires write access (e.g., for `__pycache__`), add a separate tmpfs mount for cache directories.

---

### [MEDIUM] CRYPTO-002: PBKDF2 Uses Fixed Application-Level Salt

**File**: `src/core/encryption.py:29-34`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
        derived = hashlib.pbkdf2_hmac(
            'sha256',
            secret.encode(),
            b'kmflow-fernet-key-derivation-v1',  # Fixed application-level salt
            iterations=600_000,
        )
        return base64.urlsafe_b64encode(derived)
```
**Description**: The PBKDF2 key derivation function uses a fixed, publicly visible salt that is identical for all deployments. While PBKDF2 with 600,000 iterations is a significant improvement over the previous raw SHA-256 (which was remediated from the original audit), the fixed salt means that two deployments using the same encryption key will derive identical Fernet keys. The salt is committed to source code and is therefore not secret.
**Risk**: If an attacker obtains the derived key from one deployment, they can use it to decrypt data in any other deployment that uses the same input secret. The fixed salt also means that precomputed tables specific to this application could be built once and reused. However, the 600,000 iterations of PBKDF2 make brute-force expensive regardless, so this is a moderate risk.
**Recommendation**: Consider deriving a per-deployment salt from a combination of a deployment-specific identifier (e.g., a random value generated at first deployment and stored alongside the encryption key). Alternatively, accept the fixed salt as a reasonable trade-off given that the encryption key itself should be high-entropy in production (enforced by the `reject_default_secrets_in_production` validator).

---

### [MEDIUM] NETWORK-003: Neo4j and PostgreSQL Use Unencrypted Connections

**File**: `src/core/config.py:48` and `src/core/neo4j.py:28-31`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
# config.py:48
neo4j_uri: str = "bolt://localhost:7687"

# neo4j.py:28-31
driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)
```
And for PostgreSQL (`config.py:196`):
```python
self.database_url = (
    f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
    f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
)
```
**Description**: Both the Neo4j connection (`bolt://`) and PostgreSQL connection (`postgresql+asyncpg://`) use unencrypted transport protocols. The encrypted alternatives are `bolt+s://` (or `bolt+ssc://` for self-signed) for Neo4j and `postgresql+asyncpg://...?ssl=require` for PostgreSQL. Within a Docker bridge network on the same host, unencrypted connections are acceptable for development. In production deployments where services may span hosts or networks, credentials are transmitted in plaintext.
**Risk**: Credentials and query data transmitted between the application and databases can be intercepted via network sniffing if any network segment is compromised. In a container environment on the same host, the Docker bridge network provides some isolation, but in multi-host or cloud deployments, this is a real risk.
**Recommendation**: For production deployments, enforce TLS on database connections. Use `bolt+s://` for Neo4j and add `?ssl=require` (or `sslmode=require`) to the PostgreSQL connection string. Configure the database containers with TLS certificates. In `docker-compose.prod.yml`, override the connection URIs to use encrypted variants.

---

## LOW Findings

### [LOW] NETWORK-001: CIB7 Camunda Engine Has No Authentication (Unresolved)

**File**: `docker-compose.yml:93` and CamundaClient usage
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```yaml
    ports:
      - "${CIB7_PORT:-8081}:8080"
```
And from `src/api/main.py:114-115`:
```python
cib7_url = os.environ.get("CIB7_URL", "http://localhost:8080/engine-rest")
camunda_client = CamundaClient(cib7_url)
```
**Description**: This finding was identified in the original audit and remains unresolved. The CIB7 Camunda engine REST API is accessible without any authentication. The port is mapped to the host in the development compose file. The `CamundaClient` makes HTTP requests with no authentication headers. While the production overlay does not explicitly close this port (it is not listed in `docker-compose.prod.yml`), the `security_opt` and `cap_drop` hardening from the dev compose apply.
**Risk**: Any process on the host (development) or Docker network can interact with the BPMN engine, deploying processes, starting workflow instances, or completing tasks. This is lower risk because CIB7 is primarily used internally by the KMFlow backend.
**Recommendation**: Add CIB7 to the production overlay with `ports: []`. Configure CIB7 basic authentication or restrict access via network policies. Pass credentials from the KMFlow backend.

---

### [LOW] NETWORK-002: MinIO and Mailpit Ports Still Exposed in Production Overlay

**File**: `docker-compose.prod.yml` (absence of MinIO/Mailpit overrides)
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
The production overlay (`docker-compose.prod.yml`) sets `ports: []` for postgres, neo4j, and redis, but does not override port mappings for:
```yaml
# docker-compose.yml:121-123
  minio:
    ports:
      - "${MINIO_PORT:-9002}:9000"
      - "${MINIO_CONSOLE_PORT:-9003}:9001"
```
```yaml
# docker-compose.yml:165-167
  mailpit:
    ports:
      - "${SMTP_PORT:-1026}:1025"
      - "${MAILPIT_UI_PORT:-8026}:8025"
```
**Description**: The production overlay successfully removes host port mappings for PostgreSQL, Neo4j, and Redis (remediation from the original audit). However, MinIO (object storage with root credentials) and Mailpit (development email server) still have ports mapped to the host. MinIO exposes both the API (port 9000) and the console UI (port 9001). Mailpit should not be present in production at all.
**Risk**: MinIO console access on port 9003 provides a web UI that could be accessed with the default credentials if they are not overridden. Mailpit is a development tool that should not exist in production -- it captures all outbound email, meaning production emails would be silently swallowed rather than delivered.
**Recommendation**: Add MinIO to the production overlay with `ports: []`. Remove or exclude the Mailpit service entirely from production composition (either via the overlay or by using Docker Compose profiles). Configure a real SMTP server for production email delivery.

---

### [LOW] WORKER-002: Descope Project ID Exposed in Source Code

**File**: `infrastructure/cloudflare-workers/presentation-auth/wrangler.toml:13`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```toml
[vars]
DESCOPE_PROJECT_ID = "P39ERvEl6A8ec0DKtrKBvzM4Ue5V"
PAGES_URL = "https://kmflow-presentation.pages.dev"
WORKER_DOMAIN = "https://kmflow.agentic-innovations.com"
```
And hardcoded in the JWKS URL at `src/index.ts:290`:
```typescript
const DESCOPE_JWKS_URL = 'https://api.descope.com/P39ERvEl6A8ec0DKtrKBvzM4Ue5V/.well-known/jwks.json';
```
**Description**: The Descope project ID is hardcoded in both the `wrangler.toml` configuration and directly in the TypeScript source code. While Descope project IDs are designed to be semi-public (they appear in JWKS URLs and are needed for client-side SDKs), embedding them in committed source code makes it trivial for anyone to identify the authentication provider and project, enabling targeted attacks against the Descope account (e.g., brute-forcing OTPs if rate limiting is not configured in Descope, or social engineering Descope support).
**Risk**: Low direct risk since Descope project IDs are not secret credentials. However, unnecessary information disclosure assists reconnaissance. The JWKS URL at line 290 should derive from the environment variable rather than being hardcoded.
**Recommendation**: Derive the JWKS URL from the `DESCOPE_PROJECT_ID` environment variable rather than hardcoding it: `const DESCOPE_JWKS_URL = \`https://api.descope.com/${env.DESCOPE_PROJECT_ID}/.well-known/jwks.json\``. This also makes the worker more portable across Descope projects.

---

### [LOW] CONFIG-001: Redis URL Built Without Password When REDIS_URL Not Set

**File**: `src/core/config.py:199-200`
**Agent**: A3 (Infrastructure Security Auditor)
**Evidence**:
```python
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"
```
**Description**: When `REDIS_URL` is not explicitly set as an environment variable, the `build_derived_urls` model validator constructs the Redis URL without a password component. The dev `.env` file does set `REDIS_URL=redis://:dev_redis_password@localhost:6380/0`, and the Docker backend environment also sets it. However, if someone runs the backend outside Docker without the `.env` file (or with a partial `.env`), the derived URL will omit the password, causing a silent authentication failure or connection to an unauthenticated Redis instance.
**Risk**: Low -- this only affects local development scenarios where `.env` is incomplete. The production overlay enforces `REDIS_PASSWORD` via `${REDIS_PASSWORD:?}`. However, the inconsistency between the `redis_url` construction (no password) and the `database_url` construction (includes password) is a design asymmetry that could cause confusion.
**Recommendation**: Include the Redis password in the derived URL when `redis_password` is available. Add a `redis_password` field to the Settings model, or detect the `REDIS_PASSWORD` environment variable during URL construction: `f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"` when a password is set.

---

## Security Posture Assessment

**Overall Risk Level**: MEDIUM (improved from HIGH)

### Improvements Since Original Audit

Significant remediation work has been completed since the 2026-02-20 audit:

1. **Redis authentication**: Now enforced in both dev (`--requirepass` with env var default) and prod (`${REDIS_PASSWORD:?}` required).
2. **Secret validation at startup**: The `reject_default_secrets_in_production` model validator blocks startup with default dev keys outside the development environment.
3. **CORS tightened**: Explicit method and header lists replace wildcards.
4. **Container hardening**: All services now have `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]` in the dev compose. Production overlay adds resource limits and log rotation.
5. **Dockerfile security**: Multi-stage build, non-root `appuser`, no compiler in runtime image, `--reload` removed from CMD.
6. **Security headers**: HSTS (conditional on non-debug), CSP, Permissions-Policy, and Cache-Control headers now present.
7. **Encryption KDF**: Upgraded from single-pass SHA-256 to PBKDF2 with 600,000 iterations.
8. **Rate limiter**: Periodic pruning with `_PRUNE_INTERVAL` and `_MAX_TRACKED_CLIENTS` cap prevents unbounded memory growth. `X-Forwarded-For` is correctly not trusted.
9. **OpenAPI docs**: Conditionally disabled when `settings.debug` is False.

### Remaining Risks

1. **Reflected XSS on the authentication worker** (HIGH) is the most significant remaining issue. This is a live production vulnerability on `kmflow.agentic-innovations.com`.
2. **Hardcoded credentials in the PostgreSQL init script** (HIGH) are committed to version control.
3. **Unencrypted database connections** (MEDIUM) are acceptable for single-host Docker deployments but must be addressed before multi-host production.
4. **Config fields should use SecretStr** (MEDIUM) to prevent accidental logging of secrets.

### Positive Findings

- `.env` files are properly listed in `.gitignore` (line 26)
- `.dockerignore` does not exist, but the multi-stage Dockerfile minimizes what is copied
- Token blacklisting uses Redis with fail-closed behavior (returns True when Redis is unavailable)
- HttpOnly cookies with `SameSite=Strict` for refresh tokens and `SameSite=Lax` for access tokens
- Cookie `Secure` flag defaults to `True` in config (line 78), only disabled in local dev `.env`
- Refresh cookie is path-restricted to `/api/v1/auth/refresh`
- Auth rate limiting on login (5/minute) and refresh (10/minute) via slowapi
- Audit logging middleware captures all mutating requests with user identity
- Database isolation: cross-database access revoked in init script (lines 40-44)
- `auth_dev_mode` defaults to `False` in config (line 68), only enabled via explicit env var
- Token type checking prevents refresh tokens from being used as access tokens
- Subprocess usage in `video_parser.py` uses `create_subprocess_exec` (not `shell=True`) with hardcoded command arguments -- no injection risk
- No pickle, unsafe YAML, or eval usage found in the codebase
- No `dangerouslySetInnerHTML` usage in the frontend React components

### Security Score

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Secrets Management | 7 | 10 | Strong validation at startup; init script and SecretStr gaps remain |
| Container Security | 8 | 10 | Good hardening; dev volume mounts still read-write |
| Network Security | 6 | 10 | Prod overlay good for core services; CIB7/MinIO/Mailpit gaps |
| Authentication | 9 | 10 | Comprehensive: JWT rotation, blacklisting, fail-closed, cookie security |
| Encryption | 8 | 10 | PBKDF2 KDF with 600k iterations; fixed salt is a minor issue |
| CORS/Headers | 9 | 10 | Explicit origins, methods, headers; full security header suite |
| Input Validation | 7 | 10 | Good parameterized queries; XSS in CF worker unresolved |
| Audit/Logging | 9 | 10 | Comprehensive audit middleware; no sensitive data in logs |
| **Overall** | **7.9** | **10** | |
