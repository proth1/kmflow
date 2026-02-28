"""Task worker base class and status enum (Story #320).

``TaskWorker`` is the abstract base class for all background task
implementations.  Subclasses override ``execute(payload)`` and may
call ``report_progress(current_step, total_steps)`` to push live
progress into the Redis hash that the polling API reads.

Status lifecycle::

    PENDING → RUNNING → COMPLETED
                     ↘ RETRYING → RUNNING  (up to max_retries)
                                ↘ FAILED

Example subclass::

    class PovGenerationWorker(TaskWorker):
        task_type = "pov_generation"

        async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
            engagement_id = payload["engagement_id"]
            # ... long-running POV generation ...
            self.report_progress(5, 10)
            # ... more work ...
            return {"pov_id": "pov-001", "status": "generated"}
"""

from __future__ import annotations

import abc
import enum
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TaskStatus(enum.StrEnum):
    """Lifecycle states for a background task."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class TaskWorker(abc.ABC):
    """Abstract base class for background task workers.

    Subclasses must set ``task_type`` (a string used as the Redis
    Streams key suffix) and implement ``execute(payload)``.

    Attributes:
        task_type: Identifies the kind of work this worker handles.
            Used as the suffix in ``kmflow:tasks:{task_type}``.
        max_retries: Maximum number of retry attempts before marking
            the task as FAILED.  Defaults to 3.
    """

    task_type: str = ""
    max_retries: int = 3

    def __init__(self) -> None:
        self._current_step: int = 0
        self._total_steps: int = 0
        self._task_id: str = ""

    @abc.abstractmethod
    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the task with the given payload.

        Args:
            payload: Task-specific input data.

        Returns:
            Result dict to be persisted in PostgreSQL.

        Raises:
            Exception: Any unhandled exception triggers retry logic.
        """

    def report_progress(self, current_step: int, total_steps: int) -> None:
        """Record progress for the polling API.

        This updates in-memory state that the task runner reads and
        pushes to the Redis progress hash.

        Args:
            current_step: Number of steps completed so far.
            total_steps: Total number of steps expected.
        """
        self._current_step = current_step
        self._total_steps = total_steps

    @property
    def progress(self) -> dict[str, int]:
        """Current progress snapshot."""
        total = self._total_steps or 1
        return {
            "current_step": self._current_step,
            "total_steps": self._total_steps,
            "percent_complete": int((self._current_step / total) * 100),
        }
