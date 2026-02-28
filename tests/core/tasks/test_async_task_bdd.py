"""BDD tests for async task architecture (Story #320).

Tests task enqueue, progress tracking, result retrieval, retry logic,
concurrency control, and consumer group processing.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from src.core.tasks.base import TaskStatus, TaskWorker
from src.core.tasks.queue import (
    PAYLOAD_PREFIX,
    PROGRESS_PREFIX,
    STREAM_PREFIX,
    TaskProgress,
    TaskQueue,
)

# -- Test workers -------------------------------------------------------------


class SuccessWorker(TaskWorker):
    """Worker that always succeeds."""

    task_type = "test_success"

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.report_progress(5, 10)
        self.report_progress(10, 10)
        return {"result": "ok", "engagement_id": payload.get("engagement_id")}


class FailWorker(TaskWorker):
    """Worker that always raises."""

    task_type = "test_fail"
    max_retries = 3

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("simulated failure")


class EventualSuccessWorker(TaskWorker):
    """Worker that fails twice then succeeds."""

    task_type = "test_eventual"
    max_retries = 3

    def __init__(self) -> None:
        super().__init__()
        self.attempt_count = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.attempt_count += 1
        if self.attempt_count < 3:
            raise RuntimeError(f"attempt {self.attempt_count} failed")
        self.report_progress(1, 1)
        return {"recovered": True}


class SlowWorker(TaskWorker):
    """Worker that takes configurable time."""

    task_type = "test_slow"

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        steps = payload.get("steps", 5)
        for i in range(1, steps + 1):
            self.report_progress(i, steps)
            await asyncio.sleep(0)  # yield control
        return {"completed": True, "steps": steps}


# -- Fake Redis for testing ---------------------------------------------------


class FakeRedis:
    """In-memory Redis mock supporting hset/hgetall/xadd/xreadgroup/xack."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._acked: dict[str, set[str]] = {}
        self._groups: dict[str, set[str]] = {}
        self._msg_counter = 0
        self._pending: dict[str, list[tuple[str, dict[str, str]]]] = {}

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        self._hashes[key].update(mapping)
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def xadd(
        self,
        stream: str,
        fields: dict[str, str],
        maxlen: int = 0,
        approximate: bool = False,
    ) -> str:
        self._msg_counter += 1
        msg_id = f"{self._msg_counter}-0"
        if stream not in self._streams:
            self._streams[stream] = []
        self._streams[stream].append((msg_id, fields))
        # Also add to pending for consumer group reads
        if stream not in self._pending:
            self._pending[stream] = []
        self._pending[stream].append((msg_id, fields))
        return msg_id

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 1,
        block: int = 0,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        result = []
        for stream_name, _last_id in streams.items():
            pending = self._pending.get(stream_name, [])
            if pending:
                entries = pending[:count]
                self._pending[stream_name] = pending[count:]
                result.append((stream_name, entries))
        return result

    async def xack(self, stream: str, group: str, *msg_ids: str) -> int:
        if stream not in self._acked:
            self._acked[stream] = set()
        self._acked[stream].update(msg_ids)
        return len(msg_ids)

    async def xgroup_create(
        self,
        stream: str,
        group: str,
        id: str = "0",
        mkstream: bool = False,
    ) -> bool:
        key = f"{stream}:{group}"
        if key in self._groups:
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self._groups[key] = set()
        return True

    async def ping(self) -> bool:
        return True


# -- Helpers ------------------------------------------------------------------


def make_queue() -> tuple[TaskQueue, FakeRedis]:
    """Create a TaskQueue with a FakeRedis backend."""
    redis = FakeRedis()
    queue = TaskQueue(redis)
    return queue, redis


# --- Scenario 1: Long-running operation returns task ID immediately ----------


class TestEnqueueReturnsTaskId:
    """Scenario 1: POST returns 202 with task_id."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_uuid_task_id(self) -> None:
        """Enqueue returns a UUID task ID."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {"engagement_id": "eng-1"})

        assert len(task_id) == 36  # UUID format
        assert "-" in task_id

    @pytest.mark.asyncio
    async def test_enqueue_creates_pending_status(self) -> None:
        """Newly enqueued task has PENDING status."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        progress = await queue.get_status(task_id)

        assert progress.status == TaskStatus.PENDING
        assert progress.task_id == task_id

    @pytest.mark.asyncio
    async def test_enqueue_writes_to_redis_stream(self) -> None:
        """Enqueue adds a message to the Redis Stream."""
        queue, redis = make_queue()
        queue.register_worker(SuccessWorker())

        await queue.enqueue("test_success", {"key": "value"})

        stream_key = f"{STREAM_PREFIX}:test_success"
        assert stream_key in redis._streams
        assert len(redis._streams[stream_key]) == 1

    @pytest.mark.asyncio
    async def test_enqueue_stores_progress_hash(self) -> None:
        """Enqueue creates a Redis hash with initial progress fields."""
        queue, redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})

        progress_key = f"{PROGRESS_PREFIX}:{task_id}"
        data = redis._hashes.get(progress_key, {})
        assert data["status"] == "PENDING"
        assert data["current_step"] == "0"
        assert data["total_steps"] == "0"
        assert data["created_at"] != ""

    @pytest.mark.asyncio
    async def test_enqueue_stores_payload(self) -> None:
        """Enqueue stores the payload for worker retrieval."""
        queue, redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {"x": 1})

        payload_key = f"{PAYLOAD_PREFIX}:{task_id}"
        data = redis._hashes.get(payload_key, {})
        assert json.loads(data["payload"]) == {"x": 1}


# --- Scenario 2: Task progress is trackable while running -------------------


class TestProgressTracking:
    """Scenario 2: GET /tasks/{id} returns progress."""

    @pytest.mark.asyncio
    async def test_progress_updated_during_execution(self) -> None:
        """Worker progress reports are visible via get_status."""
        queue, _redis = make_queue()
        worker = SuccessWorker()
        queue.register_worker(worker)

        task_id = await queue.enqueue("test_success", {"engagement_id": "eng-1"})
        await queue.execute_task(task_id, "test_success", {"engagement_id": "eng-1"})

        progress = await queue.get_status(task_id)
        assert progress.current_step == 10
        assert progress.total_steps == 10
        assert progress.percent_complete == 100

    @pytest.mark.asyncio
    async def test_partial_progress_visible(self) -> None:
        """Progress is visible during multi-step execution."""
        queue, _redis = make_queue()

        class PartialWorker(TaskWorker):
            task_type = "test_partial"

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                self.report_progress(3, 10)
                return {"done": True}

        worker = PartialWorker()
        queue.register_worker(worker)

        task_id = await queue.enqueue("test_partial", {})
        await queue.execute_task(task_id, "test_partial", {})

        progress = await queue.get_status(task_id)
        # Final progress reflects last report_progress call
        assert progress.current_step == 3
        assert progress.total_steps == 10
        assert progress.percent_complete == 30

    @pytest.mark.asyncio
    async def test_running_status_during_execution(self) -> None:
        """Task transitions to RUNNING during execution."""
        statuses: list[TaskStatus] = []
        queue, redis = make_queue()

        original_update = queue._update_progress

        async def capture_update(task_id: str, **kwargs: Any) -> None:
            if "status" in kwargs and kwargs["status"] is not None:
                statuses.append(kwargs["status"])
            await original_update(task_id, **kwargs)

        queue._update_progress = capture_update  # type: ignore[assignment]
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        await queue.execute_task(task_id, "test_success", {})

        assert TaskStatus.RUNNING in statuses
        assert TaskStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_task_type_in_progress(self) -> None:
        """Task type is included in progress response."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        progress = await queue.get_status(task_id)

        assert progress.task_type == "test_success"


# --- Scenario 3: Completed task result is retrievable -----------------------


class TestCompletedTaskResult:
    """Scenario 3: Completed tasks have full result payload."""

    @pytest.mark.asyncio
    async def test_completed_task_has_result(self) -> None:
        """Completed task includes the result payload."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {"engagement_id": "eng-1"})
        await queue.execute_task(task_id, "test_success", {"engagement_id": "eng-1"})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.COMPLETED
        assert progress.result["result"] == "ok"
        assert progress.result["engagement_id"] == "eng-1"

    @pytest.mark.asyncio
    async def test_completed_task_has_timestamp(self) -> None:
        """Completed task has a completed_at timestamp."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        await queue.execute_task(task_id, "test_success", {})

        progress = await queue.get_status(task_id)
        assert progress.completed_at != ""
        assert "T" in progress.completed_at  # ISO 8601

    @pytest.mark.asyncio
    async def test_completed_task_attempt_count_is_one(self) -> None:
        """Successful task on first attempt has attempt_count=1."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        await queue.execute_task(task_id, "test_success", {})

        progress = await queue.get_status(task_id)
        assert progress.attempt_count == 1


# --- Scenario 4: Failed task records error and retries ----------------------


class TestFailedTaskRetry:
    """Scenario 4: Failed tasks retry up to max_retries."""

    @pytest.mark.asyncio
    async def test_failed_task_after_retries(self) -> None:
        """Task is FAILED after exhausting all retries."""
        queue, _redis = make_queue()
        queue.register_worker(FailWorker())

        task_id = await queue.enqueue("test_fail", {}, max_retries=3)
        await queue.execute_task(task_id, "test_fail", {})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.FAILED
        assert progress.attempt_count == 3
        assert "simulated failure" in progress.error

    @pytest.mark.asyncio
    async def test_failed_task_has_completed_at(self) -> None:
        """Failed task has a completed_at timestamp."""
        queue, _redis = make_queue()
        queue.register_worker(FailWorker())

        task_id = await queue.enqueue("test_fail", {}, max_retries=1)
        await queue.execute_task(task_id, "test_fail", {})

        progress = await queue.get_status(task_id)
        assert progress.completed_at != ""

    @pytest.mark.asyncio
    async def test_eventual_success_after_retries(self) -> None:
        """Task that fails twice then succeeds completes on attempt 3."""
        queue, _redis = make_queue()
        worker = EventualSuccessWorker()
        queue.register_worker(worker)

        task_id = await queue.enqueue("test_eventual", {}, max_retries=3)
        await queue.execute_task(task_id, "test_eventual", {})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.COMPLETED
        assert progress.attempt_count == 3
        assert progress.result["recovered"] is True

    @pytest.mark.asyncio
    async def test_no_worker_registered_fails_immediately(self) -> None:
        """Task with no registered worker fails with error."""
        queue, _redis = make_queue()

        task_id = await queue.enqueue("nonexistent", {})
        await queue.execute_task(task_id, "nonexistent", {})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.FAILED
        assert "No worker registered" in progress.error

    @pytest.mark.asyncio
    async def test_single_retry_exhausted(self) -> None:
        """Task with max_retries=1 fails after one attempt."""
        queue, _redis = make_queue()
        worker = FailWorker()
        worker.max_retries = 1
        queue.register_worker(worker)

        task_id = await queue.enqueue("test_fail", {}, max_retries=1)
        await queue.execute_task(task_id, "test_fail", {})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.FAILED
        assert progress.attempt_count == 1


# --- Scenario 5: Concurrent tasks with concurrency control ------------------


class TestConcurrencyControl:
    """Scenario 5: Concurrency is controlled via semaphore."""

    @pytest.mark.asyncio
    async def test_concurrent_tasks_complete_independently(self) -> None:
        """Multiple tasks complete with independent results."""
        queue, _redis = make_queue()
        queue.register_worker(SlowWorker())

        task_ids = []
        for _i in range(5):
            tid = await queue.enqueue("test_slow", {"steps": 2})
            task_ids.append(tid)

        # Execute all concurrently
        await asyncio.gather(*[queue.execute_task(tid, "test_slow", {"steps": 2}) for tid in task_ids])

        for tid in task_ids:
            progress = await queue.get_status(tid)
            assert progress.status == TaskStatus.COMPLETED
            assert progress.result["completed"] is True

    @pytest.mark.asyncio
    async def test_max_concurrency_enforced(self) -> None:
        """Semaphore limits concurrent task execution."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        queue, _redis = make_queue()

        class ConcurrencyTracker(TaskWorker):
            task_type = "test_concurrency"

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                nonlocal max_concurrent, current_concurrent
                async with lock:
                    current_concurrent += 1
                    if current_concurrent > max_concurrent:
                        max_concurrent = current_concurrent
                await asyncio.sleep(0.01)
                async with lock:
                    current_concurrent -= 1
                return {"ok": True}

        queue.register_worker(ConcurrencyTracker())

        # Enqueue 10 tasks
        task_ids = []
        for _ in range(10):
            tid = await queue.enqueue("test_concurrency", {})
            task_ids.append(tid)

        # Run with concurrency limit via semaphore
        sem = asyncio.Semaphore(4)

        async def limited_execute(tid: str) -> None:
            async with sem:
                await queue.execute_task(tid, "test_concurrency", {})

        await asyncio.gather(*[limited_execute(tid) for tid in task_ids])

        # Verify all completed
        for tid in task_ids:
            progress = await queue.get_status(tid)
            assert progress.status == TaskStatus.COMPLETED

        # Verify concurrency was limited
        assert max_concurrent <= 4

    @pytest.mark.asyncio
    async def test_no_data_corruption_under_concurrency(self) -> None:
        """Each task gets its own result under concurrent execution."""
        queue, _redis = make_queue()

        class IndexedWorker(TaskWorker):
            task_type = "test_indexed"

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                await asyncio.sleep(0)
                return {"index": payload["index"]}

        queue.register_worker(IndexedWorker())

        task_ids = []
        for i in range(10):
            tid = await queue.enqueue("test_indexed", {"index": i})
            task_ids.append((tid, i))

        await asyncio.gather(*[queue.execute_task(tid, "test_indexed", {"index": idx}) for tid, idx in task_ids])

        for tid, expected_idx in task_ids:
            progress = await queue.get_status(tid)
            assert progress.result["index"] == expected_idx


# --- Consumer group processing -----------------------------------------------


class TestConsumerGroupProcessing:
    """Consumer group: XREADGROUP, process, XACK."""

    @pytest.mark.asyncio
    async def test_process_one_reads_and_executes(self) -> None:
        """process_one reads from stream and executes the task."""
        queue, redis = make_queue()
        queue.register_worker(SuccessWorker())

        await queue.enqueue("test_success", {"engagement_id": "eng-1"})

        # Ensure consumer group
        await queue.ensure_consumer_groups()

        # Process one message
        progress = await queue.process_one("test_success", "worker-1", block_ms=0)

        assert progress is not None
        assert progress.status == TaskStatus.COMPLETED
        assert progress.result["engagement_id"] == "eng-1"

    @pytest.mark.asyncio
    async def test_process_one_acks_message(self) -> None:
        """process_one ACKs the message after execution."""
        queue, redis = make_queue()
        queue.register_worker(SuccessWorker())

        await queue.enqueue("test_success", {})
        await queue.ensure_consumer_groups()

        await queue.process_one("test_success", "worker-1", block_ms=0)

        stream_key = f"{STREAM_PREFIX}:test_success"
        assert stream_key in redis._acked
        assert len(redis._acked[stream_key]) == 1

    @pytest.mark.asyncio
    async def test_process_one_returns_none_when_empty(self) -> None:
        """process_one returns None when no messages available."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        await queue.ensure_consumer_groups()
        progress = await queue.process_one("test_success", "worker-1", block_ms=0)

        assert progress is None

    @pytest.mark.asyncio
    async def test_ensure_consumer_groups_idempotent(self) -> None:
        """ensure_consumer_groups can be called multiple times."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        await queue.ensure_consumer_groups()
        await queue.ensure_consumer_groups()  # Should not raise


# --- TaskWorker base class tests --------------------------------------------


class TestTaskWorkerBase:
    """TaskWorker abstract base class."""

    def test_report_progress_updates_state(self) -> None:
        """report_progress updates current_step and total_steps."""
        worker = SuccessWorker()
        worker.report_progress(5, 10)

        assert worker.progress["current_step"] == 5
        assert worker.progress["total_steps"] == 10
        assert worker.progress["percent_complete"] == 50

    def test_progress_defaults_to_zero(self) -> None:
        """New worker has zero progress."""
        worker = SuccessWorker()

        assert worker.progress["current_step"] == 0
        assert worker.progress["total_steps"] == 0

    def test_worker_requires_task_type(self) -> None:
        """Registering a worker without task_type raises ValueError."""
        queue, _redis = make_queue()

        class EmptyTypeWorker(TaskWorker):
            task_type = ""

            async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
                return {}

        with pytest.raises(ValueError, match="task_type must be set"):
            queue.register_worker(EmptyTypeWorker())

    def test_progress_percent_calculation(self) -> None:
        """Percent is correctly calculated from step/total."""
        worker = SuccessWorker()
        worker.report_progress(3, 10)
        assert worker.progress["percent_complete"] == 30

        worker.report_progress(7, 10)
        assert worker.progress["percent_complete"] == 70


# --- TaskProgress dataclass tests -------------------------------------------


class TestTaskProgressDataclass:
    """TaskProgress data structure."""

    def test_defaults(self) -> None:
        """TaskProgress has sensible defaults."""
        progress = TaskProgress(task_id="test-1")

        assert progress.task_id == "test-1"
        assert progress.status == TaskStatus.PENDING
        assert progress.current_step == 0
        assert progress.total_steps == 0
        assert progress.error == ""
        assert progress.result == {}

    @pytest.mark.asyncio
    async def test_not_found_status(self) -> None:
        """Unknown task_id returns FAILED with error."""
        queue, _redis = make_queue()
        progress = await queue.get_status("nonexistent-id")
        assert progress.status == TaskStatus.FAILED
        assert "not found" in progress.error.lower()


# --- Status lifecycle tests --------------------------------------------------


class TestStatusLifecycle:
    """Status transitions: PENDING → RUNNING → COMPLETED/FAILED."""

    @pytest.mark.asyncio
    async def test_pending_to_completed(self) -> None:
        """Successful task: PENDING → RUNNING → COMPLETED."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})

        # Initially PENDING
        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.PENDING

        # After execution: COMPLETED
        await queue.execute_task(task_id, "test_success", {})
        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_pending_to_failed(self) -> None:
        """Failed task: PENDING → RUNNING → RETRYING → FAILED."""
        queue, _redis = make_queue()
        queue.register_worker(FailWorker())

        task_id = await queue.enqueue("test_fail", {}, max_retries=2)
        await queue.execute_task(task_id, "test_fail", {})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.FAILED
        assert progress.attempt_count == 2

    @pytest.mark.asyncio
    async def test_created_at_set_on_enqueue(self) -> None:
        """created_at is set when task is enqueued."""
        queue, _redis = make_queue()
        queue.register_worker(SuccessWorker())

        task_id = await queue.enqueue("test_success", {})
        progress = await queue.get_status(task_id)

        assert progress.created_at != ""
        assert "T" in progress.created_at
