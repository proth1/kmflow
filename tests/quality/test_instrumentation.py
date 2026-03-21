"""Tests for the @pipeline_stage instrumentation decorator.

Covers timing, input/output count capture, error recording, and
engagement_id/evidence_item_id extraction for both sync and async functions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.quality.instrumentation import (
    PipelineStageEvent,
    _input_count,
    _output_count,
    pipeline_stage,
)

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestOutputCount:
    def test_list_result_returns_length(self) -> None:
        assert _output_count(["a", "b", "c"]) == 3

    def test_empty_list_returns_zero(self) -> None:
        assert _output_count([]) == 0

    def test_truthy_non_list_returns_one(self) -> None:
        assert _output_count("some string") == 1
        assert _output_count(42) == 1
        assert _output_count({"key": "val"}) == 1

    def test_falsy_non_list_returns_zero(self) -> None:
        assert _output_count(None) == 0
        assert _output_count(0) == 0
        assert _output_count("") == 0


class TestInputCount:
    def test_first_list_arg_returns_its_length(self) -> None:
        import inspect

        def fn(items: list, name: str) -> None:  # noqa: ARG001
            pass

        sig = inspect.signature(fn)
        bound = sig.bind(["x", "y", "z"], "bob")
        bound.apply_defaults()
        assert _input_count(bound) == 3

    def test_no_list_arg_returns_one(self) -> None:
        import inspect

        def fn(name: str, value: int) -> None:  # noqa: ARG001
            pass

        sig = inspect.signature(fn)
        bound = sig.bind("alice", 5)
        bound.apply_defaults()
        assert _input_count(bound) == 1


# ---------------------------------------------------------------------------
# Integration tests for @pipeline_stage decorator
# ---------------------------------------------------------------------------


def _make_mock_collector() -> MagicMock:
    """Return a MagicMock that mimics MetricsCollector.instance()."""
    collector = MagicMock()
    collector.record = MagicMock()
    return collector


class TestPipelineStageSync:
    def test_sync_function_records_event(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("test_stage")
        def my_fn(items: list[str]) -> list[str]:
            return items

        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            result = my_fn(["a", "b"])

        assert result == ["a", "b"]
        collector.record.assert_called_once()
        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.stage == "test_stage"
        assert event.input_count == 2
        assert event.output_count == 2
        assert event.error_count == 0
        assert event.error_type is None
        assert event.duration_ms >= 0.0

    def test_sync_function_captures_engagement_id_from_default_param(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("stage_with_eid")
        def my_fn(engagement_id: str) -> str:
            return "ok"

        eid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn(engagement_id=eid)

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.engagement_id == eid

    def test_sync_function_captures_engagement_id_from_named_param(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("named_stage", engagement_id_param="eng_id")
        def my_fn(eng_id: str) -> str:
            return "ok"

        eid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn(eng_id=eid)

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.engagement_id == eid

    def test_sync_function_captures_evidence_item_id(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("stage_with_evid")
        def my_fn(evidence_item_id: str) -> None:
            return None

        evid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn(evidence_item_id=evid)

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.evidence_item_id == evid

    def test_sync_error_is_recorded_and_reraised(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("error_stage")
        def bad_fn() -> None:
            raise ValueError("boom")

        with (
            patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector),
            pytest.raises(ValueError, match="boom"),
        ):
            bad_fn()

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.error_count == 1
        assert event.error_type == "ValueError"
        assert event.output_count == 0  # error path → 0

    def test_sync_truthy_non_list_result_gives_output_count_one(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("single_result_stage")
        def my_fn() -> str:
            return "result"

        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn()

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.output_count == 1

    def test_sync_none_result_gives_output_count_zero(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("none_stage")
        def my_fn() -> None:
            return None

        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn()

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.output_count == 0

    def test_event_has_started_at_timestamp(self) -> None:
        from datetime import UTC

        collector = _make_mock_collector()

        @pipeline_stage("ts_stage")
        def my_fn() -> str:
            return "x"

        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            my_fn()

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.started_at.tzinfo is not None
        assert event.started_at.tzinfo == UTC


@pytest.mark.asyncio
class TestPipelineStageAsync:
    async def test_async_function_records_event(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("async_stage")
        async def my_async_fn(items: list[str]) -> list[str]:
            return items

        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            result = await my_async_fn(["x", "y", "z"])

        assert result == ["x", "y", "z"]
        collector.record.assert_called_once()
        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.stage == "async_stage"
        assert event.input_count == 3
        assert event.output_count == 3
        assert event.error_count == 0

    async def test_async_error_is_recorded_and_reraised(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("async_error_stage")
        async def bad_async_fn() -> None:
            raise RuntimeError("async boom")

        with (
            patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector),
            pytest.raises(RuntimeError, match="async boom"),
        ):
            await bad_async_fn()

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.error_count == 1
        assert event.error_type == "RuntimeError"
        assert event.output_count == 0

    async def test_async_engagement_id_extracted(self) -> None:
        collector = _make_mock_collector()

        @pipeline_stage("async_eid_stage")
        async def my_fn(engagement_id: str, data: list[str]) -> list[str]:
            return data

        eid = "11111111-2222-3333-4444-555555555555"
        with patch("src.quality.metrics_collector.MetricsCollector.instance", return_value=collector):
            await my_fn(engagement_id=eid, data=["a"])

        event: PipelineStageEvent = collector.record.call_args[0][0]
        assert event.engagement_id == eid
        assert event.input_count == 1  # len(["a"])
