"""Unit tests for src/taskmining/worker.py process_task dispatch function.

Tests focus on the process_task coroutine and _handle_assemble_switching
without touching the Redis run_worker loop.
"""

from __future__ import annotations

import uuid

import pytest

from src.taskmining.worker import process_task

# ---------------------------------------------------------------------------
# aggregate task type
# ---------------------------------------------------------------------------


class TestProcessTaskAggregate:
    """aggregate task type returns not_implemented status with passthrough fields."""

    @pytest.mark.asyncio
    async def test_aggregate_returns_not_implemented(self) -> None:
        task = {"task_type": "aggregate"}
        result = await process_task(task)
        assert result["status"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_aggregate_passthrough_event_type(self) -> None:
        task = {"task_type": "aggregate", "event_type": "click"}
        result = await process_task(task)
        assert result["event_type"] == "click"

    @pytest.mark.asyncio
    async def test_aggregate_passthrough_session_id(self) -> None:
        session_id = str(uuid.uuid4())
        task = {"task_type": "aggregate", "session_id": session_id}
        result = await process_task(task)
        assert result["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_aggregate_passthrough_application_name(self) -> None:
        task = {"task_type": "aggregate", "application_name": "Excel"}
        result = await process_task(task)
        assert result["application_name"] == "Excel"

    @pytest.mark.asyncio
    async def test_aggregate_missing_optional_fields_are_none(self) -> None:
        task = {"task_type": "aggregate"}
        result = await process_task(task)
        assert result["event_type"] is None
        assert result["session_id"] is None
        assert result["application_name"] is None


# ---------------------------------------------------------------------------
# materialize task type
# ---------------------------------------------------------------------------


class TestProcessTaskMaterialize:
    """materialize task type returns not_implemented status."""

    @pytest.mark.asyncio
    async def test_materialize_returns_not_implemented(self) -> None:
        task = {"task_type": "materialize"}
        result = await process_task(task)
        assert result["status"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_materialize_extra_fields_ignored(self) -> None:
        task = {"task_type": "materialize", "some_extra_field": "value"}
        result = await process_task(task)
        assert result["status"] == "not_implemented"

    @pytest.mark.asyncio
    async def test_materialize_result_has_no_unexpected_error_key(self) -> None:
        task = {"task_type": "materialize"}
        result = await process_task(task)
        assert "error" not in result


# ---------------------------------------------------------------------------
# unknown task type
# ---------------------------------------------------------------------------


class TestProcessTaskUnknown:
    """Unknown task types return unknown_task_type status."""

    @pytest.mark.asyncio
    async def test_unknown_type_returns_unknown_status(self) -> None:
        task = {"task_type": "nonexistent_type"}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_unknown_type_echoes_task_type(self) -> None:
        task = {"task_type": "some_future_task"}
        result = await process_task(task)
        assert result["task_type"] == "some_future_task"

    @pytest.mark.asyncio
    async def test_missing_task_type_treated_as_unknown(self) -> None:
        # No task_type key → defaults to "unknown"
        task: dict = {}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"

    @pytest.mark.asyncio
    async def test_empty_string_task_type_is_unknown(self) -> None:
        task = {"task_type": ""}
        result = await process_task(task)
        assert result["status"] == "unknown_task_type"


# ---------------------------------------------------------------------------
# assemble_switching — missing engagement_id
# ---------------------------------------------------------------------------


class TestProcessTaskAssembleSwitchingMissingEngagementId:
    """assemble_switching without engagement_id must return an error."""

    @pytest.mark.asyncio
    async def test_missing_engagement_id_returns_error_status(self) -> None:
        task = {"task_type": "assemble_switching"}
        result = await process_task(task)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_engagement_id_has_detail(self) -> None:
        task = {"task_type": "assemble_switching"}
        result = await process_task(task)
        assert "detail" in result
        assert result["detail"] == "engagement_id required"

    @pytest.mark.asyncio
    async def test_none_engagement_id_returns_error(self) -> None:
        task = {"task_type": "assemble_switching", "engagement_id": None}
        result = await process_task(task)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_empty_engagement_id_returns_error(self) -> None:
        task = {"task_type": "assemble_switching", "engagement_id": ""}
        result = await process_task(task)
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# assemble_switching — invalid UUID
# ---------------------------------------------------------------------------


class TestProcessTaskAssembleSwitchingInvalidUuid:
    """assemble_switching with a non-UUID engagement_id must return an error."""

    @pytest.mark.asyncio
    async def test_invalid_engagement_id_uuid_returns_error(self) -> None:
        task = {"task_type": "assemble_switching", "engagement_id": "not-a-uuid"}
        result = await process_task(task)
        assert result["status"] == "error"
        assert result["detail"] == "invalid UUID"

    @pytest.mark.asyncio
    async def test_invalid_session_id_with_valid_engagement_returns_error(self) -> None:
        task = {
            "task_type": "assemble_switching",
            "engagement_id": str(uuid.uuid4()),
            "session_id": "not-a-uuid",
        }
        # The lazy imports will fail in a pure-unit test environment, but UUID
        # validation happens before the lazy imports, so the invalid session_id
        # causes an early error return without hitting the DB.
        result = await process_task(task)
        assert result["status"] == "error"
        assert result["detail"] == "invalid UUID"
