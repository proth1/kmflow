"""User management and engagement membership API routes.

Provides:
- POST   /api/v1/users                          (admin only)
- GET    /api/v1/users                          (admin only)
- GET    /api/v1/users/{id}                     (authenticated)
- PATCH  /api/v1/users/{id}                     (admin only)
- POST   /api/v1/engagements/{id}/members       (lead+ only)
- DELETE /api/v1/engagements/{id}/members/{uid}  (lead+ only)
- GET    /api/v1/engagements/{id}/members       (authenticated)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import get_current_user, hash_password
from src.core.models import AuditAction, AuditLog, Engagement, EngagementMember, User, UserRole
from src.core.permissions import has_permission, has_role_level, require_engagement_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Schema for creating a user."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.PROCESS_ANALYST
    password: str | None = Field(None, min_length=8)


class UserUpdate(BaseModel):
    """Schema for updating a user (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User response schema."""

    model_config = {"from_attributes": True}

    id: UUID
    email: str
    name: str
    role: UserRole
    is_active: bool


class UserListResponse(BaseModel):
    """Paginated user list response."""

    items: list[UserResponse]
    total: int


class MemberCreate(BaseModel):
    """Schema for adding a member to an engagement."""

    user_id: UUID
    role_in_engagement: str = "member"


class MemberResponse(BaseModel):
    """Engagement member response."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    user_id: UUID
    role_in_engagement: str


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


@router.post("/api/v1/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """Create a new user (platform admin only)."""
    if not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can create users",
        )

    # Check for duplicate email
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {payload.email} already exists",
        )

    hashed_pw = hash_password(payload.password) if payload.password else None

    user = User(
        email=payload.email,
        name=payload.name,
        role=payload.role,
        is_active=True,
        hashed_password=hashed_pw,
    )
    session.add(user)
    await session.flush()

    audit = AuditLog(
        action=AuditAction.USER_CREATED,
        actor=str(current_user.id),
        details=f"Created user {payload.email} with role {payload.role}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(user)
    return user


@router.get("/api/v1/users", response_model=UserListResponse)
async def list_users(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all users (platform admin only)."""
    if not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can list users",
        )

    query = select(User).offset(offset).limit(limit)
    result = await session.execute(query)
    users = list(result.scalars().all())

    count_result = await session.execute(select(func.count()).select_from(User))
    total = count_result.scalar() or 0

    return {"items": users, "total": total}


@router.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """Get a user by ID.

    Non-admin users may only view their own profile.
    """
    # Non-admin users can only view their own profile (IDOR prevention)
    if not has_role_level(current_user, UserRole.PLATFORM_ADMIN) and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return user


@router.patch("/api/v1/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    """Update a user (platform admin only)."""
    if not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform admins can update users",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(user, field_name, value)

    audit = AuditLog(
        action=AuditAction.USER_UPDATED,
        actor=str(current_user.id),
        details=f"Updated user {user_id}: {list(update_data.keys())}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Engagement membership
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/engagements/{engagement_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_engagement_member(
    engagement_id: UUID,
    payload: MemberCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _engagement_user: User = Depends(require_engagement_access),
) -> EngagementMember:
    """Add a member to an engagement (engagement lead+ or admin)."""
    if not has_permission(current_user, "team:manage") and not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage team members",
        )

    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if eng_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Verify user exists
    user_result = await session.execute(select(User).where(User.id == payload.user_id))
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {payload.user_id} not found",
        )

    # Check for existing membership
    existing = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == payload.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this engagement",
        )

    member = EngagementMember(
        engagement_id=engagement_id,
        user_id=payload.user_id,
        role_in_engagement=payload.role_in_engagement,
    )
    session.add(member)
    await session.flush()

    audit = AuditLog(
        engagement_id=engagement_id,
        action=AuditAction.MEMBER_ADDED,
        actor=str(current_user.id),
        details=f"Added user {payload.user_id} as {payload.role_in_engagement}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(member)
    return member


@router.delete(
    "/api/v1/engagements/{engagement_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_engagement_member(
    engagement_id: UUID,
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _engagement_user: User = Depends(require_engagement_access),
) -> None:
    """Remove a member from an engagement (engagement lead+ or admin)."""
    if not has_permission(current_user, "team:manage") and not has_role_level(current_user, UserRole.PLATFORM_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage team members",
        )

    result = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    await session.delete(member)

    audit = AuditLog(
        engagement_id=engagement_id,
        action=AuditAction.MEMBER_REMOVED,
        actor=str(current_user.id),
        details=f"Removed user {user_id} from engagement",
    )
    session.add(audit)

    await session.commit()


@router.get("/api/v1/engagements/{engagement_id}/members", response_model=list[MemberResponse])
async def list_engagement_members(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _engagement_user: User = Depends(require_engagement_access),
) -> list[EngagementMember]:
    """List all members of an engagement."""
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if eng_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    result = await session.execute(select(EngagementMember).where(EngagementMember.engagement_id == engagement_id))
    return list(result.scalars().all())
