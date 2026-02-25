"""Data retention policy enforcement.

Provides functions to identify and clean up engagement data
that has exceeded its configured retention period.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditLog,
    CopilotMessage,
    Engagement,
    EngagementStatus,
    EvidenceFragment,
    EvidenceItem,
    HttpAuditEvent,
    PIIQuarantine,
    QuarantineStatus,
    TaskMiningAction,
    TaskMiningEvent,
    TaskMiningSession,
)

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
    """Delete evidence data for expired engagements and archive the engagement record.

    For each expired engagement:
    1. Delete evidence fragments (FK child of evidence_items).
    2. Delete evidence items.
    3. Delete engagement-scoped audit logs.
    4. Mark engagement as ARCHIVED (engagement record kept for reference).

    Returns the number of engagements cleaned up.
    """
    expired = await find_expired_engagements(session)

    count = 0
    for eng in expired:
        logger.info("Retention cleanup: processing engagement %s (%s)", eng.id, eng.name)

        # 1. Delete evidence fragments (children of evidence_items via CASCADE,
        #    but we do it explicitly to control ordering).
        evidence_ids_result = await session.execute(
            select(EvidenceItem.id).where(EvidenceItem.engagement_id == eng.id)
        )
        evidence_ids = [row[0] for row in evidence_ids_result]

        if evidence_ids:
            await session.execute(
                delete(EvidenceFragment).where(EvidenceFragment.evidence_id.in_(evidence_ids))
            )
            logger.info(
                "Retention cleanup: deleted fragments for %d evidence items in engagement %s",
                len(evidence_ids),
                eng.id,
            )

        # 2. Delete evidence items.
        await session.execute(
            delete(EvidenceItem).where(EvidenceItem.engagement_id == eng.id)
        )

        # 3. Delete engagement-scoped audit logs.
        await session.execute(
            delete(AuditLog).where(AuditLog.engagement_id == eng.id)
        )

        # 4. Archive the engagement record (data cleaned but record preserved).
        eng.status = EngagementStatus.ARCHIVED
        count += 1

    if count:
        await session.commit()
        logger.info("Retention cleanup: processed %d expired engagements", count)

    return count


async def cleanup_old_copilot_messages(session: AsyncSession, retention_days: int) -> int:
    """Delete copilot_messages older than retention_days.

    Copilot conversation history is ephemeral and should not accumulate
    indefinitely.  This function removes messages older than the configured
    retention window.

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(
        delete(CopilotMessage).where(CopilotMessage.created_at < cutoff)
    )
    deleted = result.rowcount or 0
    if deleted:
        await session.commit()
        logger.info("Retention cleanup: deleted %d copilot_messages older than %d days", deleted, retention_days)
    return deleted


async def cleanup_old_http_audit_events(session: AsyncSession, retention_days: int) -> int:
    """Delete http_audit_events older than retention_days.

    These events are platform-level and not scoped to an engagement.

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(
        delete(HttpAuditEvent).where(HttpAuditEvent.created_at < cutoff)
    )
    deleted = result.rowcount or 0
    if deleted:
        await session.commit()
        logger.info("Retention cleanup: deleted %d http_audit_events older than %d days", deleted, retention_days)
    return deleted


async def cleanup_old_task_mining_events(session: AsyncSession, retention_days: int) -> int:
    """Delete task_mining_events older than retention_days.

    Raw events are high-volume and should be purged after the configured
    retention period (default 90 days). Aggregated actions are kept longer.

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(
        delete(TaskMiningEvent).where(TaskMiningEvent.created_at < cutoff)
    )
    deleted = result.rowcount or 0
    if deleted:
        await session.commit()
        logger.info("Retention cleanup: deleted %d task_mining_events older than %d days", deleted, retention_days)
    return deleted


async def cleanup_old_task_mining_actions(session: AsyncSession, retention_days: int) -> int:
    """Delete task_mining_actions older than retention_days.

    Aggregated actions are retained longer than raw events (default 365 days).

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await session.execute(
        delete(TaskMiningAction).where(TaskMiningAction.created_at < cutoff)
    )
    deleted = result.rowcount or 0
    if deleted:
        await session.commit()
        logger.info("Retention cleanup: deleted %d task_mining_actions older than %d days", deleted, retention_days)
    return deleted


async def cleanup_expired_pii_quarantine(session: AsyncSession) -> int:
    """Auto-delete quarantined PII events past their expiry.

    Quarantined events with status PENDING_REVIEW that have passed
    their auto_delete_at timestamp are permanently deleted.

    Returns the number of rows deleted.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        delete(PIIQuarantine).where(
            PIIQuarantine.status == QuarantineStatus.PENDING_REVIEW,
            PIIQuarantine.auto_delete_at <= now,
        )
    )
    deleted = result.rowcount or 0
    if deleted:
        await session.commit()
        logger.info("Retention cleanup: auto-deleted %d expired PII quarantine items", deleted)
    return deleted
