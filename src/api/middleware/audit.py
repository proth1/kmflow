"""Audit logging middleware for all API requests.

Automatically logs every HTTP request with user identity, endpoint path,
IP address, user agent, engagement context, and response status to the
audit trail. Fires asynchronously to avoid adding latency.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.audit import log_audit_event_async

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths exempt from audit logging (health checks, OpenAPI docs)
_SKIP_PATHS = frozenset({"/api/v1/health", "/docs", "/openapi.json", "/redoc"})


def _extract_client_ip(request: Request) -> str:
    """Extract client IP, preferring X-Forwarded-For when behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the chain is the original client
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _extract_resource_type(path: str) -> str | None:
    """Infer resource type from URL path segments."""
    parts = path.strip("/").split("/")
    # Pattern: /api/v1/{resource}/... → resource
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "v1":
        return parts[2]
    return None


async def _persist_audit_event(
    session_factory: object | None,
    **kwargs: object,
) -> None:
    """Persist an audit event to the database (fire-and-forget).

    Called via asyncio.create_task() from the middleware so that the
    database round-trip does not block the HTTP response.
    """
    try:
        if session_factory is not None:
            async with session_factory() as session:
                await log_audit_event_async(**kwargs, session=session)
        else:
            await log_audit_event_async(**kwargs)
    except Exception as e:  # Intentionally broad: audit must not block requests
        logger.warning("Audit persistence failed (request not blocked): %s", e)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests for audit trail compliance.

    Captures method, path, user identity (from JWT), response status,
    IP address, user agent, and request duration. Persists to the
    http_audit_events table via async fire-and-forget.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip health checks and docs
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.monotonic()
        user_id = "anonymous"

        # Extract user identity from request state (set by auth dependencies)
        if hasattr(request.state, "user"):
            user_id = str(getattr(request.state.user, "id", "anonymous"))

        ip_address = _extract_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        resource_type = _extract_resource_type(request.url.path)

        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Extract engagement_id from path if present
        engagement_id = None
        path_parts = request.url.path.split("/")
        if "engagements" in path_parts:
            idx = path_parts.index("engagements")
            if idx + 1 < len(path_parts) and len(path_parts[idx + 1]) > 8:
                engagement_id = path_parts[idx + 1]

        logger.info(
            "AUDIT method=%s path=%s user=%s status=%d duration_ms=%.2f engagement=%s ip=%s",
            request.method,
            request.url.path,
            user_id,
            response.status_code,
            duration_ms,
            engagement_id or "none",
            ip_address,
        )

        # Fire-and-forget: persist audit event asynchronously to avoid
        # adding database latency to the request path.
        session_factory = getattr(request.app.state, "db_session_factory", None)
        asyncio.create_task(
            _persist_audit_event(
                session_factory=session_factory,
                method=request.method,
                path=request.url.path,
                user_id=user_id,
                status_code=response.status_code,
                engagement_id=engagement_id,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_agent=user_agent[:512],
                resource_type=resource_type,
            )
        )

        response.headers["X-Audit-Logged"] = "true"
        return response
