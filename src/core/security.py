"""Engagement-level data isolation utilities.

Provides helper functions that add engagement-scoped WHERE clauses
to SQLAlchemy queries based on user membership.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EngagementMember, User, UserRole

logger = logging.getLogger(__name__)


async def get_accessible_engagement_ids(
    session: AsyncSession,
    user: User,
) -> list[UUID]:
    """Get the list of engagement IDs a user has access to.

    Platform admins get an empty list (signalling "no filter needed").

    Args:
        session: The database session.
        user: The current user.

    Returns:
        A list of engagement UUIDs, or an empty list for admins.
    """
    if user.role == UserRole.PLATFORM_ADMIN:
        return []  # empty = no filtering needed

    result = await session.execute(
        select(EngagementMember.engagement_id).where(
            EngagementMember.user_id == user.id,
        )
    )
    return list(result.scalars().all())


def filter_by_engagement_access(
    query: Select,
    user: User,
    engagement_ids: list[UUID],
    engagement_id_column: Any,
) -> Select:
    """Add a WHERE clause to restrict results to accessible engagements.

    If the user is a platform admin (indicated by empty engagement_ids),
    the query is returned unmodified.

    Args:
        query: The SQLAlchemy select statement.
        user: The current user.
        engagement_ids: List of accessible engagement IDs
            (empty list for admins = no filter).
        engagement_id_column: The column to filter on
            (e.g. EvidenceItem.engagement_id).

    Returns:
        The query with the engagement filter applied (or unchanged for admins).
    """
    if user.role == UserRole.PLATFORM_ADMIN:
        return query

    return query.where(engagement_id_column.in_(engagement_ids))
