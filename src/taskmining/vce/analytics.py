"""VCE analytics: aggregated statistics for visual context events.

All queries are scoped by engagement_id for multi-tenant isolation.
Functions return plain dicts for direct serialisation by API routes.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import VisualContextEvent

logger = logging.getLogger(__name__)


async def get_vce_distribution(
    session: AsyncSession,
    engagement_id: UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> dict[str, Any]:
    """Return distribution of screen_state_class values.

    Args:
        session: Async database session.
        engagement_id: Engagement to filter by.
        period_start: Optional lower bound (inclusive) on VCE timestamp.
        period_end: Optional upper bound (inclusive) on VCE timestamp.

    Returns:
        Dict with "distributions" list of {screen_state_class, count, percentage}.
    """
    query = (
        select(
            VisualContextEvent.screen_state_class,
            func.count(VisualContextEvent.id).label("count"),
        )
        .where(VisualContextEvent.engagement_id == engagement_id)
        .group_by(VisualContextEvent.screen_state_class)
        .order_by(func.count(VisualContextEvent.id).desc())
    )
    if period_start is not None:
        query = query.where(VisualContextEvent.timestamp >= period_start)
    if period_end is not None:
        query = query.where(VisualContextEvent.timestamp <= period_end)

    result = await session.execute(query)
    rows = result.all()

    total = sum(row.count for row in rows)
    distributions = [
        {
            "screen_state_class": row.screen_state_class,
            "count": row.count,
            "percentage": round(row.count / total * 100, 2) if total > 0 else 0.0,
        }
        for row in rows
    ]
    return {"distributions": distributions, "total": total}


async def get_trigger_summary(
    session: AsyncSession,
    engagement_id: UUID,
) -> dict[str, Any]:
    """Return trigger_reason distribution with avg confidence per trigger type.

    Args:
        session: Async database session.
        engagement_id: Engagement to filter by.

    Returns:
        Dict with "triggers" list of {trigger_reason, count, avg_confidence}.
    """
    query = (
        select(
            VisualContextEvent.trigger_reason,
            func.count(VisualContextEvent.id).label("count"),
            func.avg(VisualContextEvent.confidence).label("avg_confidence"),
        )
        .where(VisualContextEvent.engagement_id == engagement_id)
        .group_by(VisualContextEvent.trigger_reason)
        .order_by(func.count(VisualContextEvent.id).desc())
    )

    result = await session.execute(query)
    rows = result.all()

    triggers = [
        {
            "trigger_reason": row.trigger_reason,
            "count": row.count,
            "avg_confidence": round(float(row.avg_confidence), 4) if row.avg_confidence is not None else None,
        }
        for row in rows
    ]
    return {"triggers": triggers}


async def get_vce_timeline(
    session: AsyncSession,
    engagement_id: UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return chronological VCE events for timeline visualisation.

    Args:
        session: Async database session.
        engagement_id: Engagement to filter by.
        limit: Maximum number of events to return (most recent first).

    Returns:
        List of VCE event summary dicts ordered by timestamp descending.
    """
    query = (
        select(VisualContextEvent)
        .where(VisualContextEvent.engagement_id == engagement_id)
        .order_by(VisualContextEvent.timestamp.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    events = result.scalars().all()

    return [
        {
            "id": str(vce.id),
            "timestamp": vce.timestamp.isoformat(),
            "screen_state_class": vce.screen_state_class,
            "trigger_reason": vce.trigger_reason,
            "confidence": vce.confidence,
            "application_name": vce.application_name,
            "dwell_ms": vce.dwell_ms,
            "session_id": str(vce.session_id) if vce.session_id else None,
        }
        for vce in events
    ]


async def get_dwell_analysis(
    session: AsyncSession,
    engagement_id: UUID,
) -> dict[str, Any]:
    """Return dwell time statistics per application and screen state class.

    Computes avg, median, and p95 dwell times from raw records.

    Args:
        session: Async database session.
        engagement_id: Engagement to filter by.

    Returns:
        Dict with "per_app" and "per_class" lists of dwell statistics.
    """
    query = (
        select(
            VisualContextEvent.application_name,
            VisualContextEvent.screen_state_class,
            VisualContextEvent.dwell_ms,
        )
        .where(VisualContextEvent.engagement_id == engagement_id)
        .order_by(VisualContextEvent.application_name, VisualContextEvent.screen_state_class)
    )
    result = await session.execute(query)
    rows = result.all()

    # Group dwell_ms by app and by screen_state_class
    app_dwells: dict[str, list[int]] = {}
    class_dwells: dict[str, list[int]] = {}

    for row in rows:
        app_dwells.setdefault(row.application_name, []).append(row.dwell_ms)
        class_dwells.setdefault(row.screen_state_class, []).append(row.dwell_ms)

    def _stats(dwells: list[int]) -> dict[str, float | None]:
        if not dwells:
            return {"avg": None, "median": None, "p95": None}
        sorted_d = sorted(dwells)
        n = len(sorted_d)
        p95_idx = max(0, int(n * 0.95) - 1)
        return {
            "avg": round(statistics.mean(sorted_d), 2),
            "median": round(statistics.median(sorted_d), 2),
            "p95": float(sorted_d[p95_idx]),
            "count": n,
        }

    per_app = [
        {"application_name": app, **_stats(dwells)}
        for app, dwells in sorted(app_dwells.items())
    ]
    per_class = [
        {"screen_state_class": cls, **_stats(dwells)}
        for cls, dwells in sorted(class_dwells.items())
    ]

    return {"per_app": per_app, "per_class": per_class}
