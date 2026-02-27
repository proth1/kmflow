"""GDPR erasure background job.

Finds approved erasure requests past their retention/grace period
and anonymises the associated user accounts. Designed to run as a
periodic background task (e.g. via APScheduler or a cron-triggered endpoint).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import User

logger = logging.getLogger(__name__)


async def _anonymize_user(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Replace PII fields on a user record with anonymised values.

    Preserves the user UUID so foreign key relationships remain intact.
    Also anonymises audit log actor references for this user.

    Args:
        user_id: The UUID of the user to anonymise.
        db: An active async database session (caller manages commit).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.warning("GDPR erasure: user %s not found, skipping", user_id)
        return

    anon_id = uuid.uuid4()
    anon_email = f"deleted-{anon_id}@anonymized.local"

    user.name = "Deleted User"
    user.email = anon_email
    user.is_active = False
    user.hashed_password = None
    user.external_id = None

    # Anonymise audit log actor references
    user_id_str = str(user_id)
    await db.execute(
        text("UPDATE audit_logs SET actor = 'anonymized' WHERE actor = :uid"),
        {"uid": user_id_str},
    )

    logger.info("GDPR erasure: anonymised user %s", user_id)


async def run_erasure_job(db: AsyncSession) -> int:
    """Process approved erasure requests that have passed their scheduled date.

    Finds all users with erasure_scheduled_at in the past and
    erasure_requested_at set (indicating an approved erasure request).
    Calls _anonymize_user for each, then marks the request as completed
    by clearing the erasure timestamp fields.

    Args:
        db: An active async database session.

    Returns:
        The number of users anonymised in this run.
    """
    now = datetime.now(UTC)

    result = await db.execute(
        select(User).where(
            User.erasure_requested_at.isnot(None),
            User.erasure_scheduled_at.isnot(None),
            User.erasure_scheduled_at <= now,
            User.is_active == True,  # noqa: E712 — SQLAlchemy filter
        )
    )
    users_to_erase = list(result.scalars().all())

    if not users_to_erase:
        logger.info("GDPR erasure job: no pending erasure requests")
        return 0

    count = 0
    for user in users_to_erase:
        await _anonymize_user(user.id, db)
        # Clear the erasure request fields to mark as completed
        user.erasure_requested_at = None
        user.erasure_scheduled_at = None
        count += 1

    await db.commit()
    logger.info("GDPR erasure job: anonymised %d user(s)", count)
    return count
