"""Correlation diagnostics: daily quality reporting for case linkage coverage.

Computes the percentage of endpoint time accounted for by case links,
confidence score distributions, and generates uncertainty items for time
blocks that remain unlinked.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX

logger = logging.getLogger(__name__)

# Confidence buckets for distribution reporting
_CONFIDENCE_BUCKETS = [
    (0.9, 1.0, "high"),
    (0.7, 0.9, "medium_high"),
    (0.4, 0.7, "medium"),
    (0.0, 0.4, "low"),
]


def _utc_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=UTC)
    return start, end


class CorrelationDiagnostics:
    """Generates daily correlation quality reports."""

    async def generate_daily_report(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
        target_date: date,
    ) -> dict:
        """Compute correlation quality metrics for a single day.

        Args:
            session: Async database session.
            engagement_id: Engagement to analyze.
            target_date: Calendar date to scope the report to.

        Returns:
            Dict with keys:
              date, engagement_id, total_events, linked_events, linked_pct,
              confidence_distribution, non_linkage_causes, uncertainty_items
        """
        start_ts, end_ts = _utc_day_bounds(target_date)

        # Total events for the day
        total_stmt = select(func.count(CanonicalActivityEvent.id)).where(
            CanonicalActivityEvent.engagement_id == engagement_id,
            CanonicalActivityEvent.timestamp_utc >= start_ts,
            CanonicalActivityEvent.timestamp_utc <= end_ts,
        )
        total_result = await session.execute(total_stmt)
        total_events: int = total_result.scalar_one() or 0

        if total_events == 0:
            return self._empty_report(engagement_id, target_date)

        # All links for the day's events (join on event timestamp)
        links_stmt = (
            select(CaseLinkEdge)
            .join(CanonicalActivityEvent, CaseLinkEdge.event_id == CanonicalActivityEvent.id)
            .where(
                CaseLinkEdge.engagement_id == engagement_id,
                CanonicalActivityEvent.timestamp_utc >= start_ts,
                CanonicalActivityEvent.timestamp_utc <= end_ts,
            )
        )
        links_result = await session.execute(links_stmt)
        all_links = list(links_result.scalars().all())

        # Partition into real case links and role aggregates
        real_links = [lk for lk in all_links if not lk.case_id.startswith(ROLE_AGGREGATE_PREFIX)]
        role_links = [lk for lk in all_links if lk.case_id.startswith(ROLE_AGGREGATE_PREFIX)]

        linked_event_ids = {lk.event_id for lk in real_links}
        linked_events = len(linked_event_ids)
        linked_pct = round(linked_events / total_events * 100, 2) if total_events else 0.0

        # Confidence distribution (only real links)
        confidence_distribution = self._build_confidence_distribution(real_links)

        # Non-linkage causes
        non_linkage_causes = self._build_non_linkage_causes(
            total_events=total_events,
            linked_events=linked_events,
            role_linked_events=len({lk.event_id for lk in role_links}),
        )

        # Uncertainty items: hourly blocks with low/no coverage
        uncertainty_items = await self._generate_uncertainty_items(
            session=session,
            engagement_id=engagement_id,
            start_ts=start_ts,
            end_ts=end_ts,
            linked_event_ids=linked_event_ids,
        )

        return {
            "date": target_date.isoformat(),
            "engagement_id": str(engagement_id),
            "total_events": total_events,
            "linked_events": linked_events,
            "linked_pct": linked_pct,
            "confidence_distribution": confidence_distribution,
            "non_linkage_causes": non_linkage_causes,
            "uncertainty_items": uncertainty_items,
        }

    def _build_confidence_distribution(self, links: list[CaseLinkEdge]) -> dict[str, int]:
        dist: dict[str, int] = {bucket: 0 for _, _, bucket in _CONFIDENCE_BUCKETS}
        for link in links:
            for low, high, label in _CONFIDENCE_BUCKETS:
                if low <= link.confidence <= high:
                    dist[label] += 1
                    break
        return dist

    def _build_non_linkage_causes(
        self,
        total_events: int,
        linked_events: int,
        role_linked_events: int,
    ) -> list[dict]:
        unlinked = total_events - linked_events - role_linked_events
        causes = []
        if role_linked_events > 0:
            causes.append(
                {
                    "cause": "role_aggregate_only",
                    "event_count": role_linked_events,
                    "description": "Events attributed to role cohort; no specific case match found.",
                }
            )
        if unlinked > 0:
            causes.append(
                {
                    "cause": "no_link",
                    "event_count": unlinked,
                    "description": "Events with no case link and no role association.",
                }
            )
        return causes

    async def _generate_uncertainty_items(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
        start_ts: datetime,
        end_ts: datetime,
        linked_event_ids: set[uuid.UUID],
    ) -> list[dict]:
        """Identify hourly blocks where most events are unlinked."""
        stmt = select(CanonicalActivityEvent).where(
            CanonicalActivityEvent.engagement_id == engagement_id,
            CanonicalActivityEvent.timestamp_utc >= start_ts,
            CanonicalActivityEvent.timestamp_utc <= end_ts,
        )
        result = await session.execute(stmt)
        all_events = list(result.scalars().all())

        # Group by hour
        hourly: dict[int, dict] = defaultdict(lambda: {"total": 0, "unlinked": 0})
        for event in all_events:
            hour = event.timestamp_utc.hour
            hourly[hour]["total"] += 1
            if event.id not in linked_event_ids:
                hourly[hour]["unlinked"] += 1

        uncertainty_items = []
        for hour in sorted(hourly):
            stats = hourly[hour]
            if stats["total"] == 0:
                continue
            unlinked_pct = stats["unlinked"] / stats["total"] * 100
            if unlinked_pct >= 50:
                uncertainty_items.append(
                    {
                        "hour": hour,
                        "total_events": stats["total"],
                        "unlinked_events": stats["unlinked"],
                        "unlinked_pct": round(unlinked_pct, 1),
                        "recommendation": "Review activities in this hour for manual case assignment.",
                    }
                )

        return uncertainty_items

    def _empty_report(self, engagement_id: uuid.UUID, target_date: date) -> dict:
        return {
            "date": target_date.isoformat(),
            "engagement_id": str(engagement_id),
            "total_events": 0,
            "linked_events": 0,
            "linked_pct": 0.0,
            "confidence_distribution": {label: 0 for _, _, label in _CONFIDENCE_BUCKETS},
            "non_linkage_causes": [],
            "uncertainty_items": [],
        }
