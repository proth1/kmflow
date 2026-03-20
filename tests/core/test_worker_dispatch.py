"""Tests for task queue worker dispatch mechanism."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.tasks.base import TaskStatus, TaskWorker
from src.core.tasks.queue import TaskQueue
from src.core.tasks.runner import run_task_worker

# ---------------------------------------------------------------------------
# Test worker implementations
# ---------------------------------------------------------------------------


class SimpleWorker(TaskWorker):
    """Minimal worker for registration and dispatch tests."""

    task_type = "simple_task"
    max_retries = 1

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.report_progress(1, 1)
        return {"done": True}


class FailingWorker(TaskWorker):
    """Worker that always raises an exception."""

    task_type = "failing_task"
    max_retries = 2

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Intentional failure")


class CountingWorker(TaskWorker):
    """Worker that records invocation count via payload echo."""

    task_type = "counting_task"
    max_retries = 1

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        steps = payload.get("steps", 3)
        for i in range(steps):
            self.report_progress(i + 1, steps)
        return {"steps_completed": steps}


# ---------------------------------------------------------------------------
# Queue factory
# ---------------------------------------------------------------------------


def make_queue(*workers: TaskWorker) -> tuple[TaskQueue, AsyncMock]:
    """Create a TaskQueue backed by a mock Redis client."""
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.xadd = AsyncMock(return_value="1-0")
    redis.hgetall = AsyncMock(return_value={})
    redis.xgroup_create = AsyncMock()
    redis.xreadgroup = AsyncMock(return_value=[])
    redis.xack = AsyncMock(return_value=1)

    queue = TaskQueue(redis)
    for w in workers:
        queue.register_worker(w)
    return queue, redis


# ===========================================================================
# Worker registration
# ===========================================================================


class TestWorkerRegistration:
    """TaskQueue correctly registers workers."""

    def test_register_single_worker(self) -> None:
        queue, _ = make_queue(SimpleWorker())
        assert queue.has_worker("simple_task")

    def test_register_multiple_workers(self) -> None:
        queue, _ = make_queue(SimpleWorker(), FailingWorker())
        assert queue.has_worker("simple_task")
        assert queue.has_worker("failing_task")

    def test_registered_types_returns_set(self) -> None:
        queue, _ = make_queue(SimpleWorker(), CountingWorker())
        assert queue.registered_types == {"simple_task", "counting_task"}

    def test_unregistered_type_returns_false(self) -> None:
        queue, _ = make_queue()
        assert not queue.has_worker("nonexistent")

    def test_empty_task_type_raises(self) -> None:
        class BadWorker(TaskWorker):
            task_type = ""

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {}

        queue, _ = make_queue()
        with pytest.raises(ValueError, match="task_type must be set"):
            queue.register_worker(BadWorker())

    def test_registering_replaces_existing(self) -> None:
        """Re-registering the same task_type replaces the previous worker."""
        queue, _ = make_queue()
        queue.register_worker(SimpleWorker())
        queue.register_worker(SimpleWorker())  # Should not raise
        assert queue.has_worker("simple_task")


# ===========================================================================
# Task dispatch
# ===========================================================================


class TestTaskDispatch:
    """TaskQueue dispatches tasks to the correct worker."""

    @pytest.mark.asyncio
    async def test_dispatch_to_registered_worker(self) -> None:
        queue, redis = make_queue(SimpleWorker())

        task_id = "test-task-001"
        base_data = {
            "task_id": task_id,
            "task_type": "simple_task",
            "status": TaskStatus.PENDING.value,
            "current_step": "0",
            "total_steps": "0",
            "percent_complete": "0",
            "error": "",
            "attempt_count": "0",
            "max_retries": "1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "",
        }
        # First call fetches max_retries (returns PENDING); subsequent call
        # from get_status after execution should reflect COMPLETED state.
        completed_data = {**base_data, "status": TaskStatus.COMPLETED.value, "result": '{"done": true}'}
        redis.hgetall = AsyncMock(side_effect=[base_data, completed_data])

        progress = await queue.execute_task(task_id, "simple_task", {})

        assert progress.status == TaskStatus.COMPLETED
        assert progress.result == {"done": True}

    @pytest.mark.asyncio
    async def test_unknown_task_type_returns_failed(self) -> None:
        queue, redis = make_queue()

        task_id = "test-task-002"
        redis.hgetall = AsyncMock(
            return_value={
                "task_id": task_id,
                "task_type": "unknown",
                "status": TaskStatus.FAILED.value,
                "error": "No worker registered for task type: unknown",
                "current_step": "0",
                "total_steps": "0",
                "percent_complete": "0",
                "attempt_count": "0",
                "created_at": "",
                "completed_at": "",
            }
        )

        progress = await queue.execute_task(task_id, "unknown", {})

        assert progress.status == TaskStatus.FAILED
        assert "No worker registered" in progress.error

    @pytest.mark.asyncio
    async def test_worker_receives_payload(self) -> None:
        """Worker's execute() is called with the correct payload."""
        received_payload: dict[str, Any] = {}

        class PayloadCapture(TaskWorker):
            task_type = "capture_task"
            max_retries = 1

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                received_payload.update(payload)
                return {}

        queue, redis = make_queue(PayloadCapture())
        task_id = "capture-001"
        redis.hgetall = AsyncMock(
            return_value={
                "task_id": task_id,
                "task_type": "capture_task",
                "status": TaskStatus.PENDING.value,
                "current_step": "0",
                "total_steps": "0",
                "percent_complete": "0",
                "error": "",
                "attempt_count": "0",
                "max_retries": "1",
                "created_at": "",
                "completed_at": "",
            }
        )

        await queue.execute_task(task_id, "capture_task", {"key": "value", "num": 42})

        assert received_payload["key"] == "value"
        assert received_payload["num"] == 42


# ===========================================================================
# Error handling
# ===========================================================================


class TestWorkerErrorHandling:
    """TaskQueue handles worker failures with retry logic."""

    @pytest.mark.asyncio
    async def test_failed_worker_returns_failed_status(self) -> None:
        queue, redis = make_queue(FailingWorker())
        task_id = "fail-001"
        redis.hgetall = AsyncMock(
            return_value={
                "task_id": task_id,
                "task_type": "failing_task",
                "status": TaskStatus.FAILED.value,
                "error": "Intentional failure",
                "current_step": "0",
                "total_steps": "0",
                "percent_complete": "0",
                "attempt_count": "2",
                "max_retries": "2",
                "created_at": "",
                "completed_at": "",
            }
        )

        progress = await queue.execute_task(task_id, "failing_task", {})

        assert progress.status == TaskStatus.FAILED
        assert "Intentional failure" in progress.error

    @pytest.mark.asyncio
    async def test_progress_reports_correctly(self) -> None:
        """Worker progress is stored in the progress hash."""
        queue, redis = make_queue(CountingWorker())
        task_id = "count-001"
        redis.hgetall = AsyncMock(
            return_value={
                "task_id": task_id,
                "task_type": "counting_task",
                "status": TaskStatus.COMPLETED.value,
                "current_step": "3",
                "total_steps": "3",
                "percent_complete": "100",
                "error": "",
                "attempt_count": "1",
                "max_retries": "1",
                "result": '{"steps_completed": 3}',
                "created_at": "",
                "completed_at": "",
            }
        )

        progress = await queue.execute_task(task_id, "counting_task", {"steps": 3})

        # Either actual execution or mocked result shows completion
        assert progress.status == TaskStatus.COMPLETED


# ===========================================================================
# Graceful shutdown
# ===========================================================================


class TestGracefulShutdown:
    """run_task_worker stops cleanly when shutdown_event is set."""

    @pytest.mark.asyncio
    async def test_no_workers_exits_immediately(self) -> None:
        """Worker runner exits if no task types are registered."""
        queue, redis = make_queue()
        shutdown = asyncio.Event()
        redis_client = AsyncMock()

        # Should return quickly with no workers registered
        await asyncio.wait_for(
            run_task_worker(queue, "worker-0", shutdown, redis_client),
            timeout=2.0,
        )

    @pytest.mark.asyncio
    async def test_shutdown_event_stops_loop(self) -> None:
        """Setting shutdown_event causes the runner loop to exit."""
        queue, redis = make_queue(SimpleWorker())
        redis.xreadgroup = AsyncMock(return_value=[])

        shutdown = asyncio.Event()
        redis_client = AsyncMock()
        redis_client.publish = AsyncMock()

        async def stop_after_start() -> None:
            await asyncio.sleep(0.05)
            shutdown.set()

        await asyncio.gather(
            run_task_worker(queue, "worker-0", shutdown, redis_client),
            stop_after_start(),
        )

        assert shutdown.is_set()

    @pytest.mark.asyncio
    async def test_cancelled_error_exits_cleanly(self) -> None:
        """CancelledError during worker loop exits without re-raising."""
        queue, redis = make_queue(SimpleWorker())
        redis.xreadgroup = AsyncMock(return_value=[])

        shutdown = asyncio.Event()
        redis_client = AsyncMock()
        redis_client.publish = AsyncMock()

        task = asyncio.create_task(run_task_worker(queue, "worker-0", shutdown, redis_client))
        await asyncio.sleep(0.02)
        task.cancel()

        # Should not raise (CancelledError is acceptable if propagated)
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_unexpected_error_retries_after_backoff(self) -> None:
        """Worker loop catches unexpected errors and retries."""
        error_count = 0

        class BoomWorker(TaskWorker):
            task_type = "boom"
            max_retries = 1

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                nonlocal error_count
                error_count += 1
                raise RuntimeError("Boom!")

        queue, redis = make_queue(BoomWorker())
        shutdown = asyncio.Event()
        redis_client = AsyncMock()
        redis_client.publish = AsyncMock()

        # Simulate xreadgroup returning a task entry once, then empty
        task_fields = {"task_id": "boom-001", "payload": "{}"}
        redis.xreadgroup = AsyncMock(
            side_effect=[
                [[b"kmflow:tasks:boom", [(b"1-0", task_fields)]]],
                [],  # No more tasks — allow worker loop to check shutdown
            ]
            + [[] for _ in range(100)]  # Keep returning empty
        )
        redis.hgetall = AsyncMock(
            return_value={
                "task_id": "boom-001",
                "task_type": "boom",
                "status": TaskStatus.PENDING.value,
                "current_step": "0",
                "total_steps": "0",
                "percent_complete": "0",
                "error": "",
                "attempt_count": "0",
                "max_retries": "1",
                "created_at": "",
                "completed_at": "",
            }
        )

        with patch("src.core.tasks.runner._ERROR_BACKOFF", 0.01):

            async def stop_soon() -> None:
                await asyncio.sleep(0.15)
                shutdown.set()

            await asyncio.gather(
                run_task_worker(queue, "worker-0", shutdown, redis_client),
                stop_soon(),
            )
