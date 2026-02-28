"""Tests for the switching sequence service (src/taskmining/switching.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.taskmining import DesktopEventType, SwitchingTrace
from src.taskmining.switching import (
    IDLE_GAP_SECONDS,
    assemble_switching_traces,
    compute_friction_score,
    compute_transition_matrix,
    detect_ping_pong,
    get_friction_analysis,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    app_name: str,
    timestamp: datetime,
    engagement_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> MagicMock:
    evt = MagicMock()
    evt.id = uuid.uuid4()
    evt.engagement_id = engagement_id or uuid.uuid4()
    evt.session_id = session_id or uuid.uuid4()
    evt.event_type = DesktopEventType.APP_SWITCH
    evt.application_name = app_name
    evt.timestamp = timestamp
    return evt


def _make_trace(
    engagement_id: uuid.UUID | None = None,
    trace_sequence: list[str] | None = None,
    friction_score: float = 0.1,
    is_ping_pong: bool = False,
    ping_pong_count: int | None = None,
    total_duration_ms: int = 60_000,
    app_count: int = 2,
) -> MagicMock:
    t = MagicMock(spec=SwitchingTrace)
    t.id = uuid.uuid4()
    t.engagement_id = engagement_id or uuid.uuid4()
    t.session_id = uuid.uuid4()
    t.trace_sequence = trace_sequence or ["Excel", "Chrome"]
    t.friction_score = friction_score
    t.is_ping_pong = is_ping_pong
    t.ping_pong_count = ping_pong_count
    t.total_duration_ms = total_duration_ms
    t.app_count = app_count
    t.started_at = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    t.ended_at = datetime(2026, 2, 1, 9, 1, tzinfo=UTC)
    t.created_at = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    return t


# ---------------------------------------------------------------------------
# detect_ping_pong
# ---------------------------------------------------------------------------


class TestDetectPingPong:
    def test_detects_basic_ping_pong(self) -> None:
        seq = ["Excel", "Chrome", "Excel", "Chrome", "Excel", "Chrome"]
        is_pp, count = detect_ping_pong(seq, threshold=3)
        assert is_pp is True
        assert count >= 3

    def test_below_threshold_not_detected(self) -> None:
        seq = ["Excel", "Chrome", "Excel"]
        is_pp, count = detect_ping_pong(seq, threshold=3)
        assert is_pp is False
        assert count == 0

    def test_no_ping_pong_all_different(self) -> None:
        seq = ["Excel", "Word", "Outlook", "Chrome", "Slack"]
        is_pp, count = detect_ping_pong(seq, threshold=3)
        assert is_pp is False
        assert count == 0

    def test_empty_sequence_returns_false(self) -> None:
        is_pp, count = detect_ping_pong([], threshold=3)
        assert is_pp is False
        assert count == 0

    def test_single_element_returns_false(self) -> None:
        is_pp, count = detect_ping_pong(["Excel"], threshold=3)
        assert is_pp is False
        assert count == 0

    def test_custom_threshold(self) -> None:
        seq = ["A", "B", "A", "B"]
        is_pp, count = detect_ping_pong(seq, threshold=2)
        assert is_pp is True
        assert count >= 2


# ---------------------------------------------------------------------------
# compute_friction_score
# ---------------------------------------------------------------------------


class TestComputeFrictionScore:
    def test_zero_friction_long_dwells(self) -> None:
        # Long dwell times, no ping-pong, few apps → low friction
        score = compute_friction_score(
            trace_sequence=["Excel", "Chrome"],
            dwell_durations=[60_000, 60_000],
            total_duration_ms=120_000,
            is_ping_pong=False,
            ping_pong_count=0,
        )
        assert 0.0 <= score < 0.3

    def test_high_friction_rapid_ping_pong(self) -> None:
        # Rapid switches + ping-pong → high friction
        score = compute_friction_score(
            trace_sequence=["A", "B", "A", "B", "A", "B"],
            dwell_durations=[1_000, 1_000, 1_000, 1_000, 1_000, 0],
            total_duration_ms=5_000,
            is_ping_pong=True,
            ping_pong_count=5,
        )
        assert score >= 0.5

    def test_score_clamped_to_one(self) -> None:
        score = compute_friction_score(
            trace_sequence=["A", "B"] * 10,
            dwell_durations=[100] * 20,
            total_duration_ms=2_000,
            is_ping_pong=True,
            ping_pong_count=15,
        )
        assert score <= 1.0

    def test_empty_sequence_returns_zero(self) -> None:
        score = compute_friction_score(
            trace_sequence=[],
            dwell_durations=[],
            total_duration_ms=0,
            is_ping_pong=False,
            ping_pong_count=0,
        )
        assert score == 0.0

    def test_score_is_float_in_range(self) -> None:
        score = compute_friction_score(
            trace_sequence=["A", "B", "C"],
            dwell_durations=[3_000, 3_000, 0],
            total_duration_ms=6_000,
            is_ping_pong=False,
            ping_pong_count=0,
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# assemble_switching_traces
# ---------------------------------------------------------------------------


class TestAssembleSwitchingTraces:
    @pytest.mark.asyncio
    async def test_basic_trace_assembly(self) -> None:
        """Creates a single trace from consecutive APP_SWITCH events."""
        engagement_id = uuid.uuid4()
        session_id = uuid.uuid4()
        base_time = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
        events = [
            _make_event("Excel", base_time, engagement_id, session_id),
            _make_event("Chrome", base_time + timedelta(seconds=30), engagement_id, session_id),
            _make_event("Slack", base_time + timedelta(seconds=60), engagement_id, session_id),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = events
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        traces = await assemble_switching_traces(session, engagement_id)

        assert len(traces) == 1
        trace = traces[0]
        assert trace.app_count == 3
        assert "Excel" in trace.trace_sequence
        assert len(trace.trace_sequence) == 3

    @pytest.mark.asyncio
    async def test_idle_gap_breaks_trace(self) -> None:
        """Verifies that an idle gap > 5min creates two separate traces."""
        engagement_id = uuid.uuid4()
        session_id = uuid.uuid4()
        base_time = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
        gap = timedelta(seconds=IDLE_GAP_SECONDS + 60)  # 6 minutes

        events = [
            _make_event("Excel", base_time, engagement_id, session_id),
            _make_event("Chrome", base_time + timedelta(seconds=30), engagement_id, session_id),
            # Idle gap here
            _make_event("Word", base_time + timedelta(seconds=30) + gap, engagement_id, session_id),
            _make_event("Outlook", base_time + timedelta(seconds=60) + gap, engagement_id, session_id),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = events
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        traces = await assemble_switching_traces(session, engagement_id)

        assert len(traces) == 2
        assert "Excel" in traces[0].trace_sequence
        assert "Word" in traces[1].trace_sequence

    @pytest.mark.asyncio
    async def test_no_events_returns_empty(self) -> None:
        """Returns empty list when no APP_SWITCH events exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        traces = await assemble_switching_traces(session, uuid.uuid4())

        assert traces == []

    @pytest.mark.asyncio
    async def test_session_id_filter_applied(self) -> None:
        """Session filter is passed to DB query (verifies execute called)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        session_id = uuid.uuid4()
        await assemble_switching_traces(session, uuid.uuid4(), session_id=session_id)

        session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# compute_transition_matrix
# ---------------------------------------------------------------------------


class TestComputeTransitionMatrix:
    @pytest.mark.asyncio
    async def test_builds_matrix_from_events(self) -> None:
        """Verifies transition counts are correctly assembled."""
        engagement_id = uuid.uuid4()
        base_time = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
        events = [
            _make_event("Excel", base_time, engagement_id),
            _make_event("Chrome", base_time + timedelta(seconds=10), engagement_id),
            _make_event("Excel", base_time + timedelta(seconds=20), engagement_id),
            _make_event("Chrome", base_time + timedelta(seconds=30), engagement_id),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = events
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        period_start = base_time
        period_end = base_time + timedelta(minutes=5)

        matrix = await compute_transition_matrix(
            session=session,
            engagement_id=engagement_id,
            role_id=None,
            period_start=period_start,
            period_end=period_end,
        )

        assert matrix.total_transitions == 3
        assert matrix.unique_apps == 2
        assert "Excel" in matrix.matrix_data
        assert matrix.matrix_data["Excel"]["Chrome"] >= 1

    @pytest.mark.asyncio
    async def test_empty_events_creates_zero_matrix(self) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()

        base = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
        matrix = await compute_transition_matrix(
            session=session,
            engagement_id=uuid.uuid4(),
            role_id=None,
            period_start=base,
            period_end=base + timedelta(hours=1),
        )

        assert matrix.total_transitions == 0
        assert matrix.unique_apps == 0
        assert matrix.matrix_data == {}


# ---------------------------------------------------------------------------
# get_friction_analysis
# ---------------------------------------------------------------------------


class TestGetFrictionAnalysis:
    @pytest.mark.asyncio
    async def test_no_traces_returns_zeros(self) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_friction_analysis(session, uuid.uuid4())

        assert result["avg_friction_score"] == 0.0
        assert result["total_traces_analyzed"] == 0
        assert result["high_friction_traces"] == []
        assert result["top_ping_pong_pairs"] == []

    @pytest.mark.asyncio
    async def test_avg_friction_computed(self) -> None:
        engagement_id = uuid.uuid4()
        traces = [
            _make_trace(engagement_id=engagement_id, friction_score=0.2),
            _make_trace(engagement_id=engagement_id, friction_score=0.8),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = traces
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_friction_analysis(session, engagement_id)

        assert result["avg_friction_score"] == pytest.approx(0.5, abs=0.01)
        assert result["total_traces_analyzed"] == 2

    @pytest.mark.asyncio
    async def test_high_friction_traces_capped_at_five(self) -> None:
        engagement_id = uuid.uuid4()
        traces = [_make_trace(engagement_id=engagement_id, friction_score=float(i) / 10) for i in range(10)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = traces
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_friction_analysis(session, engagement_id)

        assert len(result["high_friction_traces"]) <= 5

    @pytest.mark.asyncio
    async def test_ping_pong_pairs_detected(self) -> None:
        engagement_id = uuid.uuid4()
        traces = [
            _make_trace(
                engagement_id=engagement_id,
                trace_sequence=["Excel", "Chrome", "Excel", "Chrome"],
                is_ping_pong=True,
                ping_pong_count=2,
            ),
            _make_trace(
                engagement_id=engagement_id,
                trace_sequence=["Excel", "Chrome", "Excel", "Chrome"],
                is_ping_pong=True,
                ping_pong_count=2,
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = traces
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_friction_analysis(session, engagement_id)

        assert len(result["top_ping_pong_pairs"]) >= 1
        pair_entry = result["top_ping_pong_pairs"][0]
        assert "Chrome" in pair_entry["pair"] or "Excel" in pair_entry["pair"]
        assert pair_entry["trace_count"] >= 1
