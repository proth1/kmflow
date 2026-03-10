"""BDD tests for Redis worker wiring (KMFLOW-58).

Tests the unified task worker runner, POV async dispatch, evidence batch
processing, GDPR erasure worker, and WebSocket progress bridge.

Acceptance criteria from Jira:
  - Submit async task → 202 with task_id, task in Redis stream as PENDING
  - Poll task status → response includes status, progress_percentage, current_stage
  - Worker crash → retry up to 3 times, then FAILED with logged attempts
  - POV progress → 12.5% per consensus step, WebSocket updates
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.tasks.base import TaskStatus, TaskWorker
from src.core.tasks.queue import (
    STREAM_PREFIX,
    TaskQueue,
)
from src.core.tasks.runner import _publish_task_progress, run_task_worker

# -- FakeRedis (extended for Pub/Sub) -----------------------------------------


class FakeRedis:
    """In-memory Redis mock with Streams + Pub/Sub support."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._acked: dict[str, set[str]] = {}
        self._groups: dict[str, set[str]] = {}
        self._msg_counter = 0
        self._pending: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self._published: list[tuple[str, str]] = []

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
        for stream_name in streams:
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

    async def publish(self, channel: str, data: str) -> int:
        self._published.append((channel, data))
        return 1

    async def ping(self) -> bool:
        return True


# -- Test workers --------------------------------------------------------------


class CountingWorker(TaskWorker):
    """Worker that tracks calls and reports step-by-step progress."""

    task_type = "test_counting"
    max_retries = 1

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        steps = payload.get("steps", 4)
        for i in range(1, steps + 1):
            self.report_progress(i, steps)
        return {"done": True, "steps": steps}


class CrashWorker(TaskWorker):
    """Worker that crashes every time."""

    task_type = "test_crash"
    max_retries = 3

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.attempts += 1
        raise RuntimeError(f"crash on attempt {self.attempts}")


class CrashThenRecoverWorker(TaskWorker):
    """Worker that crashes twice then succeeds (tests retry)."""

    task_type = "test_crash_recover"
    max_retries = 3

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.attempts += 1
        if self.attempts < 3:
            raise RuntimeError(f"crash on attempt {self.attempts}")
        self.report_progress(1, 1)
        return {"recovered": True}


# -- Helpers -------------------------------------------------------------------


def make_queue(*workers: TaskWorker) -> tuple[TaskQueue, FakeRedis]:
    """Create a TaskQueue with FakeRedis and register workers."""
    redis = FakeRedis()
    queue = TaskQueue(redis)
    for w in workers:
        queue.register_worker(w)
    return queue, redis


# =============================================================================
# Scenario 1: Submit async task and receive task_id
# =============================================================================


class TestSubmitAsyncTask:
    """Given the worker service is running and connected to Redis,
    When a client submits a task,
    Then a 202 Accepted response is returned with a task_id,
    And the task appears in the Redis stream with status PENDING.
    """

    @pytest.mark.asyncio
    async def test_enqueue_returns_task_id(self) -> None:
        queue, redis = make_queue(CountingWorker())
        task_id = await queue.enqueue("test_counting", {"steps": 4})

        assert task_id
        assert len(task_id) == 36  # UUID

    @pytest.mark.asyncio
    async def test_task_appears_in_stream(self) -> None:
        queue, redis = make_queue(CountingWorker())
        task_id = await queue.enqueue("test_counting", {"steps": 4})

        stream = f"{STREAM_PREFIX}:test_counting"
        assert stream in redis._streams
        assert len(redis._streams[stream]) == 1
        _, fields = redis._streams[stream][0]
        assert fields["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_task_status_is_pending(self) -> None:
        queue, redis = make_queue(CountingWorker())
        task_id = await queue.enqueue("test_counting", {"steps": 4})

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.PENDING
        assert progress.task_type == "test_counting"


# =============================================================================
# Scenario 2: Poll task status with progress
# =============================================================================


class TestPollTaskProgress:
    """Given a task has been submitted with a task_id,
    When the client polls the status,
    Then the response includes status, progress_percentage, and current_stage.
    """

    @pytest.mark.asyncio
    async def test_completed_task_has_100_percent(self) -> None:
        queue, redis = make_queue(CountingWorker())
        await queue.enqueue("test_counting", {"steps": 4})

        result = await queue.process_one("test_counting", "worker-0")
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.percent_complete == 100

    @pytest.mark.asyncio
    async def test_progress_reflects_steps(self) -> None:
        queue, redis = make_queue(CountingWorker())
        await queue.enqueue("test_counting", {"steps": 8})

        result = await queue.process_one("test_counting", "worker-0")
        assert result is not None
        assert result.current_step == 8
        assert result.total_steps == 8

    @pytest.mark.asyncio
    async def test_poll_after_completion(self) -> None:
        queue, redis = make_queue(CountingWorker())
        task_id = await queue.enqueue("test_counting", {"steps": 4})
        await queue.process_one("test_counting", "worker-0")

        progress = await queue.get_status(task_id)
        assert progress.status == TaskStatus.COMPLETED
        assert progress.result == {"done": True, "steps": 4}


# =============================================================================
# Scenario 3: Handle worker crash with retry
# =============================================================================


class TestWorkerCrashRetry:
    """Given a worker is processing a task,
    When the worker crashes unexpectedly,
    Then the task is retried up to 3 times before marking as FAILED,
    And each retry is logged with attempt number and error detail.
    """

    @pytest.mark.asyncio
    async def test_crash_exhausts_retries_then_fails(self) -> None:
        worker = CrashWorker()
        queue, redis = make_queue(worker)
        await queue.enqueue("test_crash", {}, max_retries=3)

        result = await queue.process_one("test_crash", "worker-0")
        assert result is not None
        assert result.status == TaskStatus.FAILED
        assert result.attempt_count == 3
        assert "crash on attempt" in result.error

    @pytest.mark.asyncio
    async def test_crash_then_recover(self) -> None:
        worker = CrashThenRecoverWorker()
        queue, redis = make_queue(worker)
        await queue.enqueue("test_crash_recover", {}, max_retries=3)

        result = await queue.process_one("test_crash_recover", "worker-0")
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"recovered": True}
        assert result.attempt_count == 3

    @pytest.mark.asyncio
    async def test_error_detail_includes_attempt_number(self) -> None:
        worker = CrashWorker()
        queue, redis = make_queue(worker)
        await queue.enqueue("test_crash", {}, max_retries=2)

        result = await queue.process_one("test_crash", "worker-0")
        assert result is not None
        assert "attempt 2" in result.error


# =============================================================================
# Scenario 4: Track POV task progress (12.5% per step)
# =============================================================================


class TestPovProgressTracking:
    """Given a POV generation task is in progress,
    When the worker completes each of the 8 consensus algorithm steps,
    Then the task progress increments proportionally (12.5% per step).
    """

    @pytest.mark.asyncio
    async def test_pov_worker_reports_8_steps(self) -> None:
        from src.pov.orchestrator import PovGenerationWorker

        worker = PovGenerationWorker()
        queue, redis = make_queue(worker)
        await queue.enqueue(
            "pov_generation",
            {"engagement_id": "test-eng-1"},
            max_retries=1,
        )

        result = await queue.process_one("pov_generation", "worker-0")
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.current_step == 8
        assert result.total_steps == 8
        assert result.percent_complete == 100

    @pytest.mark.asyncio
    async def test_pov_result_contains_state(self) -> None:
        from src.pov.orchestrator import PovGenerationWorker

        worker = PovGenerationWorker()
        queue, redis = make_queue(worker)
        await queue.enqueue(
            "pov_generation",
            {"engagement_id": "test-eng-1"},
            max_retries=1,
        )

        result = await queue.process_one("pov_generation", "worker-0")
        assert result is not None
        assert result.result["status"] == "COMPLETED"
        assert result.result["engagement_id"] == "test-eng-1"
        assert len(result.result["completed_steps"]) == 8


# =============================================================================
# Scenario 5: Unified worker runner publishes progress to Pub/Sub
# =============================================================================


class TestWorkerRunnerPubSub:
    """The unified task worker runner publishes progress updates
    to Redis Pub/Sub for WebSocket relay.
    """

    @pytest.mark.asyncio
    async def test_publish_task_progress(self) -> None:
        redis = FakeRedis()
        progress = MagicMock()
        progress.task_id = "abc-123"
        progress.task_type = "test_counting"
        progress.status.value = "COMPLETED"
        progress.current_step = 4
        progress.total_steps = 4
        progress.percent_complete = 100
        progress.error = ""

        await _publish_task_progress(redis, progress)

        assert len(redis._published) == 1
        channel, data = redis._published[0]
        assert channel == "kmflow:realtime:tasks"
        parsed = json.loads(data)
        assert parsed["task_id"] == "abc-123"
        assert parsed["status"] == "COMPLETED"
        assert parsed["percent_complete"] == 100

    @pytest.mark.asyncio
    async def test_runner_processes_and_publishes(self) -> None:
        worker = CountingWorker()
        queue, redis = make_queue(worker)
        await queue.ensure_consumer_groups()
        await queue.enqueue("test_counting", {"steps": 2})

        shutdown = asyncio.Event()

        async def run_then_stop() -> None:
            # Let the runner process one message, then stop
            await asyncio.sleep(0.1)
            shutdown.set()

        await asyncio.gather(
            run_task_worker(queue, "test-worker-0", shutdown, redis),
            run_then_stop(),
        )

        # Verify task was processed (check via Pub/Sub events, not instance
        # state, since execute_task creates a fresh worker instance)
        assert len(redis._published) >= 1
        _, data = redis._published[0]
        parsed = json.loads(data)
        assert parsed["event"] == "task_progress"
        assert parsed["task_type"] == "test_counting"
        assert parsed["status"] == "COMPLETED"


# =============================================================================
# Scenario 6: Task queue integration with multiple task types
# =============================================================================


class TestMultipleTaskTypes:
    """The worker runner processes multiple task types in round-robin."""

    @pytest.mark.asyncio
    async def test_two_task_types_processed(self) -> None:
        worker1 = CountingWorker()
        crash_worker = CrashThenRecoverWorker()
        queue, redis = make_queue(worker1, crash_worker)
        await queue.ensure_consumer_groups()

        await queue.enqueue("test_counting", {"steps": 2})
        await queue.enqueue("test_crash_recover", {})

        shutdown = asyncio.Event()

        async def run_then_stop() -> None:
            await asyncio.sleep(0.3)
            shutdown.set()

        await asyncio.gather(
            run_task_worker(queue, "test-worker-0", shutdown, redis),
            run_then_stop(),
        )

        # Verify both task types were processed (check via Pub/Sub events,
        # not instance state, since execute_task creates fresh instances)
        completed_types = {
            json.loads(data)["task_type"]
            for _, data in redis._published
            if json.loads(data).get("status") == "COMPLETED"
        }
        assert "test_counting" in completed_types
        assert "test_crash_recover" in completed_types


# =============================================================================
# Scenario 7: Evidence batch worker
# =============================================================================


class TestEvidenceBatchWorker:
    """Evidence batch worker validates payload and reports per-item progress."""

    @pytest.mark.asyncio
    async def test_missing_engagement_id_raises(self) -> None:
        from src.evidence.batch_worker import EvidenceBatchWorker

        worker = EvidenceBatchWorker()
        with pytest.raises(ValueError, match="engagement_id"):
            await worker.execute({"evidence_item_ids": ["id-1"]})

    @pytest.mark.asyncio
    async def test_empty_item_ids_raises(self) -> None:
        from src.evidence.batch_worker import EvidenceBatchWorker

        worker = EvidenceBatchWorker()
        with pytest.raises(ValueError, match="evidence_item_ids"):
            await worker.execute({"engagement_id": "eng-1", "evidence_item_ids": []})


# =============================================================================
# Scenario 8: GDPR erasure worker
# =============================================================================


class TestGdprErasureWorker:
    """GDPR erasure worker coordinates across PG, Neo4j, and Redis."""

    @pytest.mark.asyncio
    async def test_worker_has_correct_task_type(self) -> None:
        from src.gdpr.erasure_worker import GdprErasureWorker

        worker = GdprErasureWorker()
        assert worker.task_type == "gdpr_erasure"
        assert worker.max_retries == 3


# =============================================================================
# Scenario 9: Task not found returns 404-style error
# =============================================================================


class TestTaskNotFound:
    """Polling a non-existent task returns a clear error."""

    @pytest.mark.asyncio
    async def test_unknown_task_id(self) -> None:
        queue, _ = make_queue(CountingWorker())
        progress = await queue.get_status("nonexistent-id")
        assert progress.status == TaskStatus.FAILED
        assert "not found" in progress.error.lower()
