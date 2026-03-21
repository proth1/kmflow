"""CSRF protection middleware for cookie-authenticated mutation endpoints.

Validates the presence and correctness of a CSRF token on state-changing
requests (POST, PUT, PATCH, DELETE) when the request uses cookie-based
authentication. Bearer-token (API/MCP) requests are exempt.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src.core.auth import ACCESS_COOKIE_NAME
from src.core.config import get_settings

logger = logging.getLogger(__name__)

CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "kmflow_csrf"
CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce double-submit cookie CSRF protection for cookie-auth requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only enforce on mutation methods
        if request.method in CSRF_SAFE_METHODS:
            response = await call_next(request)
            # Set CSRF cookie on safe requests so client can read it
            if request.cookies.get(ACCESS_COOKIE_NAME):
                self._ensure_csrf_cookie(response, request)
            return response

        # Skip CSRF check for bearer-token requests (no cookie auth)
        if not request.cookies.get(ACCESS_COOKIE_NAME):
            return await call_next(request)

        # Validate CSRF token
        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        csrf_header = request.headers.get(CSRF_HEADER)

        if not csrf_cookie or not csrf_header:
            return Response(
                content='{"detail":"CSRF token missing"}',
                status_code=403,
                media_type="application/json",
            )

        access_cookie = request.cookies.get(ACCESS_COOKIE_NAME, "")
        expected_token = generate_csrf_token(access_cookie)
        if not hmac.compare_digest(expected_token, csrf_header):
            return Response(
                content='{"detail":"CSRF token mismatch"}',
                status_code=403,
                media_type="application/json",
            )

        response = await call_next(request)
        return response

    def _ensure_csrf_cookie(self, response: Response, request: Request) -> None:
        """Set the CSRF cookie bound to the current session if not already present."""
        if not request.cookies.get(CSRF_COOKIE):
            access_cookie = request.cookies.get(ACCESS_COOKIE_NAME, "")
            token = generate_csrf_token(access_cookie)
            settings = get_settings()
            response.set_cookie(
                key=CSRF_COOKIE,
                value=token,
                httponly=False,  # Client JS must read this
                secure=settings.cookie_secure,
                samesite="lax",
                path="/",
            )


def generate_csrf_token(access_cookie_value: str) -> str:
    """Generate CSRF token cryptographically bound to the current session."""
    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    return hmac.new(
        secret.encode(),
        access_cookie_value.encode(),
        hashlib.sha256,
    ).hexdigest()
