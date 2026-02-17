"""Authentication API routes.

Provides:
- POST /api/v1/auth/token  (dev mode: email+password login)
- POST /api/v1/auth/refresh (refresh access token)
- GET  /api/v1/auth/me     (current user info)
- POST /api/v1/auth/logout  (blacklist token)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


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


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/token", response_model=TokenResponse)
async def get_token(
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

    # Look up user
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

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
async def refresh_token(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Refresh an access token using a valid refresh token."""
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


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the currently authenticated user's info."""
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Invalidate the current access token by adding it to the blacklist."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    await blacklist_token(request, credentials.credentials)
