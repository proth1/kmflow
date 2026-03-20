"""Pydantic schemas for regulatory API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models import (
    ControlEffectiveness,
    PolicyType,
)

# ---------------------------------------------------------------------------
# Policy Schemas
# ---------------------------------------------------------------------------


class PolicyCreate(BaseModel):
    """Schema for creating a policy."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    policy_type: PolicyType
    source_evidence_id: UUID | None = None
    clauses: dict[str, Any] | None = None
    description: str | None = None


class PolicyUpdate(BaseModel):
    """Schema for updating a policy (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    policy_type: PolicyType | None = None
    source_evidence_id: UUID | None = None
    clauses: dict[str, Any] | None = None
    description: str | None = None


class PolicyResponse(BaseModel):
    """Schema for policy responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    policy_type: PolicyType
    source_evidence_id: UUID | None
    clauses: dict[str, Any] | None
    description: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PolicyList(BaseModel):
    """Schema for listing policies."""

    items: list[PolicyResponse]
    total: int


# ---------------------------------------------------------------------------
# Control Schemas
# ---------------------------------------------------------------------------


class ControlCreate(BaseModel):
    """Schema for creating a control."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    effectiveness: ControlEffectiveness = ControlEffectiveness.EFFECTIVE
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    linked_policy_ids: list[str] | None = None


class ControlUpdate(BaseModel):
    """Schema for updating a control (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    effectiveness: ControlEffectiveness | None = None
    effectiveness_score: float | None = Field(None, ge=0.0, le=1.0)
    linked_policy_ids: list[str] | None = None


class ControlResponse(BaseModel):
    """Schema for control responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    description: str | None
    effectiveness: ControlEffectiveness
    effectiveness_score: float
    linked_policy_ids: list[str] | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ControlList(BaseModel):
    """Schema for listing controls."""

    items: list[ControlResponse]
    total: int


# ---------------------------------------------------------------------------
# Regulation Schemas
# ---------------------------------------------------------------------------


class RegulationCreate(BaseModel):
    """Schema for creating a regulation."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    framework: str | None = None
    jurisdiction: str | None = None
    obligations: dict[str, Any] | None = None


class RegulationUpdate(BaseModel):
    """Schema for updating a regulation (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    framework: str | None = None
    jurisdiction: str | None = None
    obligations: dict[str, Any] | None = None


class RegulationResponse(BaseModel):
    """Schema for regulation responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    framework: str | None
    jurisdiction: str | None
    obligations: dict[str, Any] | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RegulationList(BaseModel):
    """Schema for listing regulations."""

    items: list[RegulationResponse]
    total: int


# ---------------------------------------------------------------------------
# Governance Chain Schemas
# ---------------------------------------------------------------------------


class GovernanceChainLink(BaseModel):
    """A single link in the governance chain."""

    entity_id: str
    entity_type: str
    name: str
    relationship_type: str | None = None


class GovernanceChainResponse(BaseModel):
    """Response for governance chain traversal."""

    activity_id: str
    chain: list[GovernanceChainLink]
