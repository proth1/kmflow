"""Redis Stream consumer for task mining action aggregation.

Background worker that reads processed events from the task mining Redis
stream and aggregates them into higher-level user actions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

import redis.asyncio as aioredis

from src.core.redis import ensure_consumer_group
from src.taskmining.processor import TASK_MINING_STREAM

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "task_mining_workers"

# Action aggregation window: events within this window for the same
# app+window are grouped into a single action.
AGGREGATION_WINDOW_SECONDS = 30


async def process_task(task_data: dict[str, Any]) -> dict[str, Any]:
    """Process a single task mining stream message.

    Currently supports:
    - aggregate: Group raw events into user actions

    Args:
        task_data: The parsed task payload from the stream.

    Returns:
        Processing result dict.
    """
    task_type = task_data.get("task_type", "unknown")
    logger.debug("Processing task mining task: type=%s", task_type)

    # TODO: Wire up aggregation engine (src/taskmining/aggregation/) here.
    # SessionAggregator -> ActionClassifier -> EvidenceMaterializer
    # See Epic #206 stories #207, #208, #209. Stubs below are Phase 1 placeholders.
    if task_type == "aggregate":
        return {
            "status": "aggregated",
            "event_type": task_data.get("event_type"),
            "session_id": task_data.get("session_id"),
            "application_name": task_data.get("application_name"),
        }
    elif task_type == "materialize":
        return {"status": "materialized"}
    elif task_type == "assemble_switching":
        return await _handle_assemble_switching(task_data)
    else:
        return {"status": "unknown_task_type", "task_type": task_type}


async def run_worker(
    redis_client: aioredis.Redis,
    worker_id: str = "tm-worker-1",
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run the task mining worker loop.

    Reads events from the Redis Stream and processes them.
    Stops when shutdown_event is set.
    """
    await ensure_consumer_group(redis_client, TASK_MINING_STREAM, CONSUMER_GROUP)
    logger.info("Task mining worker %s started", worker_id)

    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    while not shutdown_event.is_set():
        try:
            result = await redis_client.xreadgroup(
                CONSUMER_GROUP,
                worker_id,
                {TASK_MINING_STREAM: ">"},
                count=10,
                block=2000,
            )
            if not result:
                continue

            for _stream, messages in result:
                for msg_id, fields in messages:
                    try:
                        task_data = json.loads(fields.get("payload", "{}"))
                        await process_task(task_data)
                        await redis_client.xack(TASK_MINING_STREAM, CONSUMER_GROUP, msg_id)
                    except Exception:  # Intentionally broad: worker loop
                        logger.exception("Failed to process task mining message %s", msg_id)
        except asyncio.CancelledError:
            break
        except Exception:  # Intentionally broad: worker loop
            logger.exception("Task mining worker error, retrying in 5s")
            await asyncio.sleep(5)

    logger.info("Task mining worker %s stopped", worker_id)


async def _handle_assemble_switching(task_data: dict[str, Any]) -> dict[str, Any]:
    """Handle the assemble_switching task type.

    Assembles APP_SWITCH events into SwitchingTrace records and ingests
    them into the knowledge graph. Requires a database session and graph
    service — these are lazily imported to avoid circular dependencies.

    Args:
        task_data: Must contain 'engagement_id'. 'session_id' is optional.

    Returns:
        Dict with traces_created and graph_nodes_created counts.
    """
    engagement_id_str = task_data.get("engagement_id")
    session_id_str = task_data.get("session_id")

    if not engagement_id_str:
        logger.warning("assemble_switching task missing engagement_id")
        return {"status": "error", "detail": "engagement_id required"}

    import uuid as _uuid

    try:
        engagement_id = _uuid.UUID(engagement_id_str)
        session_id = _uuid.UUID(session_id_str) if session_id_str else None
    except ValueError:
        logger.warning("assemble_switching: invalid UUID in task_data")
        return {"status": "error", "detail": "invalid UUID"}

    # Lazy imports to avoid circular dependency at module load time
    from src.core.database import async_session_factory
    from src.semantic.graph import KnowledgeGraphService
    from src.taskmining.graph_ingest import ingest_switching_traces
    from src.taskmining.switching import assemble_switching_traces

    traces_created = 0
    graph_nodes_created = 0

    async with async_session_factory() as db_session:
        traces = await assemble_switching_traces(
            session=db_session,
            engagement_id=engagement_id,
            session_id=session_id,
        )
        await db_session.commit()
        traces_created = len(traces)

    graph_service = KnowledgeGraphService()
    async with async_session_factory() as db_session:
        graph_summary = await ingest_switching_traces(
            db_session=db_session,
            graph_service=graph_service,
            engagement_id=str(engagement_id),
        )
        graph_nodes_created = graph_summary.get("switching_traces", 0)

    logger.info(
        "assemble_switching complete: engagement=%s traces=%d graph_nodes=%d",
        engagement_id_str,
        traces_created,
        graph_nodes_created,
    )
    return {
        "status": "ok",
        "traces_created": traces_created,
        "graph_nodes_created": graph_nodes_created,
    }
