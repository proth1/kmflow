"""Replay service for process animation tasks (Story #345).

Handles creation and management of async replay tasks: single-case
timeline, aggregate volume, and variant comparison. Tasks are stored
in-memory with frame data for paginated retrieval.
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ReplayTaskStatus(enum.StrEnum):
    """Status of an async replay task."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReplayType(enum.StrEnum):
    """Type of replay task."""

    SINGLE_CASE = "single_case"
    AGGREGATE = "aggregate"
    VARIANT_COMPARISON = "variant_comparison"


@dataclass
class ReplayFrame:
    """A single frame in a replay sequence."""

    frame_index: int
    timestamp: str
    active_elements: list[str] = field(default_factory=list)
    completed_elements: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "active_elements": self.active_elements,
            "completed_elements": self.completed_elements,
            "metrics": self.metrics,
        }


@dataclass
class ReplayTask:
    """An async replay computation task."""

    id: str
    replay_type: str
    status: str = ReplayTaskStatus.PENDING
    progress_pct: int = 0
    frames: list[ReplayFrame] = field(default_factory=list)
    created_at: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(tz=UTC).isoformat()

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.id,
            "replay_type": self.replay_type,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at,
        }


# In-memory task store (production would use Redis)
_task_store: dict[str, ReplayTask] = {}


def create_single_case_task(case_id: str) -> ReplayTask:
    """Create a single-case replay task.

    Generates sample frames for the given case. In production this
    would enqueue a Redis task and return immediately.
    """
    task = ReplayTask(
        id=str(uuid.uuid4()),
        replay_type=ReplayType.SINGLE_CASE,
        status=ReplayTaskStatus.COMPLETED,
        progress_pct=100,
        params={"case_id": case_id},
    )

    # Generate sample frames (production: populated by async worker)
    task.frames = _generate_sample_frames(case_id, frame_count=20)

    _task_store[task.id] = task
    logger.debug("Created single-case replay task %s for case %s", task.id, case_id)
    return task


def create_aggregate_task(
    engagement_id: str,
    time_range_start: str,
    time_range_end: str,
    interval_granularity: str = "daily",
) -> ReplayTask:
    """Create an aggregate volume replay task."""
    task = ReplayTask(
        id=str(uuid.uuid4()),
        replay_type=ReplayType.AGGREGATE,
        status=ReplayTaskStatus.COMPLETED,
        progress_pct=100,
        params={
            "engagement_id": engagement_id,
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
            "interval_granularity": interval_granularity,
        },
    )

    task.frames = _generate_sample_frames(engagement_id, frame_count=15)

    _task_store[task.id] = task
    logger.debug("Created aggregate replay task %s", task.id)
    return task


def create_variant_comparison_task(
    variant_a_id: str,
    variant_b_id: str,
) -> ReplayTask:
    """Create a variant comparison replay task."""
    task = ReplayTask(
        id=str(uuid.uuid4()),
        replay_type=ReplayType.VARIANT_COMPARISON,
        status=ReplayTaskStatus.COMPLETED,
        progress_pct=100,
        params={
            "variant_a_id": variant_a_id,
            "variant_b_id": variant_b_id,
        },
    )

    task.frames = _generate_sample_frames(f"{variant_a_id}_vs_{variant_b_id}", frame_count=10)

    _task_store[task.id] = task
    logger.debug("Created variant comparison task %s", task.id)
    return task


def get_task(task_id: str) -> ReplayTask | None:
    """Retrieve a replay task by ID."""
    return _task_store.get(task_id)


def get_task_frames(
    task_id: str,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any] | None:
    """Get paginated frames for a replay task.

    Returns None if task not found. Returns frame page with
    pagination metadata otherwise.
    """
    task = _task_store.get(task_id)
    if task is None:
        return None

    total = len(task.frames)
    page = task.frames[offset : offset + limit]

    return {
        "task_id": task_id,
        "frames": [f.to_dict() for f in page],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


def _generate_sample_frames(seed: str, frame_count: int = 10) -> list[ReplayFrame]:
    """Generate sample replay frames for demonstration."""
    frames = []
    for i in range(frame_count):
        frames.append(ReplayFrame(
            frame_index=i,
            timestamp=f"2026-01-01T{i:02d}:00:00Z",
            active_elements=[f"element_{seed}_{i}"],
            completed_elements=[f"element_{seed}_{j}" for j in range(i)],
            metrics={"progress": round(i / max(frame_count - 1, 1) * 100, 1)},
        ))
    return frames


def clear_task_store() -> None:
    """Clear the in-memory task store. Used in tests."""
    _task_store.clear()
