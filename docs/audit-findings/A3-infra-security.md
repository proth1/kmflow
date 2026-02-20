# A3: Infrastructure Security Audit Findings

**Auditor**: A3 (Infrastructure Security Auditor)
**Date**: 2026-02-20
**Scope**: Docker configuration, Cloudflare worker, Redis/Neo4j authentication, secrets management, CORS, encryption

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 4     |
| MEDIUM   | 5     |
| LOW      | 3     |
| **Total**| **14**|

---

## CRITICAL Findings

### [CRITICAL] SECRETS-001: Redis Deployed Without Authentication

**File**: `docker-compose.yml:57-75`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
  redis:
    image: redis:7.4-alpine
    container_name: kmflow-redis
    ports:
      - "${REDIS_PORT:-6380}:6379"
```
**Description**: The Redis container is started with no `requirepass` configuration in both the development `docker-compose.yml` and the production `docker-compose.prod.yml`. The prod override (`docker-compose.prod.yml:46-47`) adds `--maxmemory` and `--maxmemory-policy` flags but still omits `--requirepass`. The Redis URL in `src/core/redis.py:41-44` uses `redis://host:port/0` with no password component.
**Risk**: Any process on the Docker network (or on the host via the mapped port 6380) can read/write/flush Redis data without credentials. An attacker gaining access to any container could exfiltrate cached session data, manipulate monitoring streams, or flush all data causing denial of service.
**Recommendation**: Add `--requirepass ${REDIS_PASSWORD}` to the Redis command in both compose files. Update `redis_url` in config to include the password: `redis://:${REDIS_PASSWORD}@host:port/0`. Use `${REDIS_PASSWORD:?Set REDIS_PASSWORD}` in the prod override to enforce it.

---

### [CRITICAL] SECRETS-002: Insecure Default JWT and Encryption Keys Accepted in Production

**File**: `src/core/config.py:61-67`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
jwt_secret_key: str = "dev-secret-key-change-in-production"
jwt_secret_keys: str = ""  # Comma-separated list for key rotation
jwt_algorithm: str = "HS256"
jwt_access_token_expire_minutes: int = 30
jwt_refresh_token_expire_minutes: int = 10080  # 7 days
auth_dev_mode: bool = True  # Allow local dev tokens
encryption_key: str = "dev-encryption-key-change-in-production"
```
**Description**: The `jwt_secret_key` and `encryption_key` have hardcoded development defaults. There is no `model_validator` or startup check that rejects these defaults when `app_env == "production"`. If the environment variable is not set, the application silently runs with a publicly known secret key. Additionally, `auth_dev_mode` defaults to `True`, which could bypass authentication in production if not explicitly overridden.
**Risk**: Token forgery -- any attacker who reads this source code can forge valid JWTs. Encrypted data can be decrypted by anyone with access to the default key. The `auth_dev_mode` flag could allow unauthenticated access.
**Recommendation**: Add a `model_validator` that raises a `ValueError` at startup when `app_env == "production"` and any of these conditions are true: `jwt_secret_key` contains "dev-", `encryption_key` contains "dev-", or `auth_dev_mode` is `True`. Use `SecretStr` for `jwt_secret_key` and `encryption_key` to prevent accidental logging.

---

## HIGH Findings

### [HIGH] CORS-001: Overly Permissive CORS Methods and Headers

**File**: `src/api/main.py:162-168`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**Description**: While `allow_origins` is properly restricted to a configured list, `allow_methods=["*"]` and `allow_headers=["*"]` allow all HTTP methods (including TRACE, PATCH, DELETE, OPTIONS) and all custom headers from any allowed origin. Combined with `allow_credentials=True`, this creates an expanded attack surface for cross-origin requests.
**Risk**: A compromised or malicious page on an allowed origin can make arbitrary HTTP method calls with any headers, potentially exploiting TRACE for credential theft or making unexpected DELETE/PATCH calls. The wildcard headers allow forwarding of custom auth headers cross-origin.
**Recommendation**: Restrict `allow_methods` to only those used by the API: `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]`. Restrict `allow_headers` to specific required headers: `["Authorization", "Content-Type", "X-Request-ID", "Accept"]`.

---

### [HIGH] DOCKER-001: Hardcoded Credentials in Docker Compose

**File**: `docker-compose.yml:12, 85, 110-111, 136`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
# PostgreSQL
POSTGRES_PASSWORD: postgres_dev

# CIB7 Camunda
DB_USERNAME: camunda
DB_PASSWORD: camunda_dev

# MinIO
MINIO_ROOT_USER: kmflow-dev
MINIO_ROOT_PASSWORD: kmflow-dev-secret
```
**Description**: Several services have credentials hardcoded directly in the compose file rather than using environment variable substitution with `${VAR:-default}` syntax. Notably, the PostgreSQL root user (`postgres_dev`), the Camunda database credentials (`camunda/camunda_dev`), and MinIO credentials (`kmflow-dev/kmflow-dev-secret`) are hardcoded strings. The MinIO init container also hardcodes the same credentials on line 136. These credentials are committed to version control.
**Risk**: Credentials in version control are visible to all repository contributors. If the dev compose file is accidentally used for a deployment, these known credentials provide immediate access. The Camunda credentials are not environment-variable-overridable.
**Recommendation**: Use `${VAR:?Set VAR}` pattern for all credentials. Move MinIO and Camunda credentials to environment variable substitution like PostgreSQL and Neo4j already use. Add a `.env.example` entry for each. Never commit actual credentials.

---

### [HIGH] DOCKER-002: Backend Container Runs as Root

**File**: `Dockerfile.backend:1-21`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src/ ./src/
...
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```
**Description**: The Dockerfile has no `USER` directive and no creation of a non-root user. The application runs as root inside the container. Additionally, `--reload` is in the production CMD (the dev compose file uses volume mounts, but the Dockerfile CMD itself includes `--reload`), and the `gcc` compiler is left installed in the final image.
**Risk**: Container escape vulnerabilities are significantly more dangerous when the containerized process runs as root. An attacker exploiting an application vulnerability gains root access within the container, making privilege escalation and host escape easier. The `--reload` flag watches file changes and is unnecessary in production, adding attack surface.
**Recommendation**: Add a non-root user: `RUN adduser --disabled-password --no-create-home appuser` and `USER appuser`. Use a multi-stage build to exclude `gcc` from the final image. Remove `--reload` from the Dockerfile CMD (the dev compose can override CMD).

---

### [HIGH] HEADERS-001: Missing HSTS and Content-Security-Policy Headers

**File**: `src/api/middleware/security.py:52-63`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-API-Version"] = API_VERSION
        return response
```
**Description**: The security headers middleware is missing `Strict-Transport-Security` (HSTS), `Content-Security-Policy` (CSP), and `Permissions-Policy` headers. Without HSTS, browsers will not enforce HTTPS, making the application vulnerable to SSL stripping attacks. Without CSP, there is no browser-enforced protection against XSS via script injection.
**Risk**: Without HSTS, MITM attackers can downgrade HTTPS connections to HTTP. Without CSP, any XSS vulnerability in the frontend has unrestricted access to execute arbitrary scripts, make network requests, and exfiltrate data.
**Recommendation**: Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` when not in development mode. Add a restrictive `Content-Security-Policy` header. Add `Permissions-Policy` to disable unused browser features (camera, microphone, geolocation, etc.).

---

## MEDIUM Findings

### [MEDIUM] CRYPTO-001: Weak Key Derivation Using Raw SHA-256

**File**: `src/core/encryption.py:22-29`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
def _derive_fernet_key(secret: str) -> bytes:
    """Derive a valid Fernet key from an arbitrary secret string."""
    try:
        Fernet(secret.encode())
        return secret.encode()
    except (ValueError, Exception):
        derived = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(derived)
```
**Description**: When the input secret is not already a valid Fernet key (which is the common case with human-readable secrets like `dev-encryption-key-change-in-production`), the function falls back to a single SHA-256 hash with no salt and no iterations. This is not a proper key derivation function.
**Risk**: A single-pass SHA-256 without salt is vulnerable to rainbow table and dictionary attacks. If the encryption key has low entropy (e.g., a memorable passphrase), the derived Fernet key can be brute-forced significantly faster than if PBKDF2 or scrypt were used.
**Recommendation**: Replace with a proper KDF such as PBKDF2 with at least 600,000 iterations: `hashlib.pbkdf2_hmac('sha256', secret.encode(), salt, iterations=600_000)`. Use a fixed application-level salt stored alongside the configuration (not a secret, but prevents rainbow tables).

---

### [MEDIUM] WORKER-001: Reflected XSS in Cloudflare Worker Login Page

**File**: `infrastructure/cloudflare-workers/presentation-auth/src/index.ts:628`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```typescript
${error ? `<div class="error">${error}</div>` : ''}
```
**Description**: The `error` parameter is read from the URL query string (`url.searchParams.get('error')`) on line 469 and rendered directly into HTML on line 628 without escaping. An attacker can craft a URL like `/auth/login?error=<script>alert(1)</script>` to inject arbitrary HTML/JavaScript.
The same issue affects `pendingEmail` (line 647) which comes from a cookie value, and `email` in the unauthorized page (line 188). While `pendingEmail` is set server-side via cookie, the `error` parameter is directly attacker-controlled via URL.
**Risk**: Reflected XSS allows an attacker to execute JavaScript in the context of the authentication page. This could be used to steal OTP codes, redirect users to phishing pages, or exfiltrate session cookies (though HttpOnly mitigates cookie theft).
**Recommendation**: HTML-encode all dynamic values before rendering into HTML. Create an `escapeHtml()` function that encodes `<`, `>`, `&`, `"`, and `'` characters. Apply it to `error`, `email`, `pendingEmail`, and `redirect` values.

---

### [MEDIUM] RATELIMIT-001: In-Memory Rate Limiter Unbounded Growth

**File**: `src/api/middleware/security.py:79-128`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests=100, window_seconds=60):
        super().__init__(app)
        self._clients: dict[str, _RateLimitEntry] = defaultdict(_RateLimitEntry)
```
**Description**: The rate limiter stores client entries in an unbounded `defaultdict`. Old entries are never pruned -- the window is only reset for the same IP when it makes a new request after the window expires. An attacker can send requests from many different IPs (or spoof `X-Forwarded-For` headers) to grow this dictionary indefinitely until the process runs out of memory.
**Risk**: Memory exhaustion denial of service. Each unique IP or spoofed `X-Forwarded-For` value creates a permanent entry in the dictionary. Additionally, `X-Forwarded-For` is trusted without validation, allowing rate limit bypass by rotating the header value.
**Recommendation**: Add periodic cleanup of expired entries (e.g., via a background task or LRU eviction). Cap the dictionary size. For production, use Redis-based rate limiting instead of in-memory. Do not trust `X-Forwarded-For` without validating it comes from a trusted proxy.

---

### [MEDIUM] DOCKER-003: OpenAPI Documentation Exposed Unconditionally

**File**: `src/api/main.py:155-156`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
app = FastAPI(
    title=settings.app_name,
    description="AI-powered Process Intelligence platform",
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
```
**Description**: The Swagger UI (`/docs`) and ReDoc (`/redoc`) endpoints are enabled regardless of the environment. In production, these endpoints expose the complete API schema including all endpoint paths, parameters, request/response models, and authentication requirements. This is an information disclosure that assists reconnaissance.
**Risk**: Attackers can enumerate all API endpoints, understand parameter validation rules, and identify potential attack surfaces without any authentication. The OpenAPI schema may also reveal internal implementation details.
**Recommendation**: Conditionally disable docs in production: `docs_url="/docs" if settings.debug else None` and `redoc_url="/redoc" if settings.debug else None`.

---

### [MEDIUM] DOCKER-004: Source Code Volume Mounts in Dev Compose

**File**: `docker-compose.yml:187-189`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
    volumes:
      - ./src:/app/src
      - ./alembic:/app/alembic
      - ./alembic.ini:/app/alembic.ini
```
**Description**: The development compose file mounts host source code directories into the backend container with read-write access. While the production override sets `volumes: []`, if the dev compose is mistakenly used in a deployment context, the container has write access to the host filesystem's source code. Combined with the root user issue (DOCKER-002), a container compromise would allow modification of source code on the host.
**Risk**: A compromised container could modify source code on the host, potentially introducing backdoors that persist across container restarts. The production compose override addresses this, but the default compose file is insecure.
**Recommendation**: Add `:ro` (read-only) to volume mounts in the dev compose: `./src:/app/src:ro`. Ensure the prod override continues to strip volumes.

---

## LOW Findings

### [LOW] DOCKER-005: No Docker Container Security Options

**File**: `docker-compose.yml` (entire file)
**Agent**: A3 (Infra Security Auditor)
**Evidence**: No `security_opt`, `read_only`, `cap_drop`, or `no-new-privileges` directives found in any service definition.
**Description**: None of the containers have security hardening options enabled. Missing configurations include: `security_opt: [no-new-privileges:true]` to prevent privilege escalation, `cap_drop: [ALL]` to drop all Linux capabilities, `read_only: true` for filesystem immutability, and `tmpfs` mounts for writable directories.
**Risk**: Containers retain default Linux capabilities (including potentially dangerous ones like `NET_RAW`, `SYS_CHROOT`). A container compromise has more room for privilege escalation.
**Recommendation**: Add to each service: `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`, then `cap_add` only the specific capabilities needed. Consider `read_only: true` with explicit `tmpfs` for temp directories.

---

### [LOW] NETWORK-001: CIB7 Camunda Engine Has No Authentication

**File**: `src/integrations/camunda.py:20-36`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```python
class CamundaClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _request(self, method, path, *, json=None, files=None, params=None):
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, url, json=json, files=files, params=params)
```
**Description**: The CamundaClient makes HTTP requests to the CIB7 engine REST API with no authentication headers. The CIB7 container (port 8081 on host) exposes the engine REST API. While this is on the internal Docker network, the port is also mapped to the host, making it accessible on localhost:8081 without any credentials.
**Risk**: Any process on the host or Docker network can interact with the BPMN engine -- deploying processes, starting instances, completing tasks. This is lower risk because it is typically only exposed locally in development.
**Recommendation**: Configure CIB7 with basic auth or filter auth and pass credentials from the KMFlow backend. In production, do not expose the CIB7 port to the host.

---

### [LOW] NETWORK-002: All Service Ports Mapped to Host

**File**: `docker-compose.yml:14,41-42,65,88,113-114,149-150,185,222`
**Agent**: A3 (Infra Security Auditor)
**Evidence**:
```yaml
postgres:   "${POSTGRES_PORT:-5433}:5432"
neo4j:      "7475:7474" / "7688:7687"
redis:      "${REDIS_PORT:-6380}:6379"
cib7:       "${CIB7_PORT:-8081}:8080"
minio:      "${MINIO_PORT:-9002}:9000" / "${MINIO_CONSOLE_PORT:-9003}:9001"
mailpit:    "${SMTP_PORT:-1026}:1025" / "${MAILPIT_UI_PORT:-8026}:8025"
backend:    "${BACKEND_PORT:-8002}:8000"
frontend:   "3002:3000"
```
**Description**: Every service in the development compose file maps its ports to the host. In a development context this is convenient, but the production override does not remove these port mappings. Services like PostgreSQL, Neo4j, Redis, and MinIO should only be accessible via the internal Docker network in production.
**Risk**: In production, exposed database ports allow direct access to data stores, bypassing the application's authentication and authorization layer. Combined with weak or absent credentials (SECRETS-001, DOCKER-001), this is especially dangerous.
**Recommendation**: In `docker-compose.prod.yml`, explicitly remove port mappings for internal services: set `ports: []` for postgres, neo4j, redis, cib7, minio, and mailpit. Only expose the backend and frontend ports behind a reverse proxy.

---

## Security Posture Assessment

**Overall Risk Level**: HIGH

The infrastructure has several significant security gaps that need to be addressed before production deployment:

1. **Secrets management** is the most critical area -- Redis has no authentication, and the application accepts known default secrets in production without validation.
2. **Container security** is minimal -- no non-root users, no capability restrictions, no filesystem read-only constraints.
3. **Network exposure** is overly broad -- all ports are mapped to the host and the production overlay does not restrict this.
4. **The Cloudflare worker** has a reflected XSS vulnerability in the login page error handling.
5. **Encryption** uses a weak key derivation function that could be brute-forced if the input secret has low entropy.

**Positive findings**:
- `.env` files are properly gitignored
- Production compose uses `${VAR:?}` syntax for PostgreSQL and Neo4j credentials (but not for all services)
- CORS origins are configurable and not wildcarded
- Session cookies in the Cloudflare worker use `HttpOnly`, `Secure`, and `SameSite=Lax`
- Rate limiting middleware exists (though the implementation needs hardening)
- Security headers middleware exists (though missing HSTS and CSP)
- Audit logging middleware is present
- Request ID middleware provides traceability
