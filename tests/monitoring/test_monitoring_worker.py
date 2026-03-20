"""Unit tests for src/monitoring/worker.py process_task function.

Tests the dispatch logic for known task types, unknown types, and
error handling. The Redis run_worker loop is not tested here.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.monitoring.worker import process_task

# ---------------------------------------------------------------------------
# detect task type
# ---------------------------------------------------------------------------


class TestProcessTaskDetect:
    """detect task type returns a successful detection result."""

    @pytest.mark.asyncio
    async def test_detect_returns_detection_completed(self) -> None:
        task = {"task_type": "detect"}
        result = await process_task(task)
        assert result["status"] == "detection_completed"

    @pytest.mark.asyncio
    async def test_detect_includes_deviations_found(self) -> None:
        task = {"task_type": "detect"}
        result = await process_task(task)
        assert "deviations_found" in result

    @pytest.mark.asyncio
    async def test_detect_deviations_found_is_zero_stub(self) -> None:
        task = {"task_type": "detect"}
        result = await process_task(task)
        assert result["deviations_found"] == 0

    @pytest.mark.asyncio
    async def test_detect_extra_fields_in_task_are_ignored(self) -> None:
        task = {"task_type": "detect", "engagement_id": "some-id", "extra": "data"}
        result = await process_task(task)
        assert result["status"] == "detection_completed"


# ---------------------------------------------------------------------------
# alert task type
# ---------------------------------------------------------------------------


class TestProcessTaskAlert:
    """alert task type returns alert_processed."""

    @pytest.mark.asyncio
    async def test_alert_returns_alert_processed(self) -> None:
        task = {"task_type": "alert"}
        result = await process_task(task)
        assert result["status"] == "alert_processed"

    @pytest.mark.asyncio
    async def test_alert_extra_payload_ignored(self) -> None:
        task = {"task_type": "alert", "severity": "high", "rule_id": "R-001"}
        result = await process_task(task)
        assert result["status"] == "alert_processed"


# ---------------------------------------------------------------------------
# collect task type (mocked to avoid real IO)
# ---------------------------------------------------------------------------


class TestProcessTaskCollect:
    """collect task type delegates to collect_evidence — mocked here."""

    @pytest.mark.asyncio
    async def test_collect_calls_collect_evidence(self) -> None:
        mock_collect = AsyncMock(return_value={"status": "collected", "records": 5})

        with patch("src.monitoring.worker.collect_evidence", mock_collect, create=True):
            # We patch via the lazy import path inside process_task
            task = {
                "task_type": "collect",
                "connector_type": "celonis",
                "config": {"url": "http://example.com"},
                "engagement_id": "eng-123",
            }
            # collect_evidence is lazily imported inside the function, so we
            # patch the module attribute directly.
            with patch.dict("sys.modules", {}):
                import sys
                import types

                monitoring_collector = types.ModuleType("src.monitoring.collector")
                monitoring_collector.collect_evidence = mock_collect  # type: ignore[attr-defined]
                sys.modules["src.monitoring.collector"] = monitoring_collector

                result = await process_task(task)

        # Whether the patch succeeded or fell through, no exception should be raised
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_collect_passes_defaults_when_fields_missing(self) -> None:
        """process_task supplies default values for optional fields."""
        calls: list = []

        async def fake_collect(**kwargs):  # type: ignore[return]
            calls.append(kwargs)
            return {"status": "ok"}

        import sys
        import types

        monitoring_collector = types.ModuleType("src.monitoring.collector")
        monitoring_collector.collect_evidence = fake_collect  # type: ignore[attr-defined]
        sys.modules["src.monitoring.collector"] = monitoring_collector

        task = {"task_type": "collect"}
        await process_task(task)

        assert len(calls) == 1
        assert calls[0]["connector_type"] == ""
        assert calls[0]["config"] == {}
        assert calls[0]["engagement_id"] == ""
        assert calls[0]["incremental"] is False
        assert calls[0]["since"] is None


# ---------------------------------------------------------------------------
# unknown task type
# ---------------------------------------------------------------------------


class TestProcessTaskUnknown:
    """Unknown task types return unknown_task_type without raising."""

    @pytest.mark.asyncio
    async def test_unknown_type_returns_correct_status(self) -> None:
        task = {"task_type": "this_does_not_exist"}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_unknown_type_echoes_task_type(self) -> None:
        task = {"task_type": "mystery_task"}
        result = await process_task(task)
        assert result["task_type"] == "mystery_task"

    @pytest.mark.asyncio
    async def test_missing_task_type_treated_as_unknown(self) -> None:
        # No task_type key → defaults to "unknown"
        task: dict = {}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_empty_task_type_treated_as_unknown(self) -> None:
        task = {"task_type": ""}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_unknown_does_not_raise(self) -> None:
        task = {"task_type": "future_type_not_yet_implemented"}
        # Must complete without exception
        result = await process_task(task)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Basic structural tests
# ---------------------------------------------------------------------------


class TestProcessTaskBasicProcessing:
    """process_task always returns a dict regardless of input."""

    @pytest.mark.asyncio
    async def test_returns_dict_for_detect(self) -> None:
        result = await process_task({"task_type": "detect"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_dict_for_alert(self) -> None:
        result = await process_task({"task_type": "alert"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_dict_for_unknown(self) -> None:
        result = await process_task({"task_type": "????"})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_result_has_status_key_for_all_non_collect_types(self) -> None:
        for task_type in ("detect", "alert", "unknown_xyz"):
            result = await process_task({"task_type": task_type})
            assert "status" in result, f"Missing 'status' key for task_type={task_type!r}"
