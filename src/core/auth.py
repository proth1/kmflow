"""Authentication module for JWT token management.

Supports:
- External OIDC token validation
- Local dev token creation/validation
- Token expiry checking
- FastAPI dependency for extracting the current user
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
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
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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


async def is_token_blacklisted(request: Request, token: str) -> bool:
    """Check if a token has been blacklisted in Redis.

    Returns True if Redis is unavailable (fail-closed for security).
    """
    try:
        redis = request.app.state.redis_client
        result = await redis.get(f"token:blacklist:{token}")
        return result is not None
    except Exception:
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
        redis = request.app.state.redis_client
        await redis.setex(f"token:blacklist:{token}", expires_in, "1")
    except Exception:
        logger.warning("Redis unavailable for token blacklisting")


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

    Reads the Authorization header, decodes the JWT, checks the blacklist,
    and fetches the user from the database.

    Raises:
        HTTPException 401: If token is missing, invalid, or blacklisted.
        HTTPException 401: If user is not found or inactive.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token, settings)

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
