"""Pydantic schemas for Data Processing Agreement (DPA) API routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models.gdpr import DpaStatus, LawfulBasis


class DpaCreate(BaseModel):
    """Schema for creating a DPA."""

    reference_number: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., min_length=1, max_length=32)
    effective_date: date
    controller_name: str = Field(..., min_length=1, max_length=255)
    processor_name: str = Field(..., min_length=1, max_length=255)
    data_categories: list[str] = Field(..., min_length=1)
    lawful_basis: LawfulBasis
    expiry_date: date | None = None
    sub_processors: list[dict[str, Any]] | None = None
    retention_days_override: int | None = Field(None, ge=1)
    notes: str | None = None


class DpaUpdate(BaseModel):
    """Schema for updating a DPA (PATCH). All fields optional."""

    reference_number: str | None = Field(None, min_length=1, max_length=128)
    version: str | None = Field(None, min_length=1, max_length=32)
    effective_date: date | None = None
    expiry_date: date | None = None
    controller_name: str | None = Field(None, min_length=1, max_length=255)
    processor_name: str | None = Field(None, min_length=1, max_length=255)
    data_categories: list[str] | None = None
    sub_processors: list[dict[str, Any]] | None = None
    retention_days_override: int | None = Field(None, ge=1)
    lawful_basis: LawfulBasis | None = None
    notes: str | None = None


class DpaResponse(BaseModel):
    """Full DPA response."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    reference_number: str
    version: str
    status: DpaStatus
    effective_date: date
    expiry_date: date | None = None
    controller_name: str
    processor_name: str
    data_categories: list[str]
    sub_processors: list[dict[str, Any]] | None = None
    retention_days_override: int | None = None
    lawful_basis: LawfulBasis
    notes: str | None = None
    created_by: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DpaListResponse(BaseModel):
    """Paginated list of DPAs."""

    items: list[DpaResponse]
    total: int


class DpaComplianceSummary(BaseModel):
    """Summary of DPA compliance for embedding in engagement responses."""

    status: str  # "active", "draft", "expired", "missing"
    reference_number: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    dpa_id: UUID | None = None
