"""Pydantic schemas for shelf data request operations."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models.evidence import EvidenceCategory


class ShelfDataRequestItemCreate(BaseModel):
    """Schema for creating a shelf data request item."""

    category: EvidenceCategory
    item_name: str = Field(min_length=1, max_length=512)
    description: str | None = None
    priority: str = "medium"


class ShelfDataRequestCreate(BaseModel):
    """Schema for creating a shelf data request with line items."""

    engagement_id: UUID
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    due_date: date | None = None
    assigned_to: str | None = Field(default=None, max_length=255)
    items: list[ShelfDataRequestItemCreate] = Field(default_factory=list)


class ShelfDataRequestItemRead(BaseModel):
    """Schema for reading a shelf data request item."""

    id: str
    request_id: str
    category: str
    item_name: str
    description: str | None = None
    priority: str
    status: str
    matched_evidence_id: str | None = None
    received_at: str | None = None
    uploaded_by: str | None = None
    created_at: str


class ShelfDataRequestRead(BaseModel):
    """Schema for reading a shelf data request."""

    id: str
    engagement_id: str
    title: str
    description: str | None = None
    status: str
    due_date: str | None = None
    assigned_to: str | None = None
    completion_timestamp: str | None = None
    fulfillment_pct: float
    outstanding_items: list[ShelfDataRequestItemRead] = Field(default_factory=list)
    items: list[ShelfDataRequestItemRead] = Field(default_factory=list)
    created_at: str


class IntakeRequest(BaseModel):
    """Schema for matching a client upload to a request item."""

    item_id: UUID
    evidence_id: UUID
    uploaded_by: str | None = Field(default=None, max_length=255)


class FollowUpReminderRead(BaseModel):
    """Schema for reading a follow-up reminder."""

    id: str
    request_id: str
    item_id: str
    reminder_type: str
    sent_at: str
