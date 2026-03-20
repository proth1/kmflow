"""Pydantic schemas for validation API routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.models.validation_decision import ReviewerAction

# ---------------------------------------------------------------------------
# Review Pack Schemas
# ---------------------------------------------------------------------------


class ReviewPackResponse(BaseModel):
    """Response schema for a single review pack."""

    id: uuid.UUID
    engagement_id: uuid.UUID
    pov_version_id: uuid.UUID
    segment_index: int
    segment_activities: list[dict[str, Any]]
    activity_count: int
    evidence_list: list[str] | None = None
    confidence_scores: dict[str, float] | None = None
    conflict_flags: list[str] | None = None
    seed_terms: list[str] | None = None
    assigned_sme_id: uuid.UUID | None = None
    assigned_role: str | None = None
    status: str
    avg_confidence: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedReviewPackResponse(BaseModel):
    """Paginated response for review pack queries."""

    items: list[ReviewPackResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Decision Schemas
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    """Request body for submitting a reviewer decision."""

    element_id: str = Field(..., description="ID of the graph element being reviewed")
    action: ReviewerAction = Field(..., description="Reviewer action: confirm/correct/reject/defer")
    payload: dict[str, Any] | None = Field(None, description="Action-specific payload")


class DecisionResponse(BaseModel):
    """Response from submitting a reviewer decision."""

    decision_id: str
    action: str
    element_id: str
    graph_write_back: dict[str, Any]
    decision_at: str


class DecisionListItem(BaseModel):
    """Decision item for listing."""

    id: uuid.UUID
    engagement_id: uuid.UUID
    review_pack_id: uuid.UUID
    element_id: str
    action: str
    reviewer_id: uuid.UUID | None
    payload: dict[str, Any] | None
    graph_write_back_result: dict[str, Any] | None
    decision_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDecisionResponse(BaseModel):
    """Paginated response for decision queries."""

    items: list[DecisionListItem]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Generation Schemas
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """Request body for review pack generation."""

    pov_version_id: uuid.UUID
    engagement_id: uuid.UUID


class GenerateResponse(BaseModel):
    """Response from async review pack generation."""

    task_id: str
    status: str = "pending"
    message: str = "Review pack generation started"


# ---------------------------------------------------------------------------
# Reviewer Routing Schemas
# ---------------------------------------------------------------------------


class RoutePacksRequest(BaseModel):
    """Request body for routing review packs to reviewers."""

    engagement_id: uuid.UUID


class RoutedPackResponse(BaseModel):
    """Response showing which packs were routed to which reviewer."""

    pack_id: str
    assigned_role: str | None
    assigned_sme_id: str | None
    status: str


# ---------------------------------------------------------------------------
# Republish Schemas
# ---------------------------------------------------------------------------


class RepublishRequest(BaseModel):
    """Request body to trigger POV republish."""

    pov_version_id: uuid.UUID
    engagement_id: uuid.UUID


class RepublishResponse(BaseModel):
    """Response from POV republish."""

    new_version_id: str
    new_version_number: int
    total_elements: int
    dark_shrink_rate: float | None
    changes_summary: dict[str, int]


# ---------------------------------------------------------------------------
# Version Diff Schemas
# ---------------------------------------------------------------------------


class ElementChangeResponse(BaseModel):
    """A single element change in the diff."""

    element_id: str
    element_name: str
    change_type: str
    changed_fields: list[str] = []
    color: str = "none"
    css_class: str = "unchanged"


class VersionDiffResponse(BaseModel):
    """Structured diff between two POV versions."""

    v1_id: str
    v2_id: str
    added: list[ElementChangeResponse]
    removed: list[ElementChangeResponse]
    modified: list[ElementChangeResponse]
    unchanged_count: int
    dark_shrink_rate: float | None
    total_changes: int


# ---------------------------------------------------------------------------
# Dark-Room Shrink Rate Schemas (Story #370)
# ---------------------------------------------------------------------------


class ShrinkRateAlertResponse(BaseModel):
    """Alert included when shrink rate is below target."""

    severity: str
    message: str
    version_number: int
    actual_rate: float
    target_rate: float
    dark_segments: list[str]


class VersionShrinkResponse(BaseModel):
    """Per-version shrink rate data."""

    version_number: int
    pov_version_id: str
    dark_count: int
    dim_count: int
    bright_count: int
    total_elements: int
    reduction_pct: float | None
    snapshot_at: str


class IlluminationEventResponse(BaseModel):
    """Timeline event for a segment that was illuminated."""

    element_name: str
    element_id: str
    from_classification: str
    to_classification: str
    illuminated_in_version: int
    pov_version_id: str
    evidence_ids: list[str]


class DarkRoomDashboardResponse(BaseModel):
    """Complete dark-room shrink rate dashboard data."""

    engagement_id: str
    shrink_rate_target: float
    versions: list[VersionShrinkResponse]
    alerts: list[ShrinkRateAlertResponse]
    illumination_timeline: list[IlluminationEventResponse]


# ---------------------------------------------------------------------------
# Grading Progression Schemas (Story #357)
# ---------------------------------------------------------------------------


class VersionGradeResponse(BaseModel):
    """Per-version grade distribution data."""

    version_number: int
    pov_version_id: str
    grade_counts: dict[str, int]
    total_elements: int
    improvement_pct: float | None
    snapshot_at: str


class GradingProgressionResponse(BaseModel):
    """Complete grading progression dashboard data."""

    engagement_id: str
    improvement_target: float
    versions: list[VersionGradeResponse]
