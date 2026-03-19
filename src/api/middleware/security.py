"""Security middleware for KMFlow.

Provides:
- Request ID middleware (X-Request-ID header)
- Rate limiting middleware (Redis-backed, per-IP, multi-worker safe)
- Security headers middleware (X-Content-Type-Options, etc.)
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.api.version import API_VERSION
from src.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request ID Middleware
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add a unique X-Request-ID header to every response.

    If the client sends an X-Request-ID, it is preserved. Otherwise,
    a new UUID4 is generated.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        # Store on request state for downstream use
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers and API version to every response.

    Headers are pre-built at construction time to avoid per-request overhead.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self._static_headers: dict[str, str] = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Cache-Control": "no-store",
            "X-API-Version": API_VERSION,
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self'"
            ),
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        }
        if not settings.debug:
            self._static_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.update(self._static_headers)
        return response


# ---------------------------------------------------------------------------
# Rate Limiting Middleware
# ---------------------------------------------------------------------------


_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)
return {count, ttl}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed per-IP rate limiter (multi-worker safe).

    Uses an atomic Lua script (INCR + EXPIRE) for fixed-window counting.
    Each client IP gets a Redis key ``ratelimit:{ip}`` with a TTL equal
    to the window. The counter is shared across all uvicorn workers via
    the same Redis instance.

    Falls back to allowing the request if Redis is unavailable (fail-open for
    availability — rate limiting is a best-effort defence, not an auth gate).
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from the ASGI connection.

        Only ``request.client.host`` is used.  ``X-Forwarded-For`` is NOT
        trusted because an attacker can spoof the header to bypass rate
        limits.  In production, configure the reverse proxy (nginx / ALB)
        to set the real IP via ASGI ``client`` instead.
        """
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = self._get_client_ip(request)
        redis_client = getattr(request.app.state, "redis_client", None)

        count = 0
        ttl = self.window_seconds
        if redis_client is not None:
            try:
                key = f"ratelimit:{client_ip}"
                result = await redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, self.window_seconds)
                count = int(result[0])
                ttl = max(int(result[1]), 1)
            except Exception:
                # Redis unavailable — fail open (allow request)
                logger.debug("Rate limiter Redis unavailable, allowing request")
                count = 0

        if count > self.max_requests:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(ttl)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.max_requests - count))
        return response
