"""Authentication API routes.

Provides:
- POST /api/v1/auth/token    (dev mode: email+password login — returns raw tokens)
- POST /api/v1/auth/login    (cookie-based login for browser clients — Issue #156)
- POST /api/v1/auth/refresh  (refresh access token — supports both body and cookie)
- GET  /api/v1/auth/me       (current user info)
- POST /api/v1/auth/logout   (blacklist token + clear cookies)
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    blacklist_token,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    is_token_blacklisted,
    set_auth_cookies,
    verify_password,
)
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)

# Use Redis-backed storage for multi-worker safety when REDIS_URL is available.
_redis_url: str | None = None
try:
    _settings = Settings()
    _redis_url = _settings.redis_url
except Exception:
    logger.warning("Settings load failed for rate limiter Redis URL, using in-memory storage")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=_redis_url or "memory://",
)

# Per-email lockout constants
_LOGIN_LOCKOUT_MAX_ATTEMPTS = 10
_LOGIN_LOCKOUT_WINDOW_SECONDS = 900  # 15 minutes


def _get_redis_client(request: Request):  # type: ignore[return]
    """Extract the Redis client from application state, or None if unavailable."""
    state = getattr(getattr(request, "app", None), "state", None)
    return getattr(state, "redis_client", None) if state else None


async def _check_email_lockout(email: str, request: Request) -> None:
    """Check per-email failed login counter in Redis.

    Blocks login attempts for an email after too many failures,
    regardless of source IP. This defends against distributed
    credential stuffing attacks.
    """
    redis_client = _get_redis_client(request)
    if redis_client is None:
        return
    key = f"login_lockout:{email}"
    try:
        count = await redis_client.get(key)
        if count is not None and int(count) >= _LOGIN_LOCKOUT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
            )
    except HTTPException:
        raise
    except Exception:
        logger.debug("Email lockout check failed, allowing request")


async def _record_failed_login(email: str, request: Request) -> None:
    """Increment per-email failed login counter in Redis."""
    redis_client = _get_redis_client(request)
    if redis_client is None:
        return
    key = f"login_lockout:{email}"
    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _LOGIN_LOCKOUT_WINDOW_SECONDS)
        await pipe.execute()
    except Exception:
        logger.debug("Failed to record login failure for email lockout")


async def _clear_login_lockout(email: str, request: Request) -> None:
    """Clear per-email failed login counter on successful login."""
    redis_client = _get_redis_client(request)
    if redis_client is None:
        return
    with contextlib.suppress(Exception):
        await redis_client.delete(f"login_lockout:{email}")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TokenRequest(BaseModel):
    """Login request (dev mode only)."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class UserResponse(BaseModel):
    """User info response."""

    model_config = {"from_attributes": True}

    id: UUID
    email: str
    name: str
    role: UserRole
    is_active: bool


class LoginResponse(BaseModel):
    """Response for cookie-based login (Issue #156).

    Deliberately omits the raw token — tokens are set as HttpOnly cookies
    instead so they are not accessible to JavaScript.
    """

    message: str
    user_id: str


class RefreshCookieResponse(BaseModel):
    """Response for cookie-based token refresh (Issue #156)."""

    message: str


class LogoutResponse(BaseModel):
    """Response for logout."""

    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def get_token(
    request: Request,
    payload: TokenRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Get an access token via email + password (dev mode only).

    In production, tokens come from the external OIDC provider.
    This endpoint is only available when auth_dev_mode is True.
    """
    if not settings.auth_dev_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev-mode token endpoint is disabled",
        )

    # Per-email lockout check (defends against distributed credential stuffing)
    await _check_email_lockout(payload.email, request)

    # Look up user
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        await _record_failed_login(payload.email, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.hashed_password):
        await _record_failed_login(payload.email, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    await _clear_login_lockout(payload.email, request)

    # Build token claims
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
    }

    return {
        "access_token": create_access_token(claims, settings),
        "refresh_token": create_refresh_token(claims, settings),
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Refresh an access token using a valid refresh token."""
    # Check if the refresh token has been blacklisted (e.g. after logout)
    if await is_token_blacklisted(request, payload.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    decoded = decode_token(payload.refresh_token, settings)

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: expected refresh token",
        )

    user_id_str = decoded.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    # Verify user still exists and is active
    result = await session.execute(select(User).where(User.id == UUID(user_id_str)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
    }

    return {
        "access_token": create_access_token(claims, settings),
        "refresh_token": create_refresh_token(claims, settings),
        "token_type": "bearer",
    }


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: TokenRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Cookie-based login for browser clients (Issue #156).

    Validates email + password, creates access and refresh tokens, and sets
    them as HttpOnly cookies on the response.  The raw token values are
    **never** included in the response body so they are not accessible to
    JavaScript.

    The access cookie uses SameSite=Lax, which provides baseline CSRF
    protection for state-changing requests from third-party contexts.
    """
    # Per-email lockout check (defends against distributed credential stuffing)
    await _check_email_lockout(payload.email, request)

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        await _record_failed_login(payload.email, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.hashed_password):
        await _record_failed_login(payload.email, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    await _clear_login_lockout(payload.email, request)

    claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
    }
    access_token = create_access_token(claims, settings)
    refresh_token_value = create_refresh_token(claims, settings)

    response = JSONResponse(
        content={"message": "Login successful", "user_id": str(user.id)},
        status_code=status.HTTP_200_OK,
    )
    set_auth_cookies(response, access_token, refresh_token_value, settings)
    return response


@router.post("/refresh/cookie", response_model=RefreshCookieResponse)
@limiter.limit("10/minute")
async def refresh_token_cookie(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Refresh the access token using the ``kmflow_refresh`` HttpOnly cookie.

    This endpoint is the cookie-equivalent of ``POST /refresh`` and is
    intended for browser clients.  The refresh cookie is path-restricted to
    ``/api/v1/auth/refresh`` (and this ``/api/v1/auth/refresh/cookie`` path
    sits under that prefix), so the browser will send it only here.

    On success a new access cookie is set; the refresh cookie is unchanged.
    """
    refresh_token_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh cookie missing",
        )

    # Check if the refresh token has been blacklisted (e.g. after logout)
    if await is_token_blacklisted(request, refresh_token_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    decoded = decode_token(refresh_token_value, settings)

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: expected refresh token",
        )

    user_id_str = decoded.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    result = await session.execute(select(User).where(User.id == UUID(user_id_str)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
    }
    new_access_token = create_access_token(claims, settings)
    new_refresh_token = create_refresh_token(claims, settings)

    response = JSONResponse(
        content={"message": "Token refreshed"},
        status_code=status.HTTP_200_OK,
    )
    set_auth_cookies(response, new_access_token, new_refresh_token, settings)
    return response


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the currently authenticated user's info."""
    return current_user


@router.post("/logout", status_code=status.HTTP_200_OK, response_model=LogoutResponse)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Invalidate the current access token and clear auth cookies.

    Supports both bearer-header clients (API/MCP) and cookie-based browser
    sessions.  The token extracted from either source is blacklisted in Redis.
    Both HttpOnly cookies are cleared regardless of auth source.
    """
    token: str | None = None

    token = credentials.credentials if credentials is not None else request.cookies.get(ACCESS_COOKIE_NAME)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Blacklist the access token
    await blacklist_token(request, token)

    # Also blacklist the refresh token if present (prevents reuse after logout)
    refresh_token_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token_value:
        await blacklist_token(request, refresh_token_value, expires_in=settings.jwt_refresh_token_expire_minutes * 60)

    response = JSONResponse(
        content={"message": "Logged out"},
        status_code=status.HTTP_200_OK,
    )
    clear_auth_cookies(response, settings)
    return response
