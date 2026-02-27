"""BDD tests for Story #334: CanonicalActivityEvent Schema and Event Spine Builder.

Scenario 1: Multi-Source Canonicalization
Scenario 2: Deduplication with Confidence Retention
Scenario 3: Chronological Event Spine Assembly
Scenario 4: Unmapped Activity Handling
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import Engagement, User, UserRole
from src.core.models.canonical_event import CanonicalActivityEvent, EventMappingStatus
from src.semantic.event_spine import EventSpineBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_app(mock_session: AsyncMock) -> Any:
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Scenario 1: Multi-Source Canonicalization
# ---------------------------------------------------------------------------


class TestMultiSourceCanonicalization:
    """Events from 3 source systems normalize to canonical format."""

    def test_canonicalize_with_direct_fields(self) -> None:
        """Source events with canonical field names pass through correctly."""
        builder = EventSpineBuilder()
        raw_events = [
            {
                "case_id": "CASE-001",
                "activity_name": "Loan Application",
                "timestamp_utc": datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
                "confidence_score": 0.85,
            },
        ]
        result = builder.canonicalize(raw_events, "system_a")
        assert len(result) == 1
        assert result[0]["case_id"] == "CASE-001"
        assert result[0]["activity_name"] == "Loan Application"
        assert result[0]["source_system"] == "system_a"
        assert result[0]["confidence_score"] == 0.85
        assert result[0]["mapping_status"] == "mapped"

    def test_canonicalize_with_mapping_rules(self) -> None:
        """Source events with custom field names are mapped via rules."""
        builder = EventSpineBuilder(
            mapping_rules={
                "celonis": {
                    "CaseKey": "case_id",
                    "ActivityType": "activity_name",
                    "EventTime": "timestamp_utc",
                    "Score": "confidence_score",
                },
            }
        )
        raw_events = [
            {
                "CaseKey": "CASE-002",
                "ActivityType": "Document Review",
                "EventTime": datetime(2025, 2, 1, 14, 30, tzinfo=UTC),
                "Score": 0.92,
            },
        ]
        result = builder.canonicalize(raw_events, "celonis")
        assert result[0]["case_id"] == "CASE-002"
        assert result[0]["activity_name"] == "Document Review"
        assert result[0]["source_system"] == "celonis"
        assert result[0]["confidence_score"] == 0.92

    def test_canonicalize_three_sources_preserves_source(self) -> None:
        """Events from 3 sources all have source_system preserved."""
        builder = EventSpineBuilder()
        events_a = builder.canonicalize(
            [{"case_id": "C1", "activity_name": "A", "timestamp_utc": datetime(2025, 1, 1, tzinfo=UTC)}],
            "system_a",
        )
        events_b = builder.canonicalize(
            [{"case_id": "C1", "activity_name": "B", "timestamp_utc": datetime(2025, 1, 2, tzinfo=UTC)}],
            "system_b",
        )
        events_c = builder.canonicalize(
            [{"case_id": "C1", "activity_name": "C", "timestamp_utc": datetime(2025, 1, 3, tzinfo=UTC)}],
            "system_c",
        )
        all_events = events_a + events_b + events_c
        sources = {e["source_system"] for e in all_events}
        assert sources == {"system_a", "system_b", "system_c"}


# ---------------------------------------------------------------------------
# Scenario 2: Deduplication with Confidence Retention
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Duplicate events merged, highest confidence retained."""

    def test_duplicate_retains_highest_confidence(self) -> None:
        """Same activity within tolerance → keep highest confidence."""
        builder = EventSpineBuilder(dedup_tolerance_seconds=120)
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        events = [
            {
                "case_id": "CASE-001",
                "activity_name": "Review",
                "timestamp_utc": ts,
                "source_system": "sys_a",
                "confidence_score": 0.7,
            },
            {
                "case_id": "CASE-001",
                "activity_name": "Review",
                "timestamp_utc": ts + timedelta(seconds=30),
                "source_system": "sys_b",
                "confidence_score": 0.9,
            },
        ]
        result = builder.deduplicate(events)
        assert len(result) == 1
        assert result[0]["confidence_score"] == 0.9
        assert result[0]["source_system"] == "sys_b"

    def test_non_duplicate_different_activity(self) -> None:
        """Different activities at same timestamp are not duplicates."""
        builder = EventSpineBuilder(dedup_tolerance_seconds=120)
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        events = [
            {"case_id": "C1", "activity_name": "A", "timestamp_utc": ts, "confidence_score": 0.8},
            {"case_id": "C1", "activity_name": "B", "timestamp_utc": ts, "confidence_score": 0.7},
        ]
        result = builder.deduplicate(events)
        assert len(result) == 2

    def test_non_duplicate_outside_tolerance(self) -> None:
        """Same activity outside tolerance window → not duplicates."""
        builder = EventSpineBuilder(dedup_tolerance_seconds=60)
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        events = [
            {"case_id": "C1", "activity_name": "A", "timestamp_utc": ts, "confidence_score": 0.5},
            {
                "case_id": "C1",
                "activity_name": "A",
                "timestamp_utc": ts + timedelta(seconds=120),
                "confidence_score": 0.9,
            },
        ]
        result = builder.deduplicate(events)
        assert len(result) == 2

    def test_empty_events_dedup(self) -> None:
        """Empty list returns empty."""
        builder = EventSpineBuilder()
        assert builder.deduplicate([]) == []


# ---------------------------------------------------------------------------
# Scenario 3: Chronological Event Spine Assembly
# ---------------------------------------------------------------------------


class TestEventSpineAssembly:
    """build_spine returns deduplicated, chronologically ordered events."""

    def test_spine_orders_by_timestamp(self) -> None:
        """Events from multiple sources sorted by timestamp_utc."""
        builder = EventSpineBuilder()
        base = datetime(2025, 1, 1, tzinfo=UTC)
        events = [
            {"case_id": "C1", "activity_name": "C", "timestamp_utc": base + timedelta(hours=3), "confidence_score": 0.8},
            {"case_id": "C1", "activity_name": "A", "timestamp_utc": base + timedelta(hours=1), "confidence_score": 0.9},
            {"case_id": "C1", "activity_name": "B", "timestamp_utc": base + timedelta(hours=2), "confidence_score": 0.7},
        ]
        spine = builder.build_spine(events)
        assert len(spine) == 3
        assert spine[0]["activity_name"] == "A"
        assert spine[1]["activity_name"] == "B"
        assert spine[2]["activity_name"] == "C"

    def test_spine_deduplicates_during_build(self) -> None:
        """build_spine includes deduplication step."""
        builder = EventSpineBuilder(dedup_tolerance_seconds=60)
        ts = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        events = [
            {"case_id": "C1", "activity_name": "A", "timestamp_utc": ts, "confidence_score": 0.5},
            {"case_id": "C1", "activity_name": "A", "timestamp_utc": ts + timedelta(seconds=10), "confidence_score": 0.9},
            {"case_id": "C1", "activity_name": "B", "timestamp_utc": ts + timedelta(hours=1), "confidence_score": 0.8},
        ]
        spine = builder.build_spine(events)
        assert len(spine) == 2
        assert spine[0]["activity_name"] == "A"
        assert spine[0]["confidence_score"] == 0.9
        assert spine[1]["activity_name"] == "B"


# ---------------------------------------------------------------------------
# Scenario 4: Unmapped Activity Handling
# ---------------------------------------------------------------------------


class TestUnmappedActivityHandling:
    """Events with unknown activity names flagged as unmapped."""

    def test_unmapped_activities_flagged(self) -> None:
        """Activities not in known set get mapping_status=unmapped."""
        builder = EventSpineBuilder()
        events = [
            {"activity_name": "Known Activity", "mapping_status": "mapped"},
            {"activity_name": "Mystery Step", "mapping_status": "mapped"},
        ]
        known = {"Known Activity"}
        result = builder.check_unmapped(events, known)
        assert result[0]["mapping_status"] == "mapped"
        assert result[1]["mapping_status"] == "unmapped"

    def test_all_mapped_when_known(self) -> None:
        """All events remain mapped when all activities are known."""
        builder = EventSpineBuilder()
        events = [
            {"activity_name": "A", "mapping_status": "mapped"},
            {"activity_name": "B", "mapping_status": "mapped"},
        ]
        known = {"A", "B"}
        result = builder.check_unmapped(events, known)
        assert all(e["mapping_status"] == "mapped" for e in result)

    def test_unmapped_events_not_dropped(self) -> None:
        """Unmapped events remain in the output (not silently dropped)."""
        builder = EventSpineBuilder()
        events = [
            {"activity_name": "Unknown1", "mapping_status": "mapped"},
            {"activity_name": "Unknown2", "mapping_status": "mapped"},
        ]
        known: set[str] = set()
        result = builder.check_unmapped(events, known)
        assert len(result) == 2  # Both still present
        assert all(e["mapping_status"] == "unmapped" for e in result)


# ---------------------------------------------------------------------------
# API Route Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_event_spine_returns_ordered_events() -> None:
    """GET /cases/{case_id}/event-spine returns events ordered by timestamp."""
    session = AsyncMock()

    ts1 = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
    ts2 = datetime(2025, 1, 1, 11, 0, tzinfo=UTC)

    evt1 = _make_plain_mock(
        id=uuid.uuid4(),
        case_id="CASE-001",
        activity_name="Step A",
        timestamp_utc=ts1,
        source_system="sys_a",
        performer_role_ref=None,
        confidence_score=0.9,
        brightness="bright",
        mapping_status="mapped",
        process_element_id=None,
    )
    evt2 = _make_plain_mock(
        id=uuid.uuid4(),
        case_id="CASE-001",
        activity_name="Step B",
        timestamp_utc=ts2,
        source_system="sys_b",
        performer_role_ref="analyst",
        confidence_score=0.7,
        brightness="dim",
        mapping_status="mapped",
        process_element_id=None,
    )

    # Mock engagement existence check
    eng = MagicMock(spec=Engagement)
    eng.id = ENGAGEMENT_ID
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    # Mock count query
    count_result = MagicMock()
    count_result.scalar.return_value = 2

    # Mock spine query
    spine_result = MagicMock()
    spine_result.scalars.return_value.all.return_value = [evt1, evt2]

    session.execute = AsyncMock(side_effect=[eng_result, count_result, spine_result])
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/cases/CASE-001/event-spine?engagement_id={ENGAGEMENT_ID}"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "CASE-001"
    assert data["total_events"] == 2
    assert data["events"][0]["activity_name"] == "Step A"
    assert data["events"][1]["activity_name"] == "Step B"


@pytest.mark.asyncio
async def test_list_cases_endpoint() -> None:
    """GET /engagements/{id}/cases returns distinct case IDs."""
    session = AsyncMock()
    eng = MagicMock(spec=Engagement)
    eng.id = ENGAGEMENT_ID

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = eng

    cases_result = MagicMock()
    cases_result.all.return_value = [("CASE-001",), ("CASE-002",)]

    session.execute = AsyncMock(side_effect=[eng_result, cases_result])
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/cases")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert "CASE-001" in data["cases"]


@pytest.mark.asyncio
async def test_engagement_not_found_cases() -> None:
    """GET /engagements/{id}/cases returns 404 for unknown engagement."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/engagements/{uuid.uuid4()}/cases")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


def test_canonical_event_model_fields() -> None:
    """CanonicalActivityEvent has required fields."""
    assert hasattr(CanonicalActivityEvent, "case_id")
    assert hasattr(CanonicalActivityEvent, "activity_name")
    assert hasattr(CanonicalActivityEvent, "timestamp_utc")
    assert hasattr(CanonicalActivityEvent, "source_system")
    assert hasattr(CanonicalActivityEvent, "confidence_score")
    assert hasattr(CanonicalActivityEvent, "mapping_status")


def test_event_mapping_status_enum() -> None:
    """EventMappingStatus has mapped and unmapped values."""
    assert EventMappingStatus.MAPPED == "mapped"
    assert EventMappingStatus.UNMAPPED == "unmapped"
    assert len(EventMappingStatus) == 2
