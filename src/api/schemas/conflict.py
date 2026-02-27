"""Pydantic schemas for ConflictObject CRUD operations."""

from __future__ import annotations

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
    created_at: str
    resolved_at: str | None = None
