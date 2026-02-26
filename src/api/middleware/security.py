"""Security middleware for KMFlow.

Provides:
- Request ID middleware (X-Request-ID header)
- Rate limiting middleware (in-memory, per-IP)
- Security headers middleware (X-Content-Type-Options, etc.)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass

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
    """Add standard security headers and API version to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-API-Version"] = API_VERSION
        # Only add HSTS in non-development environments
        if not getattr(settings, "debug", False):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response


# ---------------------------------------------------------------------------
# Rate Limiting Middleware
# ---------------------------------------------------------------------------


@dataclass
class _RateLimitEntry:
    """Track request counts within a time window for a single client."""

    count: int = 0
    window_start: float = 0.0


# Maximum number of tracked client IPs before pruning stale entries.
_MAX_TRACKED_CLIENTS = 50_000
# How often (in requests) to run the pruning sweep.
_PRUNE_INTERVAL = 1000


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP rate limiter.

    Limits each client IP to `max_requests` within `window_seconds`.
    Returns 429 Too Many Requests when the limit is exceeded.

    Note: This is per-process only.  In multi-worker deployments the
    effective limit is ``workers * max_requests``.  For production
    multi-worker deployments, replace with Redis-backed rate limiting.
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
        self._clients: dict[str, _RateLimitEntry] = defaultdict(_RateLimitEntry)
        self._request_counter: int = 0

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from the ASGI connection.

        Only ``request.client.host`` is used.  ``X-Forwarded-For`` is NOT
        trusted because an attacker can spoof the header to bypass rate
        limits.  In production, configure the reverse proxy (nginx / ALB)
        to set the real IP via ASGI ``client`` instead.
        """
        return request.client.host if request.client else "unknown"

    def _prune_stale(self, now: float) -> None:
        """Remove expired client entries to prevent unbounded memory growth."""
        stale = [
            ip
            for ip, entry in self._clients.items()
            if now - entry.window_start >= self.window_seconds
        ]
        for ip in stale:
            del self._clients[ip]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        # Periodic pruning to bound memory usage
        self._request_counter += 1
        if self._request_counter >= _PRUNE_INTERVAL or len(self._clients) > _MAX_TRACKED_CLIENTS:
            self._prune_stale(now)
            self._request_counter = 0

        entry = self._clients[client_ip]

        # Reset window if expired
        if now - entry.window_start >= self.window_seconds:
            entry.count = 0
            entry.window_start = now

        entry.count += 1

        if entry.count > self.max_requests:
            retry_after = int(self.window_seconds - (now - entry.window_start))
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(max(retry_after, 1))},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.max_requests - entry.count))
        return response
