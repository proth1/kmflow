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
    """aggregate task type raises NotImplementedError (stub pending Epic #206)."""

    @pytest.mark.asyncio
    async def test_aggregate_raises_not_implemented(self) -> None:
        task = {"task_type": "aggregate"}
        with pytest.raises(NotImplementedError, match="aggregate"):
            await process_task(task)


# ---------------------------------------------------------------------------
# materialize task type
# ---------------------------------------------------------------------------


class TestProcessTaskMaterialize:
    """materialize task type raises NotImplementedError."""

    @pytest.mark.asyncio
    async def test_materialize_raises_not_implemented(self) -> None:
        task = {"task_type": "materialize"}
        with pytest.raises(NotImplementedError, match="materialize"):
            await process_task(task)


# ---------------------------------------------------------------------------
# unknown task type
# ---------------------------------------------------------------------------


class TestProcessTaskUnknown:
    """Unknown task types raise NotImplementedError."""

    @pytest.mark.asyncio
    async def test_unknown_type_raises_not_implemented(self) -> None:
        task = {"task_type": "nonexistent_type"}
        with pytest.raises(NotImplementedError, match="nonexistent_type"):
            await process_task(task)

    @pytest.mark.asyncio
    async def test_missing_task_type_raises_not_implemented(self) -> None:
        task: dict = {}
        with pytest.raises(NotImplementedError):
            await process_task(task)

    @pytest.mark.asyncio
    async def test_empty_string_task_type_raises_not_implemented(self) -> None:
        task = {"task_type": ""}
        with pytest.raises(NotImplementedError):
            await process_task(task)


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
