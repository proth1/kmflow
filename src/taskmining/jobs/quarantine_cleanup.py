"""PII quarantine auto-cleanup: deletes expired quarantine records.

Runs on a configurable interval (default: every 60 minutes) and removes
records whose auto_delete_at timestamp has passed. Writes an audit log
entry on each run with the count of deleted records and duration.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import PIIQuarantine, QuarantineStatus

logger = logging.getLogger(__name__)

# Statuses eligible for auto-cleanup
_CLEANUP_STATUSES = {
    QuarantineStatus.PENDING_REVIEW,
    QuarantineStatus.DELETED,
    QuarantineStatus.RELEASED,
}


async def run_quarantine_cleanup(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict:
    """Delete expired quarantine records and return a summary.

    Args:
        session: Database session.
        now: Override for current time (useful for testing). Defaults to UTC now.

    Returns:
        Dict with keys: rows_deleted, run_at, duration_ms
    """
    if now is None:
        now = datetime.now(timezone.utc)

    start = time.monotonic()

    # Atomic delete — no TOCTOU gap between count and delete
    delete_stmt = (
        delete(PIIQuarantine)
        .where(
            PIIQuarantine.auto_delete_at < now,
            PIIQuarantine.status.in_(_CLEANUP_STATUSES),
        )
    )
    result = await session.execute(delete_stmt)
    rows_deleted = result.rowcount or 0

    if rows_deleted > 0:
        await session.flush()

    elapsed_ms = (time.monotonic() - start) * 1000

    summary = {
        "rows_deleted": rows_deleted,
        "run_at": now.isoformat(),
        "duration_ms": round(elapsed_ms, 2),
    }

    if rows_deleted > 0:
        logger.info(
            "Quarantine cleanup: deleted %d expired records in %.1fms",
            rows_deleted,
            elapsed_ms,
        )
    else:
        logger.debug("Quarantine cleanup: no expired records found")

    return summary


async def count_expired(session: AsyncSession, now: datetime | None = None) -> int:
    """Count expired quarantine records without deleting them."""
    if now is None:
        now = datetime.now(timezone.utc)
    stmt = (
        select(func.count())
        .select_from(PIIQuarantine)
        .where(
            PIIQuarantine.auto_delete_at < now,
            PIIQuarantine.status.in_(_CLEANUP_STATUSES),
        )
    )
    result = await session.execute(stmt)
    return result.scalar() or 0
