"""Audit logging middleware for mutating API requests.

Automatically logs POST, PUT, PATCH, DELETE requests with user identity,
endpoint path, and engagement context to the application audit log.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all mutating HTTP requests for audit trail.

    Captures method, path, user identity (from JWT), response status,
    and request duration. Logs to structured application logger.
    Non-mutating requests (GET, HEAD, OPTIONS) are skipped.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)

        start = time.monotonic()
        user_id = "anonymous"

        # Extract user identity from request state (set by auth dependencies)
        if hasattr(request.state, "user"):
            user_id = str(getattr(request.state.user, "id", "anonymous"))

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
            "AUDIT method=%s path=%s user=%s status=%d duration_ms=%.2f engagement=%s",
            request.method,
            request.url.path,
            user_id,
            response.status_code,
            duration_ms,
            engagement_id or "none",
        )

        # Also persist to database for compliance
        try:
            from src.core.audit import log_audit_event_async
            await log_audit_event_async(
                method=request.method,
                path=request.url.path,
                user_id=user_id,
                status_code=response.status_code,
                engagement_id=engagement_id,
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # Don't fail requests if audit persistence fails

        response.headers["X-Audit-Logged"] = "true"
        return response
