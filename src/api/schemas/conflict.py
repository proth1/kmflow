"""Pydantic schemas for ConflictObject CRUD operations.

Supports Story #388: Disagreement Resolution Workflow.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models.conflict import MismatchType, ResolutionStatus, ResolutionType


class ConflictObjectCreate(BaseModel):
    """Schema for creating a conflict object."""

    engagement_id: UUID
    mismatch_type: MismatchType
    source_a_id: UUID | None = None
    source_b_id: UUID | None = None
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    resolution_notes: str | None = None


class ConflictResolutionUpdate(BaseModel):
    """Schema for resolving or escalating a conflict object."""

    resolution_type: ResolutionType | None = None
    resolution_status: ResolutionStatus
    resolution_notes: str | None = None


class ConflictResolveRequest(BaseModel):
    """Schema for resolving a conflict via PATCH /api/v1/conflicts/{id}/resolve."""

    resolution_type: ResolutionType
    resolution_notes: str | None = None
    resolver_id: UUID


class ConflictAssignRequest(BaseModel):
    """Schema for assigning a conflict to an SME reviewer."""

    assigned_to: UUID


class ConflictEscalateRequest(BaseModel):
    """Schema for manually escalating a conflict."""

    escalation_notes: str | None = None


class ConflictObjectRead(BaseModel):
    """Schema for reading a conflict object."""

    id: str
    engagement_id: str
    mismatch_type: str
    resolution_type: str | None = None
    resolution_status: str
    source_a_id: str | None = None
    source_b_id: str | None = None
    severity: float
    escalation_flag: bool
    resolution_notes: str | None = None
    conflict_detail: dict[str, Any] | None = None
    resolution_details: dict[str, Any] | None = None
    resolver_id: str | None = None
    assigned_to: str | None = None
    created_at: str
    resolved_at: str | None = None


class ConflictListResponse(BaseModel):
    """Paginated response for conflict listings."""

    items: list[ConflictObjectRead]
    total: int
    limit: int
    offset: int
