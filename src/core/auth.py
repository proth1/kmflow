"""Authentication module for JWT token management.

Supports:
- External OIDC token validation
- Local dev token creation/validation
- Token expiry checking
- FastAPI dependency for extracting the current user
- HttpOnly cookie helpers for browser-based sessions (Issue #156)
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt
import redis.asyncio as _aioredis
from fastapi import Depends, HTTPException, Request, Response, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.models import User

logger = logging.getLogger(__name__)

# Bearer token scheme (auto_error=False so we can give clear messages)
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password helpers (dev mode only)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict[str, Any],
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        data: Claims to include in the token (must include "sub").
        settings: Application settings. Defaults to get_settings().
        expires_delta: Custom expiry. Defaults to config value.

    Returns:
        Encoded JWT string.
    """
    if settings is None:
        settings = get_settings()

    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def create_refresh_token(
    data: dict[str, Any],
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT refresh token with longer expiry.

    Args:
        data: Claims to include (must include "sub").
        settings: Application settings. Defaults to get_settings().
        expires_delta: Custom expiry. Defaults to config value.

    Returns:
        Encoded JWT string.
    """
    if settings is None:
        settings = get_settings()

    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.jwt_refresh_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: The raw JWT string.
        settings: Application settings.

    Returns:
        The decoded claims dict.

    Raises:
        HTTPException: If the token is invalid or expired.
    """
    if settings is None:
        settings = get_settings()

    # Try each verification key (supports key rotation)
    last_exc: PyJWTError | None = None
    for key in settings.jwt_verification_keys:
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except PyJWTError as exc:
            last_exc = exc
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    ) from last_exc


# ---------------------------------------------------------------------------
# Token blacklist helpers (Redis-backed)
# ---------------------------------------------------------------------------


async def is_token_blacklisted(request: Request | WebSocket, token: str) -> bool:
    """Check if a token has been blacklisted in Redis.

    Returns True if Redis is unavailable (fail-closed for security).
    """
    try:
        redis_client = request.app.state.redis_client
        result = await redis_client.get(f"token:blacklist:{token}")
        return result is not None
    except (ConnectionError, OSError, _aioredis.RedisError):
        logger.warning("Redis unavailable for token blacklist check — failing closed")
        return True


async def blacklist_token(request: Request, token: str, expires_in: int = 1800) -> None:
    """Add a token to the blacklist in Redis.

    Args:
        request: The FastAPI request (to access app.state.redis_client).
        token: The raw JWT string to blacklist.
        expires_in: TTL in seconds (should match remaining token life).
    """
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(f"token:blacklist:{token}", expires_in, "1")
    except (ConnectionError, OSError, _aioredis.RedisError) as exc:
        logger.warning("Token blacklist write failed — token may remain valid: %s", exc)


# ---------------------------------------------------------------------------
# HttpOnly cookie helpers (Issue #156)
# ---------------------------------------------------------------------------

#: Name of the HttpOnly access-token cookie.
ACCESS_COOKIE_NAME = "kmflow_access"

#: Name of the HttpOnly refresh-token cookie.  Scoped to the refresh path so
#: the browser never sends it to any other endpoint.
REFRESH_COOKIE_NAME = "kmflow_refresh"

#: Path restriction for the refresh cookie.
REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"

#: Name of the non-HttpOnly CSRF cookie (readable by JavaScript for
#: double-submit pattern).
CSRF_COOKIE_NAME = "kmflow_csrf"

#: Name of the header that must carry the CSRF token on mutation requests.
CSRF_HEADER_NAME = "x-csrf-token"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    settings: Settings | None = None,
) -> None:
    """Attach HttpOnly auth cookies to *response*.

    Two cookies are set:
    - ``kmflow_access``  — short-lived access token; SameSite=Lax so it is
      sent on top-level navigations (baseline CSRF protection).
    - ``kmflow_refresh`` — longer-lived refresh token; SameSite=Strict and
      path-restricted to ``/api/v1/auth/refresh`` so it cannot be used by
      any other endpoint.

    Args:
        response: The FastAPI ``Response`` object to attach cookies to.
        access_token: Encoded JWT access token string.
        refresh_token: Encoded JWT refresh token string.
        settings: Application settings (defaults to ``get_settings()``).
    """
    if settings is None:
        settings = get_settings()

    domain = settings.cookie_domain or None  # None lets the browser default to the request host
    secure = settings.cookie_secure

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        domain=domain,
        max_age=settings.jwt_refresh_token_expire_minutes * 60,
    )

    # Double-submit CSRF cookie — NOT HttpOnly so JavaScript can read it
    # and send it back via the X-CSRF-Token header on mutation requests.
    # Token is HMAC-SHA256 of the access token, binding it to the session.
    from src.core.csrf import generate_csrf_token

    csrf_token = generate_csrf_token(access_token)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )


def clear_auth_cookies(response: Response, settings: Settings | None = None) -> None:
    """Delete both auth cookies from the browser.

    Sets both cookies to empty values with ``max_age=0`` so browsers
    remove them immediately.

    Args:
        response: The FastAPI ``Response`` object to clear cookies on.
        settings: Application settings (defaults to ``get_settings()``).
    """
    if settings is None:
        settings = get_settings()

    domain = settings.cookie_domain or None
    secure = settings.cookie_secure

    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path="/",
        domain=domain,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        domain=domain,
        httponly=True,
        secure=secure,
        samesite="strict",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        domain=domain,
        httponly=False,
        secure=secure,
        samesite="lax",
    )


# ---------------------------------------------------------------------------
# CSRF verification
# ---------------------------------------------------------------------------


async def verify_csrf_token(request: Request) -> None:
    """FastAPI dependency for double-submit CSRF protection.

    Compares the ``kmflow_csrf`` cookie value against the ``X-CSRF-Token``
    header.  Skips verification for bearer-token requests (API clients)
    since CSRF only applies to cookie-based browser sessions.
    """
    # Bearer-token requests are not vulnerable to CSRF — skip check
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return

    # No CSRF cookie means the client isn't using cookie auth
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if not csrf_cookie:
        return

    csrf_header = request.headers.get(CSRF_HEADER_NAME)
    if not csrf_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing",
        )

    # Validate against HMAC of the access cookie (session-bound token)
    from src.core.csrf import generate_csrf_token

    access_cookie = request.cookies.get(ACCESS_COOKIE_NAME, "")
    expected = generate_csrf_token(access_cookie)
    if not hmac.compare_digest(expected, csrf_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token invalid",
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def _get_session_from_request(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get a database session from request app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency that extracts and validates the current user.

    Auth source priority (Issue #156):
    1. ``Authorization: Bearer <token>`` header — preferred for API/MCP clients.
    2. ``kmflow_access`` HttpOnly cookie — preferred for browser sessions.

    If neither is present a 401 is raised.

    Raises:
        HTTPException 401: If token is missing, invalid, or blacklisted.
        HTTPException 401: If user is not found or inactive.
    """
    token: str | None = None

    token = credentials.credentials if credentials is not None else request.cookies.get(ACCESS_COOKIE_NAME)

    if token is None:
        # Dev mode: auto-authenticate as the first platform_admin user
        if settings.auth_dev_mode:
            if settings.app_env not in ("development", "testing"):
                logger.critical(
                    "AUTH_DEV_MODE is enabled in %s environment — refusing to auto-authenticate. "
                    "This setting is only allowed in development/testing.",
                    settings.app_env,
                )
                raise HTTPException(status_code=503, detail="Server misconfiguration")
            session_factory = request.app.state.db_session_factory
            async with session_factory() as session:
                result = await session.execute(
                    select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)  # noqa: E712
                )
                dev_user = result.scalar_one_or_none()
            if dev_user is not None:
                logger.debug("Auth dev mode: auto-authenticated as user %s", dev_user.id)
                return dev_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token, settings)

    # Reject non-access tokens (e.g. refresh tokens)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check blacklist
    if await is_token_blacklisted(request, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract subject claim
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_websocket_user(
    websocket: WebSocket,
    token: str | None = None,
) -> User | None:
    """Authenticate a WebSocket connection.

    Checks (in order):
    1. Explicit ``token`` query parameter.
    2. ``kmflow_access`` cookie from the upgrade request.
    3. Dev mode fallback — auto-authenticate as platform admin.

    Returns the authenticated :class:`User`, or ``None`` if authentication
    fails (caller should close the socket).
    """
    settings = get_settings()

    # Try token param, then cookie
    jwt_token = token or websocket.cookies.get(ACCESS_COOKIE_NAME)

    if jwt_token is None:
        # Dev mode: return first active admin
        if settings.auth_dev_mode:
            if settings.app_env not in ("development", "testing"):
                raise WebSocketException(code=1008, reason="Server misconfiguration")
            session_factory = websocket.app.state.db_session_factory
            async with session_factory() as session:
                result = await session.execute(
                    select(User).where(User.role == "platform_admin", User.is_active == True).limit(1)  # noqa: E712
                )
                dev_user = result.scalar_one_or_none()
            if dev_user is not None:
                logger.debug("WS auth dev mode: auto-authenticated as user %s", dev_user.id)
                return dev_user
        return None

    try:
        payload = decode_token(jwt_token, settings)
    except (HTTPException, ValueError):
        return None

    if payload.get("type") != "access":
        return None

    try:
        if await is_token_blacklisted(websocket, jwt_token):
            return None
    except Exception:  # Intentionally broad: Redis/DB errors must deny access (fail-secure)
        logger.warning("Token blacklist check failed, denying WebSocket access as a precaution")
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        return None

    session_factory = websocket.app.state.db_session_factory
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user
