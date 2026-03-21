"""Tests for the MetricsCollector singleton.

Covers singleton pattern, buffer management (ring-buffer at capacity),
async flush to database, and get_stage_summary aggregation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.quality.instrumentation import PipelineStageEvent
from src.quality.metrics_collector import _MAX_BUFFER_SIZE, MetricsCollector


def _make_event(stage: str = "test_stage", engagement_id: str | None = None) -> PipelineStageEvent:
    return PipelineStageEvent(
        stage=stage,
        engagement_id=engagement_id,
        evidence_item_id=None,
        started_at=datetime.now(tz=UTC),
        duration_ms=12.5,
        input_count=3,
        output_count=3,
        error_count=0,
        error_type=None,
    )


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the MetricsCollector singleton between tests to prevent state leakage."""
    MetricsCollector._instance = None
    yield
    MetricsCollector._instance = None


class TestMetricsCollectorSingleton:
    def test_instance_returns_same_object(self) -> None:
        c1 = MetricsCollector.instance()
        c2 = MetricsCollector.instance()
        assert c1 is c2

    def test_instance_is_metrics_collector(self) -> None:
        assert isinstance(MetricsCollector.instance(), MetricsCollector)


class TestMetricsCollectorRecord:
    def test_record_adds_event_to_buffer(self) -> None:
        collector = MetricsCollector()
        event = _make_event()
        collector.record(event)
        assert len(collector._buffer) == 1
        assert collector._buffer[0] is event

    def test_record_multiple_events(self) -> None:
        collector = MetricsCollector()
        for i in range(5):
            collector.record(_make_event(stage=f"stage_{i}"))
        assert len(collector._buffer) == 5

    def test_buffer_at_capacity_drops_oldest(self) -> None:
        collector = MetricsCollector()
        # Fill buffer to max
        for i in range(_MAX_BUFFER_SIZE):
            collector.record(_make_event(stage=f"old_{i}"))
        assert len(collector._buffer) == _MAX_BUFFER_SIZE

        # Add one more — oldest (old_0) should be evicted
        new_event = _make_event(stage="new_event")
        collector.record(new_event)

        assert len(collector._buffer) == _MAX_BUFFER_SIZE
        assert collector._buffer[-1] is new_event
        assert collector._buffer[0].stage == "old_1"

    def test_buffer_does_not_exceed_max(self) -> None:
        collector = MetricsCollector()
        for i in range(_MAX_BUFFER_SIZE + 20):
            collector.record(_make_event(stage=f"evt_{i}"))
        assert len(collector._buffer) == _MAX_BUFFER_SIZE


@pytest.mark.asyncio
class TestMetricsCollectorFlush:
    async def test_flush_empty_buffer_returns_zero(self) -> None:
        collector = MetricsCollector()
        session = AsyncMock()
        result = await collector.flush(session)
        assert result == 0
        session.add_all.assert_not_called()
        session.flush.assert_not_called()

    async def test_flush_calls_add_all_and_session_flush(self) -> None:
        collector = MetricsCollector()
        eid = str(uuid.uuid4())
        for _ in range(3):
            collector.record(_make_event(engagement_id=eid))

        session = AsyncMock()
        session.add_all = MagicMock()  # add_all is synchronous in SQLAlchemy
        count = await collector.flush(session)

        assert count == 3
        session.add_all.assert_called_once()
        rows = session.add_all.call_args[0][0]
        assert len(rows) == 3
        session.flush.assert_called_once()

    async def test_flush_clears_buffer(self) -> None:
        collector = MetricsCollector()
        collector.record(_make_event())
        collector.record(_make_event())

        session = AsyncMock()
        session.add_all = MagicMock()
        await collector.flush(session)

        assert len(collector._buffer) == 0

    async def test_flush_second_call_returns_zero_when_no_new_events(self) -> None:
        collector = MetricsCollector()
        collector.record(_make_event())

        session = AsyncMock()
        session.add_all = MagicMock()
        await collector.flush(session)

        # Second flush with no new events
        count = await collector.flush(session)
        assert count == 0

    async def test_flush_invalid_uuid_engagement_id_is_handled(self) -> None:
        """Events with non-UUID engagement_id strings should not raise — UUID coercion silently sets None."""
        collector = MetricsCollector()
        event = _make_event(engagement_id="not-a-uuid")
        collector.record(event)

        session = AsyncMock()
        session.add_all = MagicMock()
        count = await collector.flush(session)
        assert count == 1
        row = session.add_all.call_args[0][0][0]
        assert row.engagement_id is None


@pytest.mark.asyncio
class TestMetricsCollectorGetStageSummary:
    async def test_get_stage_summary_returns_mapped_rows(self) -> None:
        engagement_id = uuid.uuid4()

        # Build fake row object that mimics SQLAlchemy row namedtuple
        mock_row = MagicMock()
        mock_row.stage = "ingest"
        mock_row.execution_count = 10
        mock_row.avg_duration_ms = 42.5
        mock_row.total_input = 100
        mock_row.total_output = 95
        mock_row.total_errors = 2

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        summaries = await MetricsCollector.get_stage_summary(session, engagement_id)

        assert len(summaries) == 1
        s = summaries[0]
        assert s["stage"] == "ingest"
        assert s["execution_count"] == 10
        assert s["avg_duration_ms"] == 42.5
        assert s["total_input"] == 100
        assert s["total_output"] == 95
        assert s["total_errors"] == 2

    async def test_get_stage_summary_empty_results(self) -> None:
        engagement_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        summaries = await MetricsCollector.get_stage_summary(session, engagement_id)
        assert summaries == []

    async def test_get_stage_summary_accepts_string_engagement_id(self) -> None:
        engagement_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        # Should not raise
        summaries = await MetricsCollector.get_stage_summary(session, engagement_id)
        assert isinstance(summaries, list)

    async def test_get_stage_summary_handles_none_aggregates(self) -> None:
        """None aggregate values from SQL should be coerced to 0."""
        engagement_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.stage = "parse"
        mock_row.execution_count = 1
        mock_row.avg_duration_ms = None
        mock_row.total_input = None
        mock_row.total_output = None
        mock_row.total_errors = None

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        summaries = await MetricsCollector.get_stage_summary(session, engagement_id)
        s = summaries[0]
        assert s["avg_duration_ms"] == 0.0
        assert s["total_input"] == 0
        assert s["total_output"] == 0
        assert s["total_errors"] == 0
