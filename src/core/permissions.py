"""Role-based access control (RBAC) for KMFlow.

Defines the permission matrix and FastAPI dependencies for checking
user roles and permissions.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from src.core.auth import get_current_user
from src.core.models import EngagementMember, User, UserRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Permission matrix
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "platform_admin": ["*"],
    "engagement_lead": [
        "engagement:create",
        "engagement:read",
        "engagement:update",
        "engagement:delete",
        "evidence:create",
        "evidence:read",
        "evidence:update",
        "evidence:delete",
        "pov:generate",
        "pov:read",
        "team:manage",
        "monitoring:configure",
        "monitoring:manage",
        "monitoring:read",
        "alerts:manage",
        "alerts:read",
        "alerts:acknowledge",
        "simulation:create",
        "simulation:run",
        "simulation:read",
        "patterns:create",
        "patterns:apply",
        "patterns:read",
        "portal:manage",
        "portal:read",
        "copilot:query",
        "conformance:check",
        "conformance:manage",
        "governance:read",
        "governance:write",
        "transfer:read",
        "transfer:write",
        "incident:read",
        "incident:write",
    ],
    "process_analyst": [
        "engagement:read",
        "evidence:create",
        "evidence:read",
        "evidence:update",
        "pov:generate",
        "pov:read",
        "monitoring:read",
        "alerts:read",
        "alerts:acknowledge",
        "simulation:read",
        "patterns:read",
        "copilot:query",
        "conformance:check",
        "governance:read",
        "transfer:read",
        "incident:read",
    ],
    "evidence_reviewer": [
        "engagement:read",
        "evidence:read",
        "evidence:validate",
        "monitoring:read",
        "alerts:read",
        "governance:read",
        "transfer:read",
        "incident:read",
    ],
    "client_viewer": [
        "engagement:read",
        "pov:read",
        "portal:read",
        "monitoring:read",
    ],
}

# Ordered from most to least privileged for role-level comparisons
ROLE_HIERARCHY: list[UserRole] = [
    UserRole.PLATFORM_ADMIN,
    UserRole.ENGAGEMENT_LEAD,
    UserRole.PROCESS_ANALYST,
    UserRole.EVIDENCE_REVIEWER,
    UserRole.CLIENT_VIEWER,
]


def has_permission(user: User, permission: str) -> bool:
    """Check if a user's role grants a specific permission.

    Args:
        user: The user to check.
        permission: The permission string (e.g. "evidence:read").

    Returns:
        True if the role grants the permission.
    """
    role_perms = ROLE_PERMISSIONS.get(user.role.value, [])
    return "*" in role_perms or permission in role_perms


def has_role_level(user: User, minimum_role: UserRole) -> bool:
    """Check if a user has at least the given role level.

    The role hierarchy is defined in ROLE_HIERARCHY (index 0 = most privileged).

    Args:
        user: The user to check.
        minimum_role: The minimum required role.

    Returns:
        True if the user's role is at or above the minimum.
    """
    try:
        user_level = ROLE_HIERARCHY.index(user.role)
        required_level = ROLE_HIERARCHY.index(minimum_role)
    except ValueError:
        return False
    return user_level <= required_level


# ---------------------------------------------------------------------------
# FastAPI dependency factories
# ---------------------------------------------------------------------------


def require_permission(permission: str) -> Any:
    """Create a FastAPI dependency that checks a specific permission.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_permission("evidence:read"))])

    Args:
        permission: The permission string to check.

    Returns:
        A FastAPI dependency callable.
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required",
            )
        return user

    return _check


def require_role(role: UserRole) -> Any:
    """Create a FastAPI dependency that checks minimum role level.

    Usage:
        @router.post("/admin", dependencies=[Depends(require_role(UserRole.PLATFORM_ADMIN))])

    Args:
        role: The minimum role level required.

    Returns:
        A FastAPI dependency callable.
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if not has_role_level(user, role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role: {role.value} or higher required",
            )
        return user

    return _check


async def require_engagement_access(
    engagement_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that checks engagement membership.

    Platform admins bypass the membership check.

    Args:
        engagement_id: The engagement to check access for.
        request: The FastAPI request (for database access).
        user: The current authenticated user.

    Returns:
        The user if access is granted.

    Raises:
        HTTPException 403: If the user is not a member of the engagement.
    """
    # Platform admins bypass engagement filtering
    if user.role == UserRole.PLATFORM_ADMIN:
        return user

    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        result = await session.execute(
            select(EngagementMember).where(
                EngagementMember.engagement_id == engagement_id,
                EngagementMember.user_id == user.id,
            )
        )
        member = result.scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this engagement",
        )
    return user
