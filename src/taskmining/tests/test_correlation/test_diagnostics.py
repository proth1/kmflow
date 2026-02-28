"""Tests for CorrelationDiagnostics: daily quality reporting."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.taskmining.correlation.diagnostics import CorrelationDiagnostics
from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TARGET_DATE = date(2026, 1, 15)
ENGAGEMENT_ID = uuid.uuid4()


def _make_event(
    event_id: uuid.UUID | None = None,
    hour: int = 10,
) -> MagicMock:
    event = MagicMock(spec=CanonicalActivityEvent)
    event.id = event_id or uuid.uuid4()
    event.timestamp_utc = datetime(2026, 1, 15, hour, 0, tzinfo=timezone.utc)
    return event


def _make_link(
    event_id: uuid.UUID,
    case_id: str = "CASE-1",
    method: str = "deterministic",
    confidence: float = 1.0,
) -> MagicMock:
    link = MagicMock(spec=CaseLinkEdge)
    link.event_id = event_id
    link.case_id = case_id
    link.method = method
    link.confidence = confidence
    return link


def _build_session(
    total_count: int,
    links: list[MagicMock],
    all_events: list[MagicMock],
) -> AsyncMock:
    """Build a mock session for diagnostics queries.

    Three execute() calls in sequence:
    1. count of total events
    2. all link edges for the day
    3. all events for the day (for hourly breakdown)
    """
    session = AsyncMock()

    # Call 1: total event count
    count_result = MagicMock()
    count_result.scalar_one.return_value = total_count

    # Call 2: link edges
    link_result = MagicMock()
    link_result.scalars.return_value.all.return_value = links

    # Call 3: all events (for hourly uncertainty)
    events_result = MagicMock()
    events_result.scalars.return_value.all.return_value = all_events

    session.execute = AsyncMock(side_effect=[count_result, link_result, events_result])
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCorrelationDiagnostics:
    def setup_method(self) -> None:
        self.diag = CorrelationDiagnostics()

    @pytest.mark.asyncio
    async def test_daily_report_generation(self) -> None:
        """Report fields are populated correctly for a day with mixed links."""
        event_a_id = uuid.uuid4()
        event_b_id = uuid.uuid4()

        events = [_make_event(event_a_id, hour=10), _make_event(event_b_id, hour=10)]
        links = [
            _make_link(event_a_id, "CASE-1", "deterministic", 1.0),
        ]

        session = _build_session(
            total_count=2, links=links, all_events=events
        )

        report = await self.diag.generate_daily_report(session, ENGAGEMENT_ID, TARGET_DATE)

        assert report["date"] == TARGET_DATE.isoformat()
        assert report["engagement_id"] == str(ENGAGEMENT_ID)
        assert report["total_events"] == 2
        assert report["linked_events"] == 1
        assert report["linked_pct"] == 50.0
        assert isinstance(report["confidence_distribution"], dict)
        assert isinstance(report["non_linkage_causes"], list)
        assert isinstance(report["uncertainty_items"], list)

    @pytest.mark.asyncio
    async def test_empty_day_returns_zeroes(self) -> None:
        """When there are no events, report returns zeros and empty lists."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        session = AsyncMock()
        session.execute = AsyncMock(return_value=count_result)

        report = await self.diag.generate_daily_report(session, ENGAGEMENT_ID, TARGET_DATE)

        assert report["total_events"] == 0
        assert report["linked_events"] == 0
        assert report["linked_pct"] == 0.0
        assert report["uncertainty_items"] == []
        assert report["non_linkage_causes"] == []

    @pytest.mark.asyncio
    async def test_uncertainty_items_generated(self) -> None:
        """Hours where >=50% events are unlinked produce uncertainty items."""
        event_a_id = uuid.uuid4()
        event_b_id = uuid.uuid4()

        # Both events in hour 14, neither linked to a real case
        events = [_make_event(event_a_id, hour=14), _make_event(event_b_id, hour=14)]
        links = []  # no links at all

        session = _build_session(total_count=2, links=links, all_events=events)

        report = await self.diag.generate_daily_report(session, ENGAGEMENT_ID, TARGET_DATE)

        assert len(report["uncertainty_items"]) >= 1
        item = report["uncertainty_items"][0]
        assert item["hour"] == 14
        assert item["unlinked_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_role_aggregate_links_in_non_linkage_causes(self) -> None:
        """Role-aggregate edges appear in non_linkage_causes, not in linked_events."""
        event_a_id = uuid.uuid4()
        events = [_make_event(event_a_id, hour=9)]
        role_link = _make_link(
            event_a_id,
            case_id=f"{ROLE_AGGREGATE_PREFIX}:analyst",
            method="role_aggregate",
            confidence=0.0,
        )

        session = _build_session(total_count=1, links=[role_link], all_events=events)

        report = await self.diag.generate_daily_report(session, ENGAGEMENT_ID, TARGET_DATE)

        # Role aggregate does NOT count as a linked event
        assert report["linked_events"] == 0
        causes = report["non_linkage_causes"]
        cause_names = [c["cause"] for c in causes]
        assert "role_aggregate_only" in cause_names

    @pytest.mark.asyncio
    async def test_confidence_distribution_bucketing(self) -> None:
        """Links are correctly placed in high, medium_high, medium, low buckets."""
        e_ids = [uuid.uuid4() for _ in range(4)]
        events = [_make_event(eid, hour=10) for eid in e_ids]
        links = [
            _make_link(e_ids[0], "A", "deterministic", 0.95),
            _make_link(e_ids[1], "B", "assisted", 0.75),
            _make_link(e_ids[2], "C", "assisted", 0.55),
            _make_link(e_ids[3], "D", "assisted", 0.35),
        ]

        session = _build_session(total_count=4, links=links, all_events=events)

        report = await self.diag.generate_daily_report(session, ENGAGEMENT_ID, TARGET_DATE)

        dist = report["confidence_distribution"]
        assert dist["high"] >= 1
        assert dist["medium_high"] >= 1
        assert dist["medium"] >= 1
        assert dist["low"] >= 1
