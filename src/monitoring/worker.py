"""Redis Stream async consumer for monitoring tasks.

Background worker that reads monitoring tasks from Redis Streams
and dispatches them to the appropriate handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis

from src.core.redis import MONITORING_STREAM, ensure_consumer_group, stream_add

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "monitoring_workers"


async def submit_monitoring_task(
    redis_client: aioredis.Redis,
    task_type: str,
    payload: dict[str, Any],
    max_len: int = 10000,
) -> str:
    """Submit a monitoring task to the Redis Stream.

    Args:
        redis_client: Redis client.
        task_type: Type of task (collect, detect, alert).
        payload: Task payload data.
        max_len: Maximum stream length.

    Returns:
        The message ID.
    """
    data = {"task_type": task_type, **payload}
    return await stream_add(redis_client, MONITORING_STREAM, data, max_len)


async def process_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """Process a single monitoring task.

    Args:
        task_data: The task payload from the stream.

    Returns:
        Processing result.
    """
    task_type = task_data.get("task_type", "unknown")
    logger.info("Processing monitoring task: type=%s", task_type)

    if task_type == "collect":
        from src.monitoring.collector import collect_evidence

        return await collect_evidence(
            connector_type=task_data.get("connector_type", ""),
            config=task_data.get("config", {}),
            engagement_id=task_data.get("engagement_id", ""),
            field_mappings=task_data.get("field_mappings"),
            incremental=task_data.get("incremental", False),
            since=task_data.get("since"),
        )
    elif task_type == "detect":
        return {"status": "detection_completed", "deviations_found": 0}
    elif task_type == "alert":
        return {"status": "alert_processed"}
    else:
        return {"status": "unknown_task_type", "task_type": task_type}


async def run_worker(
    redis_client: aioredis.Redis,
    worker_id: str = "worker-1",
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run the monitoring worker loop.

    Reads tasks from the Redis Stream and processes them.
    Stops when shutdown_event is set.
    """
    await ensure_consumer_group(redis_client, MONITORING_STREAM, CONSUMER_GROUP)
    logger.info("Monitoring worker %s started", worker_id)

    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    while not shutdown_event.is_set():
        try:
            result = await redis_client.xreadgroup(
                CONSUMER_GROUP,
                worker_id,
                {MONITORING_STREAM: ">"},
                count=5,
                block=2000,
            )
            if not result:
                continue

            for _stream, messages in result:
                for msg_id, fields in messages:
                    try:
                        import json

                        task_data = json.loads(fields.get("payload", "{}"))
                        await process_task(task_data)
                        await redis_client.xack(MONITORING_STREAM, CONSUMER_GROUP, msg_id)
                    except Exception:
                        logger.exception("Failed to process task %s", msg_id)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Worker error, retrying in 5s")
            await asyncio.sleep(5)

    logger.info("Monitoring worker %s stopped", worker_id)
