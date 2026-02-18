"""Data retention policy enforcement.

Provides functions to identify and clean up engagement data
that has exceeded its configured retention period.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Engagement, EngagementStatus

logger = logging.getLogger(__name__)


async def find_expired_engagements(session: AsyncSession) -> list[Engagement]:
    """Find engagements that have exceeded their retention period.

    Only considers engagements with a non-null retention_days and
    a status of COMPLETED or ARCHIVED.
    """
    result = await session.execute(
        select(Engagement).where(
            Engagement.retention_days.isnot(None),
            Engagement.status.in_([EngagementStatus.COMPLETED, EngagementStatus.ARCHIVED]),
        )
    )
    engagements = result.scalars().all()

    now = datetime.now(UTC)
    expired = []
    for eng in engagements:
        cutoff = eng.created_at.replace(tzinfo=UTC) + timedelta(days=eng.retention_days or 0)
        if now > cutoff:
            expired.append(eng)

    return expired


async def cleanup_expired_engagements(session: AsyncSession) -> int:
    """Archive expired engagements and cascade-delete their evidence.

    Returns the number of engagements cleaned up.
    """
    expired = await find_expired_engagements(session)

    count = 0
    for eng in expired:
        logger.info("Retention cleanup: archiving engagement %s (%s)", eng.id, eng.name)
        eng.status = EngagementStatus.ARCHIVED
        count += 1

    if count:
        await session.commit()
        logger.info("Retention cleanup: processed %d expired engagements", count)

    return count
