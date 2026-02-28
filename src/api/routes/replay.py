"""Replay API routes (Story #345).

Provides async replay task endpoints:
- POST /replay/single-case — create single-case timeline replay
- POST /replay/aggregate — create aggregate volume replay
- POST /replay/variant-comparison — create variant comparison replay
- GET /replay/{id}/status — check task status
- GET /replay/{id}/frames — paginated frame retrieval
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemas.replay import (
    AggregateRequest,
    SingleCaseRequest,
    VariantComparisonRequest,
)
from src.core.models import User
from src.core.permissions import require_permission
from src.core.services.replay_service import (
    create_aggregate_task,
    create_single_case_task,
    create_variant_comparison_task,
    get_task,
    get_task_frames,
)

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


@router.post("/single-case", status_code=status.HTTP_202_ACCEPTED)
async def create_single_case_replay(
    body: SingleCaseRequest,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Create a single-case timeline replay task.

    Returns immediately with task_id and current status.
    """
    task = create_single_case_task(body.case_id)
    return {
        "task_id": task.id,
        "status": task.status,
        "replay_type": task.replay_type,
    }


@router.post("/aggregate", status_code=status.HTTP_202_ACCEPTED)
async def create_aggregate_replay(
    body: AggregateRequest,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Create an aggregate volume replay task."""
    task = create_aggregate_task(
        engagement_id=body.engagement_id,
        time_range_start=body.time_range_start.isoformat(),
        time_range_end=body.time_range_end.isoformat(),
        interval_granularity=body.interval_granularity,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "replay_type": task.replay_type,
    }


@router.post("/variant-comparison", status_code=status.HTTP_202_ACCEPTED)
async def create_variant_comparison_replay(
    body: VariantComparisonRequest,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Create a variant comparison replay task."""
    task = create_variant_comparison_task(
        variant_a_id=body.variant_a_id,
        variant_b_id=body.variant_b_id,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "replay_type": task.replay_type,
    }


@router.get("/{task_id}/status")
async def get_replay_status(
    task_id: str,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get the status of a replay task."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay task not found: {task_id}",
        )
    return task.to_status_dict()


@router.get("/{task_id}/frames")
async def get_replay_frames(
    task_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get paginated frames for a completed replay task."""
    result = get_task_frames(task_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay task not found: {task_id}",
        )
    return result
