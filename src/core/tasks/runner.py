"""Unified task worker runner (KMFLOW-58).

Starts a consumer-group worker loop that processes tasks from all
registered ``TaskWorker`` subclasses via the ``TaskQueue``.

Publishes progress updates to Redis Pub/Sub so WebSocket clients
receive real-time notifications.

Usage in main.py lifespan::

    task_queue = TaskQueue(redis_client)
    task_queue.register_worker(PovGenerationWorker())
    task_queue.register_worker(EvidenceBatchWorker())
    task_queue.register_worker(GdprErasureWorker())
    await task_queue.ensure_consumer_groups()

    for i in range(settings.task_worker_count):
        asyncio.create_task(
            run_task_worker(task_queue, f"task-worker-{i}", shutdown_event, redis_client)
        )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis

from src.core.redis import CHANNEL_TASKS, publish_event
from src.core.tasks.queue import TaskProgress, TaskQueue

logger = logging.getLogger(__name__)

# How long to block waiting for a message (ms).
_BLOCK_MS = 2000

# Seconds to wait after an unexpected error before retrying.
_ERROR_BACKOFF = 5


async def run_task_worker(
    task_queue: TaskQueue,
    worker_id: str,
    shutdown_event: asyncio.Event,
    redis_client: aioredis.Redis,
) -> None:
    """Run a task worker loop that processes all registered task types.

    Iterates through each registered task type in round-robin fashion,
    processing one message per type per cycle.  Publishes progress
    updates to the ``CHANNEL_TASKS`` Pub/Sub channel for WebSocket
    relay.

    Args:
        task_queue: TaskQueue with registered workers.
        worker_id: Unique consumer identity (e.g. ``task-worker-0``).
        shutdown_event: Set to signal graceful shutdown.
        redis_client: Redis client for Pub/Sub progress notifications.
    """
    task_types = sorted(task_queue.registered_types)
    if not task_types:
        logger.warning("Task worker %s: no task types registered, exiting", worker_id)
        return

    logger.info(
        "Task worker %s started, processing types: %s",
        worker_id,
        ", ".join(task_types),
    )

    while not shutdown_event.is_set():
        try:
            processed_any = False
            for task_type in task_types:
                if shutdown_event.is_set():
                    break

                progress = await task_queue.process_one(
                    task_type,
                    worker_id,
                    block_ms=_BLOCK_MS,
                )

                if progress is not None:
                    processed_any = True
                    # Publish progress to Pub/Sub for WebSocket relay
                    await _publish_task_progress(redis_client, progress)
                    logger.info(
                        "Task worker %s completed task %s (type=%s, status=%s)",
                        worker_id,
                        progress.task_id,
                        progress.task_type,
                        progress.status.value,
                    )

            # If nothing was processed in this cycle, short sleep to avoid
            # busy-looping (the block_ms on xreadgroup already provides
            # backpressure, but this covers the edge case of all types
            # returning None immediately).
            if not processed_any and not shutdown_event.is_set():
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Task worker %s cancelled", worker_id)
            return
        except Exception:  # Intentionally broad: worker loop must not crash on any handler error
            logger.exception("Task worker %s unexpected error", worker_id)
            if not shutdown_event.is_set():
                await asyncio.sleep(_ERROR_BACKOFF)

    logger.info("Task worker %s stopped", worker_id)


async def _publish_task_progress(
    redis_client: aioredis.Redis,
    progress: TaskProgress,
) -> None:
    """Publish task progress to Pub/Sub for WebSocket relay.

    Args:
        redis_client: Redis client.
        progress: TaskProgress dataclass from the queue.
    """
    try:
        event: dict[str, Any] = {
            "event": "task_progress",
            "task_id": progress.task_id,
            "task_type": progress.task_type,
            "status": progress.status.value,
            "current_step": progress.current_step,
            "total_steps": progress.total_steps,
            "percent_complete": progress.percent_complete,
            "error": progress.error,
        }
        await publish_event(redis_client, CHANNEL_TASKS, event)
    except Exception:  # Intentionally broad: progress notification is best-effort; must not mask original errors
        # Non-fatal — progress notification is best-effort
        logger.warning("Failed to publish task progress for %s", progress.task_id)
