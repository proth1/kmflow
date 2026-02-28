"""Pydantic schemas for the Correlation Engine API routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CorrelationLinkRequest(BaseModel):
    """Trigger a full correlation run for an engagement."""

    engagement_id: UUID


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CorrelationLinkResponse(BaseModel):
    """Summary of a completed correlation run."""

    engagement_id: UUID
    links_created: int
    deterministic_count: int
    assisted_count: int
    role_aggregate_count: int
    unlinked_count: int


class CaseLinkResponse(BaseModel):
    """Single CaseLinkEdge record."""

    id: UUID
    engagement_id: UUID
    event_id: UUID
    case_id: str
    method: str
    confidence: float
    explainability: dict[str, Any] | None = None
    created_at: datetime


class CaseLinkListResponse(BaseModel):
    """Paginated list of CaseLinkEdge records."""

    items: list[CaseLinkResponse]
    total: int


class UnlinkedEventResponse(BaseModel):
    """A canonical event that has no case link."""

    id: UUID
    engagement_id: UUID
    case_id: str
    activity_name: str
    timestamp_utc: datetime
    source_system: str
    performer_role_ref: str | None = None
    confidence_score: float


class UnlinkedEventListResponse(BaseModel):
    """Paginated list of unlinked events."""

    items: list[UnlinkedEventResponse]
    total: int


class DiagnosticsResponse(BaseModel):
    """Daily correlation quality report."""

    date: str
    engagement_id: str
    total_events: int
    linked_events: int
    linked_pct: float
    confidence_distribution: dict[str, int]
    non_linkage_causes: list[dict[str, Any]]
    uncertainty_items: list[dict[str, Any]]
