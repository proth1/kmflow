"""Camunda External Task Worker.

Polls Camunda for external tasks on configured topics, executes the
registered handler, and reports completion or failure back to the engine.
Runs as an asyncio background task within the FastAPI application.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.integrations.camunda import CamundaClient

logger = logging.getLogger(__name__)

# Type for external task handlers: receives task dict, returns output variables
TaskHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ExternalTaskWorker:
    """Polls and processes Camunda external tasks.

    Register handlers for specific topics, then call `start()` to begin polling.
    The worker runs until `stop()` is called.
    """

    def __init__(
        self,
        client: CamundaClient,
        worker_id: str = "kmflow-worker",
        poll_interval: float = 5.0,
        max_tasks: int = 5,
        lock_duration: int = 300_000,
    ) -> None:
        self._client = client
        self._worker_id = worker_id
        self._poll_interval = poll_interval
        self._max_tasks = max_tasks
        self._lock_duration = lock_duration
        self._handlers: dict[str, TaskHandler] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register(self, topic: str, handler: TaskHandler) -> None:
        """Register a handler for an external task topic."""
        self._handlers[topic] = handler
        logger.info("Registered external task handler for topic '%s'", topic)

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        if self._running:
            return
        if not self._handlers:
            logger.warning("No handlers registered — external task worker not started")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "External task worker started: worker_id=%s, topics=%s",
            self._worker_id,
            list(self._handlers.keys()),
        )

    async def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("External task worker stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop: fetch tasks, execute handlers, report results."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:  # Intentionally broad: poll cycle errors must not crash the worker loop
                logger.exception("Error in external task poll cycle")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        """Execute one poll cycle."""
        topics = [{"topicName": t} for t in self._handlers]
        try:
            tasks = await self._client.fetch_and_lock_external_tasks(
                worker_id=self._worker_id,
                topics=topics,
                max_tasks=self._max_tasks,
                lock_duration=self._lock_duration,
            )
        except Exception:  # Intentionally broad: Camunda engine may be unavailable or return unexpected errors
            logger.debug("Failed to fetch external tasks (engine may be down)")
            return

        for task in tasks:
            task_id = task.get("id", "")
            topic = task.get("topicName", "")
            handler = self._handlers.get(topic)

            if not handler:
                logger.warning("No handler for topic '%s' (task %s)", topic, task_id)
                continue

            try:
                output_vars = await handler(task)
                await self._client.complete_external_task(
                    task_id=task_id,
                    worker_id=self._worker_id,
                    variables=output_vars,
                )
                logger.info("Completed external task %s (topic=%s)", task_id, topic)
            except Exception as e:  # Intentionally broad: handler errors of any kind must be reported back to Camunda
                logger.error("External task %s failed: %s", task_id, e)
                retries = task.get("retries")
                remaining = (retries - 1) if retries and retries > 0 else 0
                try:
                    await self._client.fail_external_task(
                        task_id=task_id,
                        worker_id=self._worker_id,
                        error_message=str(e),
                        retries=remaining,
                    )
                except Exception:  # Intentionally broad: error during error handling, logging is best effort
                    logger.exception("Failed to report task failure for %s", task_id)
