"""Task queue service: enqueue, status polling, and worker loop (Story #320).

Provides ``TaskQueue`` — the central service for submitting background
tasks to Redis Streams, tracking their progress, and running the
consumer-group worker loop that dispatches to ``TaskWorker`` subclasses.

Redis keys used:
    ``kmflow:tasks:{task_type}``          — Stream per task type
    ``kmflow:task:progress:{task_id}``    — Hash with status / progress fields
    ``kmflow:task:payload:{task_id}``     — Hash with original payload

Consumer group: ``kmflow-workers``
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.tasks.base import TaskStatus, TaskWorker

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "kmflow-workers"
STREAM_PREFIX = "kmflow:tasks"
PROGRESS_PREFIX = "kmflow:task:progress"
PAYLOAD_PREFIX = "kmflow:task:payload"


@dataclass
class TaskProgress:
    """Snapshot of a task's current state.

    Attributes:
        task_id: Unique task identifier.
        task_type: The kind of task (e.g. ``pov_generation``).
        status: Current lifecycle status.
        current_step: Steps completed so far.
        total_steps: Total expected steps.
        percent_complete: Integer percentage (0-100).
        error: Error message if the task failed.
        attempt_count: Number of execution attempts.
        result: Final result payload (only when COMPLETED).
        created_at: When the task was enqueued.
        completed_at: When the task finished (COMPLETED or FAILED).
    """

    task_id: str
    task_type: str = ""
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    total_steps: int = 0
    percent_complete: int = 0
    error: str = ""
    attempt_count: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""


class TaskQueue:
    """Async task queue backed by Redis Streams.

    Manages the full lifecycle: enqueue → progress tracking → result
    retrieval.  The ``run_worker`` method starts the consumer-group
    loop that dispatches messages to registered ``TaskWorker`` instances.

    Args:
        redis: An async Redis client (``redis.asyncio.Redis``).
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._workers: dict[str, TaskWorker] = {}

    # -- Worker registration ---------------------------------------------------

    def register_worker(self, worker: TaskWorker) -> None:
        """Register a worker class for a given task type.

        Args:
            worker: TaskWorker instance whose ``task_type`` determines
                which stream it consumes from.

        Raises:
            ValueError: If ``task_type`` is empty.
        """
        if not worker.task_type:
            raise ValueError("TaskWorker.task_type must be set")
        self._workers[worker.task_type] = worker

    # -- Enqueue ---------------------------------------------------------------

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        max_retries: int = 3,
    ) -> str:
        """Submit a task to the queue.

        Creates a progress hash in Redis, enqueues a message on the
        appropriate stream, and returns the task ID.

        Args:
            task_type: Type of task (must match a registered worker).
            payload: Task-specific input data.
            max_retries: Maximum retry attempts.

        Returns:
            A UUID task_id for polling status.
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        stream = f"{STREAM_PREFIX}:{task_type}"
        progress_key = f"{PROGRESS_PREFIX}:{task_id}"
        payload_key = f"{PAYLOAD_PREFIX}:{task_id}"

        # Store initial progress hash
        await self._redis.hset(
            progress_key,
            mapping={
                "task_id": task_id,
                "task_type": task_type,
                "status": TaskStatus.PENDING.value,
                "current_step": "0",
                "total_steps": "0",
                "percent_complete": "0",
                "error": "",
                "attempt_count": "0",
                "max_retries": str(max_retries),
                "created_at": now,
                "completed_at": "",
            },
        )
        # TTL: 24 hours for progress hash
        await self._redis.expire(progress_key, 86400)

        # Store payload for worker retrieval
        await self._redis.hset(
            payload_key,
            mapping={"payload": json.dumps(payload)},
        )
        await self._redis.expire(payload_key, 86400)

        # Enqueue to stream
        await self._redis.xadd(
            stream,
            {"task_id": task_id, "payload": json.dumps(payload)},
            maxlen=10000,
        )

        logger.info("Enqueued task %s (type=%s)", task_id, task_type)
        return task_id

    # -- Status polling --------------------------------------------------------

    async def get_status(self, task_id: str) -> TaskProgress:
        """Get the current status and progress of a task.

        Args:
            task_id: The task identifier returned by ``enqueue()``.

        Returns:
            TaskProgress snapshot.
        """
        progress_key = f"{PROGRESS_PREFIX}:{task_id}"
        data = await self._redis.hgetall(progress_key)

        if not data:
            return TaskProgress(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error="Task not found",
            )

        # Check for completed result in the hash
        result_json = data.get("result", "")
        result = json.loads(result_json) if result_json else {}

        return TaskProgress(
            task_id=task_id,
            task_type=data.get("task_type", ""),
            status=TaskStatus(data.get("status", "PENDING")),
            current_step=int(data.get("current_step", 0)),
            total_steps=int(data.get("total_steps", 0)),
            percent_complete=int(data.get("percent_complete", 0)),
            error=data.get("error", ""),
            attempt_count=int(data.get("attempt_count", 0)),
            result=result,
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
        )

    # -- Progress update (called by worker runner) -----------------------------

    async def _update_progress(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        current_step: int | None = None,
        total_steps: int | None = None,
        error: str | None = None,
        attempt_count: int | None = None,
        result: dict[str, Any] | None = None,
        completed_at: str | None = None,
    ) -> None:
        """Update the progress hash for a task.

        Only provided fields are updated; others remain unchanged.
        """
        progress_key = f"{PROGRESS_PREFIX}:{task_id}"
        updates: dict[str, str] = {}

        if status is not None:
            updates["status"] = status.value
        if current_step is not None:
            updates["current_step"] = str(current_step)
        if total_steps is not None:
            updates["total_steps"] = str(total_steps)
        if current_step is not None and total_steps is not None and total_steps > 0:
            updates["percent_complete"] = str(int((current_step / total_steps) * 100))
        if error is not None:
            updates["error"] = error
        if attempt_count is not None:
            updates["attempt_count"] = str(attempt_count)
        if result is not None:
            updates["result"] = json.dumps(result)
        if completed_at is not None:
            updates["completed_at"] = completed_at

        if updates:
            await self._redis.hset(progress_key, mapping=updates)

    # -- Worker execution (single task) ----------------------------------------

    async def execute_task(
        self,
        task_id: str,
        task_type: str,
        payload: dict[str, Any],
    ) -> TaskProgress:
        """Execute a single task through its registered worker.

        Handles retries, progress updates, and result/error recording.

        Args:
            task_id: Unique task identifier.
            task_type: Worker type to dispatch to.
            payload: Task input data.

        Returns:
            Final TaskProgress after execution completes or fails.
        """
        worker = self._workers.get(task_type)
        if not worker:
            await self._update_progress(
                task_id,
                status=TaskStatus.FAILED,
                error=f"No worker registered for task type: {task_type}",
                completed_at=datetime.now(UTC).isoformat(),
            )
            return await self.get_status(task_id)

        progress_key = f"{PROGRESS_PREFIX}:{task_id}"
        data = await self._redis.hgetall(progress_key)
        max_retries = int(data.get("max_retries", str(worker.max_retries)))

        attempt = 0
        last_error = ""

        while attempt < max_retries:
            attempt += 1
            worker._task_id = task_id
            worker._current_step = 0
            worker._total_steps = 0

            await self._update_progress(
                task_id,
                status=TaskStatus.RUNNING,
                attempt_count=attempt,
            )

            try:
                result = await worker.execute(payload)

                # Push final progress from worker
                prog = worker.progress
                await self._update_progress(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    current_step=prog["current_step"],
                    total_steps=prog["total_steps"],
                    result=result,
                    completed_at=datetime.now(UTC).isoformat(),
                )
                return await self.get_status(task_id)

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Task %s attempt %d/%d failed: %s",
                    task_id, attempt, max_retries, last_error,
                )

                if attempt < max_retries:
                    await self._update_progress(
                        task_id,
                        status=TaskStatus.RETRYING,
                        error=last_error,
                        attempt_count=attempt,
                    )
                    # No sleep — retry immediately (in real deployment,
                    # exponential backoff would be added here)

        # All retries exhausted
        await self._update_progress(
            task_id,
            status=TaskStatus.FAILED,
            error=last_error,
            attempt_count=attempt,
            completed_at=datetime.now(UTC).isoformat(),
        )
        return await self.get_status(task_id)

    # -- Consumer group worker loop -------------------------------------------

    async def ensure_consumer_groups(self) -> None:
        """Create consumer groups for all registered task types.

        Idempotent — safe to call on startup.
        """
        for task_type in self._workers:
            stream = f"{STREAM_PREFIX}:{task_type}"
            try:
                await self._redis.xgroup_create(
                    stream, CONSUMER_GROUP, id="0", mkstream=True,
                )
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def process_one(
        self,
        task_type: str,
        consumer_name: str,
        block_ms: int = 5000,
    ) -> TaskProgress | None:
        """Read and process one task from the stream.

        Uses XREADGROUP to claim a message from the consumer group,
        executes it, and ACKs on success.

        Args:
            task_type: Which stream to read from.
            consumer_name: Unique consumer identity (e.g. ``worker-1``).
            block_ms: How long to block waiting for a message.

        Returns:
            TaskProgress if a task was processed, None if no messages.
        """
        stream = f"{STREAM_PREFIX}:{task_type}"

        result = await self._redis.xreadgroup(
            CONSUMER_GROUP,
            consumer_name,
            {stream: ">"},
            count=1,
            block=block_ms,
        )

        if not result:
            return None

        for _stream_name, entries in result:
            for msg_id, fields in entries:
                task_id = fields.get("task_id", "")
                payload_raw = fields.get("payload", "{}")
                try:
                    payload = json.loads(payload_raw)
                except (json.JSONDecodeError, TypeError):
                    payload = {}

                progress = await self.execute_task(task_id, task_type, payload)

                # ACK only after successful execution or final failure
                await self._redis.xack(stream, CONSUMER_GROUP, msg_id)

                return progress

        return None
