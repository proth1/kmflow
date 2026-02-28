"""Tests for AssistedLinker: probabilistic case correlation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.taskmining.correlation.assisted import (
    CONFIDENCE_THRESHOLD,
    AssistedLinker,
    _combined_score,
    _role_match_score,
    _system_match_score,
    _time_proximity_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)


def _make_event(
    timestamp_utc: datetime | None = None,
    performer_role_ref: str | None = None,
    source_system: str = "taskmining",
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    event = MagicMock(spec=CanonicalActivityEvent)
    event.id = uuid.uuid4()
    event.engagement_id = engagement_id or uuid.uuid4()
    event.timestamp_utc = timestamp_utc or BASE_TS
    event.performer_role_ref = performer_role_ref
    event.source_system = source_system
    event.case_id = "unlinked"
    event.activity_name = "Review Document"
    return event


def _make_link(case_id: str, event_id: uuid.UUID) -> MagicMock:
    link = MagicMock(spec=CaseLinkEdge)
    link.case_id = case_id
    link.event_id = event_id
    link.method = "deterministic"
    return link


# ---------------------------------------------------------------------------
# Unit tests: scoring helpers
# ---------------------------------------------------------------------------


class TestTimeScoringHelper:
    def test_within_window_high_score(self) -> None:
        event_ts = BASE_TS
        case_timestamps = [BASE_TS + timedelta(minutes=5)]
        score = _time_proximity_score(event_ts, case_timestamps, window_minutes=30)
        assert score >= 0.5

    def test_beyond_double_window_zero(self) -> None:
        event_ts = BASE_TS
        case_timestamps = [BASE_TS + timedelta(minutes=120)]
        score = _time_proximity_score(event_ts, case_timestamps, window_minutes=30)
        assert score == 0.0

    def test_no_case_timestamps_zero(self) -> None:
        score = _time_proximity_score(BASE_TS, [], window_minutes=30)
        assert score == 0.0


class TestRoleMatchHelper:
    def test_matching_role(self) -> None:
        assert _role_match_score("analyst", {"analyst", "manager"}) == 1.0

    def test_non_matching_role(self) -> None:
        assert _role_match_score("consultant", {"analyst"}) == 0.0

    def test_null_role(self) -> None:
        assert _role_match_score(None, {"analyst"}) == 0.0

    def test_empty_case_roles(self) -> None:
        assert _role_match_score("analyst", set()) == 0.0


class TestSystemMatchHelper:
    def test_matching_system(self) -> None:
        assert _system_match_score("sap", {"sap", "taskmining"}) == 1.0

    def test_non_matching_system(self) -> None:
        assert _system_match_score("salesforce", {"sap"}) == 0.0

    def test_empty_systems(self) -> None:
        assert _system_match_score("taskmining", set()) == 0.0


class TestCombinedScore:
    def test_all_ones(self) -> None:
        score = _combined_score(1.0, 1.0, 1.0)
        assert abs(score - 1.0) < 0.001

    def test_all_zeros(self) -> None:
        score = _combined_score(0.0, 0.0, 0.0)
        assert score == 0.0

    def test_weights_add_to_one(self) -> None:
        """Weights (0.5 + 0.3 + 0.2) sum to 1.0, so max score is 1.0."""
        score = _combined_score(1.0, 1.0, 1.0)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# Integration tests: link_probabilistic
# ---------------------------------------------------------------------------


class TestAssistedLinker:
    def setup_method(self) -> None:
        self.engagement_id = uuid.uuid4()
        self.linker = AssistedLinker(confidence_threshold=CONFIDENCE_THRESHOLD)

    def _mock_session_with_det_links(
        self,
        case_id: str,
        event_ts: datetime,
        role: str | None,
        source_system: str,
    ) -> AsyncMock:
        """Build a mock session that returns a feature index from one det link."""
        session = AsyncMock()

        # First execute call: _build_case_feature_index
        linked_event = MagicMock(spec=CanonicalActivityEvent)
        linked_event.id = uuid.uuid4()
        linked_event.timestamp_utc = event_ts
        linked_event.performer_role_ref = role
        linked_event.source_system = source_system

        link = MagicMock(spec=CaseLinkEdge)
        link.case_id = case_id

        mock_result = MagicMock()
        mock_result.all.return_value = [(link, linked_event)]
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()

        return session

    @pytest.mark.asyncio
    async def test_link_probabilistic_time_proximity(self) -> None:
        """Event close in time to a known case is linked."""
        case_id = "CASE-999"
        event_ts = BASE_TS + timedelta(minutes=10)

        session = self._mock_session_with_det_links(
            case_id=case_id,
            event_ts=BASE_TS,
            role=None,
            source_system="other_system",
        )

        unlinked_event = _make_event(
            timestamp_utc=event_ts,
            engagement_id=self.engagement_id,
        )

        edges = await self.linker.link_probabilistic(
            session, self.engagement_id, [unlinked_event], time_window_minutes=30
        )

        # Time proximity should yield a score above threshold (0.4)
        assert len(edges) == 1
        assert edges[0].case_id == case_id
        assert edges[0].method == "assisted"
        assert edges[0].confidence >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_link_probabilistic_role_alignment(self) -> None:
        """Event with matching role gets role_match boost."""
        case_id = "INC-1111"
        role = "analyst"

        session = self._mock_session_with_det_links(
            case_id=case_id,
            event_ts=BASE_TS,
            role=role,
            source_system="taskmining",
        )

        unlinked_event = _make_event(
            timestamp_utc=BASE_TS + timedelta(minutes=5),
            performer_role_ref=role,
            source_system="taskmining",
            engagement_id=self.engagement_id,
        )

        edges = await self.linker.link_probabilistic(
            session, self.engagement_id, [unlinked_event], time_window_minutes=30
        )

        assert len(edges) == 1
        explainability = edges[0].explainability
        assert explainability["role_match"] == 1.0
        assert explainability["system_match"] == 1.0

    @pytest.mark.asyncio
    async def test_explainability_vector(self) -> None:
        """Explainability dict contains all four required keys."""
        case_id = "PROJ-50"

        session = self._mock_session_with_det_links(
            case_id=case_id,
            event_ts=BASE_TS,
            role="manager",
            source_system="sap",
        )

        unlinked_event = _make_event(
            timestamp_utc=BASE_TS + timedelta(minutes=2),
            performer_role_ref="manager",
            source_system="sap",
            engagement_id=self.engagement_id,
        )

        edges = await self.linker.link_probabilistic(
            session, self.engagement_id, [unlinked_event], time_window_minutes=30
        )

        assert len(edges) == 1
        expl = edges[0].explainability
        for key in ("time_proximity", "role_match", "system_match", "combined"):
            assert key in expl, f"Missing explainability key: {key}"

    @pytest.mark.asyncio
    async def test_below_threshold_no_link(self) -> None:
        """Event with combined score below threshold is not linked."""
        case_id = "CASE-000"

        # Put the known case event far in the future and different role/system
        session = self._mock_session_with_det_links(
            case_id=case_id,
            event_ts=BASE_TS + timedelta(hours=10),
            role="cfo",
            source_system="erp",
        )

        unlinked_event = _make_event(
            timestamp_utc=BASE_TS,
            performer_role_ref="analyst",
            source_system="taskmining",
            engagement_id=self.engagement_id,
        )

        edges = await self.linker.link_probabilistic(
            session, self.engagement_id, [unlinked_event], time_window_minutes=30
        )

        assert edges == []

    @pytest.mark.asyncio
    async def test_no_known_cases_returns_empty(self) -> None:
        """Returns empty list when no deterministic links exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        session.add = MagicMock()

        event = _make_event(engagement_id=self.engagement_id)
        edges = await self.linker.link_probabilistic(session, self.engagement_id, [event])

        assert edges == []
