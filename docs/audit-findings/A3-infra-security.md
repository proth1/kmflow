# A3: Infrastructure Security Audit Findings (2026-03-20 Re-Audit)

**Auditor**: A3 (Infrastructure Security Auditor)
**Date**: 2026-03-20
**Scope**: Docker configuration, secrets management, CORS, encryption, TLS, HSTS, cookie security, network segmentation, Dockerfiles
**Type**: Re-audit following prior audits on 2026-02-20, 2026-02-26, and 2026-03-19

## Remediation Status from Prior Audits

| Prior Finding | Status | Notes |
|---|---|---|
| SECRETS-001: Redis no auth | **REMEDIATED** | `--requirepass` in dev compose (line 72); `${REDIS_PASSWORD:?}` enforced in prod overlay (line 66) |
| SECRETS-002: Default secrets accepted in prod | **REMEDIATED** | `reject_default_secrets_in_production` model_validator in config.py (line 238) |
| SECRETS-003: Fields not using SecretStr | **REMEDIATED** | All five fields (`postgres_password`, `neo4j_password`, `jwt_secret_key`, `encryption_key`, `watermark_signing_key`) now use `SecretStr` (config.py lines 42, 50, 64, 70, 71) |
| CORS-001: Wildcard methods/headers | **REMEDIATED** | Explicit method and header lists in main.py (lines 277-278) |
| DOCKER-001: Hardcoded creds in init script | **REMEDIATED** | Init script uses env vars (`$KMFLOW_DB_PASSWORD`, `$CAMUNDA_DB_PASSWORD`) |
| DOCKER-002: Backend runs as root | **REMEDIATED** | Multi-stage Dockerfile with `appuser` non-root user (Dockerfile.backend line 33/48) |
| DOCKER-004: Backend volume mounts not read-only | **REMEDIATED** | Backend mounts now have `:ro` flag (docker-compose.yml lines 225-228) |
| HEADERS-001: Missing HSTS/CSP | **REMEDIATED** | Full security header suite in `SecurityHeadersMiddleware` |
| CRYPTO-001: Weak SHA-256 KDF | **REMEDIATED** | Replaced with PBKDF2 (600,000 iterations) |
| WORKER-001: Reflected XSS | **REMEDIATED** | `escapeHtml()` applied to all dynamic values |
| WORKER-002: Hardcoded Descope project ID | **REMEDIATED** | JWKS URL and issuer now derived from `env.DESCOPE_PROJECT_ID` |
| RATELIMIT-001: Unbounded memory | **REMEDIATED** | Periodic pruning and max-tracked-clients cap added |
| DOCKER-003: OpenAPI exposed unconditionally | **REMEDIATED** | Conditional on `settings.debug` (main.py line 490) |

## Summary (Current State)

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 2     |
| MEDIUM   | 3     |
| LOW      | 4     |
| **Total**| **9** |

---

## HIGH Findings

### [HIGH] NETWORK-001: Production Overlay Missing Port Overrides for CIB7 and MinIO

**File**: `docker-compose.prod.yml` (absence of CIB7/MinIO network overrides)
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:104-105 (CIB7 -- exposed on host with no auth override)
    ports:
      - "${CIB7_PORT:-8081}:8080"

# docker-compose.yml:133-135 (MinIO -- exposed on host with default creds)
    ports:
      - "${MINIO_PORT:-9002}:9000"
      - "${MINIO_CONSOLE_PORT:-9003}:9001"
```
The production overlay (`docker-compose.prod.yml`) sets `ports: []` for postgres (line 20), neo4j (line 44), and redis (line 67), and sets mailpit to `profiles: [never]` (line 169-170). However, there are **no overrides** for `cib7` or `minio` services beyond `ports: []` and `networks`. CIB7 (lines 146-153) only overrides ports/networks/security, and MinIO (lines 155-165) similarly. The CIB7 REST API at `/engine-rest` remains accessible without HTTP-level authentication. MinIO inherits default credentials (`kmflow-dev`/`kmflow-dev-secret`) unless operators remember to set the env vars.
**Description**: CIB7 REST API allows unauthenticated process deployment and task completion. MinIO console provides web UI accessible with default credentials. In production, these services inherit the dev compose host port mappings if the prod overlay is not applied correctly.
**Risk**: An attacker with network access could deploy arbitrary BPMN processes, complete tasks, or access object storage contents. CIB7 unauthenticated REST API access is the most severe vector.
**Recommendation**: (1) Add `MINIO_ROOT_USER: ${MINIO_ROOT_USER:?}` and `MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?}` overrides are present (lines 157-158, confirmed). (2) Add CIB7 HTTP basic auth via `CAMUNDA_USER`/`CAMUNDA_PASSWORD` required env vars in prod overlay. (3) Place CIB7 and MinIO on `data-net` only (no `backend-net` exposure). Note: MinIO prod overlay does have `${MINIO_ROOT_USER:?}` enforcement (lines 157-158) -- re-evaluated as partially remediated. CIB7 REST API auth remains the primary gap.

---

### [HIGH] DOCKER-008: Frontend Container Runs as Root

**File**: `frontend/Dockerfile:22-32`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```dockerfile
# ── Production runner ────────────────────────────────────────
FROM base AS runner
ENV NODE_ENV=production

# Next.js standalone output copies only what's needed
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```
**Description**: The frontend production Dockerfile (`runner` stage) does not create or switch to a non-root user. The `node:20.19-alpine` base image runs as root by default. Compare with `Dockerfile.backend` (lines 33, 48) which creates `appuser` and switches with `USER appuser`. A compromised Node.js process running as root inside the container could modify the container filesystem, install packages, or exploit kernel vulnerabilities more easily.
**Risk**: Container escape or lateral movement is more impactful when the process runs as root. Even with `cap_drop: ALL` and `no-new-privileges:true` in docker-compose, running as a non-root user is a defense-in-depth requirement.
**Recommendation**: Add a non-root user to the frontend Dockerfile `runner` stage:
```dockerfile
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
USER nextjs
```

---

## MEDIUM Findings

### [MEDIUM] CRYPTO-002: PBKDF2 Salt Derived Deterministically from Secret

**File**: `src/core/encryption.py:50`
**Agent**: A3 (Infra Security Auditor)
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
**Description**: The PBKDF2 key derivation uses a salt deterministically computed from the secret itself (`sha256(secret)[:16]`). Standard practice recommends a random salt stored alongside the derived key. Two deployments with the same encryption key produce identical derived keys. The code comments (lines 36-44) acknowledge this is a known limitation and explain why changing the salt derivation would break existing ciphertext.
**Risk**: Moderate. If an attacker obtains the derived Fernet key from one deployment, it is valid in any other deployment using the same input secret. The 600,000 iteration count and production secret enforcement (`reject_default_secrets_in_production`) substantially mitigate brute-force risk.
**Recommendation**: For new deployments, generate a random salt and store it as `ENCRYPTION_SALT` env var. Existing deployments should document this as an accepted risk in a security decision record.

---

### [MEDIUM] NETWORK-002: Default Dev Database Connections Use Unencrypted Transport

**File**: `src/core/config.py:48` (Neo4j) and `src/core/config.py:221-225` (PostgreSQL)
**Agent**: A3 (Infra Security Auditor)
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
**Description**: Default config uses unencrypted `bolt://` for Neo4j and `postgresql+asyncpg://` without SSL for PostgreSQL. Production overlay correctly overrides with encrypted variants. Within a single-host Docker bridge network, unencrypted connections are acceptable. The risk is for multi-host deployments where defaults could be accidentally used.
**Risk**: Credentials and query data traverse the network in plaintext if production doesn't override defaults. The prod overlay mitigates this for the standard deployment path.
**Recommendation**: Consider adding a `reject_default_secrets_in_production` style check for unencrypted database URIs when `APP_ENV != development`.

---

### [MEDIUM] CONFIG-002: Redis URL Fallback Omits Password

**File**: `src/core/config.py:227`
**Agent**: A3 (Infra Security Auditor)
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

### [LOW] DOCKER-005: Frontend-Dev Volume Mounts Lack Read-Only Flag

**File**: `docker-compose.yml:297-299`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
  frontend-dev:
    profiles: ["dev"]
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
      - ./frontend/next.config.js:/app/next.config.js
```
The backend service correctly uses `:ro` (lines 225-228):
```yaml
    volumes:
      - ./src:/app/src:ro
      - ./scripts:/app/scripts:ro
```
**Description**: The `frontend-dev` service mounts host directories with default read-write access. This service is gated behind the `dev` profile and only used for local development with hot reload. A compromised container could modify host source files.
**Risk**: Low -- only affects local development and requires container compromise.
**Recommendation**: Add `:ro` to source mounts. If hot reload breaks, add `tmpfs: /app/.next` to the service.

---

### [LOW] DOCKER-006: AUTH_DEV_MODE and COOKIE_SECURE Not Explicitly Set in Production Overlay

**File**: `docker-compose.prod.yml:88-93`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
# docker-compose.prod.yml:88-93 (prod overlay backend environment)
  backend:
    environment:
      APP_ENV: production
      DEBUG: "false"
      AUTH_DEV_MODE: "false"
      LOG_LEVEL: WARNING
      COOKIE_SECURE: "true"
      ENABLE_HSTS: "true"
```
**Description**: The production overlay now explicitly sets `AUTH_DEV_MODE: "false"` (line 92) and `COOKIE_SECURE: "true"` (line 94). Additionally, the `validate_dev_mode_requires_debug` validator (config.py:231-234) prevents `AUTH_DEV_MODE=true` when `DEBUG=false`. This finding from the prior audit is **partially remediated** -- the explicit overrides are present. Retaining as LOW for documentation completeness.
**Risk**: Low -- defense-in-depth is properly layered with both config validation and explicit overrides.
**Recommendation**: No further action required. The explicit overrides and validator provide adequate protection.

---

### [LOW] DOCKER-007: PostgreSQL Superuser Password Variable Naming Asymmetry

**File**: `docker-compose.yml:12` and `docker-compose.prod.yml:17-19`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
# docker-compose.yml:12 (uses POSTGRES_SUPERUSER_PASSWORD)
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD:-postgres_dev}

# docker-compose.prod.yml:17-19 (uses POSTGRES_PASSWORD)
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}
```
**Description**: The dev compose uses `POSTGRES_SUPERUSER_PASSWORD` shell variable while the prod overlay uses `POSTGRES_PASSWORD` shell variable, both mapping to the container's `POSTGRES_PASSWORD` env var. The prod overlay correctly requires a non-empty value via `:?` syntax.
**Risk**: Low -- variable naming asymmetry could cause operator confusion during deployment, but production enforcement is sound.
**Recommendation**: Align variable naming between dev and prod compose files for clarity.

---

### [LOW] SEED-001: Hardcoded Superuser Credentials in seed_demo.py

**File**: `scripts/seed_demo.py:132`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
DB_URL = _os.environ.get(
    "SEED_DB_URL",
    "postgresql+asyncpg://postgres:postgres_dev@localhost:5433/kmflow",
)
```
**Description**: The seed script contains a hardcoded fallback database URL with the superuser password `postgres_dev`. This is used only for local development seeding and is overridden by `SEED_DB_URL` in Docker (backend-entrypoint.sh line 11). The entrypoint correctly clears superuser credentials after seeding (line 19: `unset SEED_DB_URL ... POSTGRES_SUPERUSER_PASSWORD`).
**Risk**: Low -- the hardcoded password matches the dev default in docker-compose.yml. The script is only executed when `AUTH_DEV_MODE=true` and is not accessible in production.
**Recommendation**: Consider replacing the hardcoded fallback with a required env var check, or document that this file must never be deployed with production credentials.

---

## Security Posture Assessment

**Overall Risk Level**: MEDIUM-LOW

### Improvements Since Prior Audit (2026-03-19)

The prior audit findings remain accurate. This re-audit confirms:

1. **All 13 prior remediations verified**: SecretStr migration, read-only mounts, dynamic Descope config, XSS fixes, init script env vars, conditional OpenAPI, and others remain in place.
2. **Production overlay is well-structured**: Three-tier network segmentation (`frontend-net`, `backend-net`, `data-net`), `ports: []` for data services, resource limits, log rotation, and `volumes: []` override for bind mounts.
3. **New finding**: Frontend Dockerfile runs as root (HIGH) -- the backend Dockerfile was already fixed but the frontend was missed.
4. **MinIO prod override partially present**: `${MINIO_ROOT_USER:?}` and `${MINIO_ROOT_PASSWORD:?}` are enforced in prod overlay (lines 157-158), reducing NETWORK-001 to CIB7-specific.

### Positive Findings

- `.env` file is properly listed in `.gitignore` (line 26) and NOT tracked by git
- `ENCRYPTION_KEY` and `WATERMARK_SIGNING_KEY` are NOT present in `.env` (only `JWT_SECRET_KEY` is set with a dev-only value)
- `reject_default_secrets_in_production` model validator blocks startup with dev keys outside development (config.py lines 238-271)
- `validate_dev_mode_requires_debug` validator prevents accidental auth bypass (config.py lines 231-234)
- CORS uses explicit origin list, specific HTTP methods, and named headers (main.py lines 273-278)
- Full security header suite: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`, CSP, `Permissions-Policy`, conditional HSTS (security.py lines 60-74)
- All Docker services use `security_opt: [no-new-privileges:true]` and `cap_drop: [ALL]`
- Container resource limits (memory, CPU) set in both dev and prod compose files
- Redis authentication enforced via `--requirepass` with `${REDIS_PASSWORD:?}` in prod (line 66)
- PBKDF2 with 600,000 iterations for encryption key derivation (encryption.py line 51-56)
- Rate limiting at two layers: custom `RateLimitMiddleware` (per-IP, Redis-backed Lua script) and `slowapi` (per-endpoint)
- Rate limiter correctly does NOT trust `X-Forwarded-For` header (security.py lines 122-128)
- Cookie security: `HttpOnly=true` for access/refresh tokens, `Secure` defaults to `true`, `SameSite=Lax` for access, `SameSite=Strict` for refresh with path restriction (auth.py lines 230-249)
- CSRF double-submit cookie pattern implemented (csrf.py + auth.py)
- Database cross-access properly revoked in init script: `REVOKE ALL ON DATABASE kmflow FROM camunda, PUBLIC` (line 35-36)
- Backend entrypoint clears superuser credentials after seeding (backend-entrypoint.sh line 19)
- OpenAPI/ReDoc docs disabled when `debug=False` (main.py line 490-491)
- Generic error handler does not leak internal details to clients (main.py lines 473-479)
- Multi-stage Docker builds for both backend and frontend minimize image surface area
- Backend Dockerfile pins to specific Python version (`python:3.12.11-slim`) for reproducibility
- Backend uses `--require-hashes` for pip install (Dockerfile.backend line 20)
- Production overlay enforces TLS for all database connections: `?ssl=require`, `bolt+s://`, `rediss://` (docker-compose.prod.yml lines 96-98)
- Production overlay disables mailpit entirely via `profiles: [never]` (line 169-170)
- No pickle, eval, or unsafe deserialization patterns found
- BYPASSRLS on kmflow database user is documented and intentional (init script line 17-18) -- required for platform_admin RLS bypass via `SET LOCAL row_security = off`

### Remaining Risks

1. **Frontend runs as root** (HIGH) -- the backend was fixed but the frontend Dockerfile `runner` stage was missed. Should add non-root user.
2. **CIB7 REST API lacks HTTP auth in production** (HIGH) -- the prod overlay sets `ports: []` and restricts networks, but the REST API itself has no authentication layer. If an attacker reaches the backend network, CIB7 is exposed.
3. **Deterministic PBKDF2 salt** (MEDIUM) -- accepted trade-off documented in code comments and `docs/audit-lessons-learned.md`.
4. **Unencrypted default database URIs** (MEDIUM) -- prod overlay correctly overrides with TLS. Risk is for non-standard deployment paths.
5. **Redis URL fallback without password** (MEDIUM) -- could cause silent unauthenticated connections with incomplete config.

### Security Score

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Secrets Management | 9 | 10 | SecretStr on all credential fields; startup validation; minor Redis URL gap |
| Container Security | 7.5 | 10 | Backend hardened; frontend runs as root; prod overlay gaps for CIB7 auth |
| Network Security | 8 | 10 | Three-tier network segmentation in prod; TLS enforced in prod overlay; CIB7 REST API auth gap |
| Authentication | 9 | 10 | JWT rotation, blacklisting, fail-closed, cookie security, CSRF, rate limiting |
| Encryption | 8 | 10 | PBKDF2 KDF with 600K iterations; deterministic salt is documented trade-off |
| CORS/Headers | 10 | 10 | Explicit origins, methods, headers; full security header suite including conditional HSTS and CSP |
| Cookie Security | 10 | 10 | HttpOnly, Secure (default true), SameSite Lax/Strict, path-restricted refresh, CSRF double-submit |
| Audit/Logging | 9 | 10 | Comprehensive audit middleware; no sensitive data in responses; request ID tracking |
| **Overall** | **8.4** | **10** | Slightly lower than prior due to newly identified frontend-root finding; otherwise stable |
