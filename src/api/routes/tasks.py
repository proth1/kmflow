"""Task status and submission API routes (KMFLOW-58).

Provides endpoints for:
- ``POST /api/v1/tasks/submit`` — Submit a new async task
- ``GET /api/v1/tasks/{task_id}`` — Poll task status and progress
- ``GET /api/v1/tasks`` — List recent tasks (optional task_type filter)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.core.models import User
from src.core.tasks import TaskProgress, TaskQueue, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# -- Schemas -------------------------------------------------------------------


class TaskSubmitRequest(BaseModel):
    """Request to submit an async task."""

    task_type: str = Field(..., description="Task type (e.g. pov_generation, evidence_batch, gdpr_erasure)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Task-specific input data")
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")


class TaskSubmitResponse(BaseModel):
    """Response after task submission."""

    task_id: str
    task_type: str
    status: str = "PENDING"
    message: str = "Task submitted successfully"


class TaskStatusResponse(BaseModel):
    """Task status polling response."""

    task_id: str
    task_type: str
    status: str
    current_step: int
    total_steps: int
    percent_complete: int
    error: str = ""
    attempt_count: int = 0
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""


# -- Helpers -------------------------------------------------------------------


def _get_task_queue(request: Request) -> TaskQueue:
    """Get the TaskQueue from app state.

    Raises:
        HTTPException: If task queue is not available.
    """
    queue = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue is not available",
        )
    return queue


def _progress_to_response(p: TaskProgress) -> dict[str, Any]:
    """Convert TaskProgress to response dict."""
    return {
        "task_id": p.task_id,
        "task_type": p.task_type,
        "status": p.status.value,
        "current_step": p.current_step,
        "total_steps": p.total_steps,
        "percent_complete": p.percent_complete,
        "error": p.error,
        "attempt_count": p.attempt_count,
        "result": p.result,
        "created_at": p.created_at,
        "completed_at": p.completed_at,
    }


# -- Routes --------------------------------------------------------------------


@router.post("/submit", response_model=TaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_task(
    body: TaskSubmitRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit an async background task.

    Returns a task_id for polling status via GET /tasks/{task_id}.
    """
    queue = _get_task_queue(request)

    # Validate task type is registered
    if body.task_type not in queue._workers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown task type: {body.task_type}. Available: {', '.join(sorted(queue._workers.keys()))}",
        )

    task_id = await queue.enqueue(
        task_type=body.task_type,
        payload=body.payload,
        max_retries=body.max_retries,
    )

    logger.info(
        "Task submitted: %s (type=%s) by user %s",
        task_id,
        body.task_type,
        user.id,
    )

    return {
        "task_id": task_id,
        "task_type": body.task_type,
        "status": TaskStatus.PENDING.value,
        "message": "Task submitted successfully",
    }


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Poll the status and progress of an async task.

    Returns current step, percentage, and result (when completed).
    """
    queue = _get_task_queue(request)
    progress = await queue.get_status(task_id)

    if progress.status == TaskStatus.FAILED and progress.error == "Task not found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found (may have expired after 24h)",
        )

    return _progress_to_response(progress)
