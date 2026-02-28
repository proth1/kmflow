"""Request and response schemas for replay API endpoints (Story #345)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

# -- Request schemas ---


class SingleCaseRequest(BaseModel):
    """Request body for single-case replay."""

    case_id: str


class AggregateRequest(BaseModel):
    """Request body for aggregate volume replay."""

    engagement_id: str
    time_range_start: date
    time_range_end: date
    interval_granularity: Literal["hourly", "daily", "weekly", "monthly"] = "daily"


class VariantComparisonRequest(BaseModel):
    """Request body for variant comparison replay."""

    variant_a_id: str
    variant_b_id: str


# -- Response schemas ---


class ReplayTaskCreatedResponse(BaseModel):
    """Response for replay task creation (202 Accepted)."""

    task_id: str
    status: str
    replay_type: str


class ReplayTaskStatusResponse(BaseModel):
    """Response for replay task status polling."""

    task_id: str
    replay_type: str
    status: str
    progress_pct: int
    created_at: str


class ReplayFrameResponse(BaseModel):
    """Single frame in a replay sequence."""

    frame_index: int
    timestamp: str
    active_elements: list[str] = Field(default_factory=list)
    completed_elements: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReplayFramesPageResponse(BaseModel):
    """Paginated frames response."""

    task_id: str
    frames: list[ReplayFrameResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
