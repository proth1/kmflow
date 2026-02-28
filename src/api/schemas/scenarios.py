"""Pydantic schemas for Scenario Comparison Workbench CRUD (Story #373)."""

from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models import ModificationType


class ScenarioStatus(enum.StrEnum):
    """Lifecycle status for a scenario in the Comparison Workbench."""

    DRAFT = "draft"
    SIMULATED = "simulated"
    ARCHIVED = "archived"


# -- Scenario Schemas ---------------------------------------------------------


class ScenarioCreatePayload(BaseModel):
    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None


class ScenarioSummary(BaseModel):
    id: str
    engagement_id: str
    name: str
    description: str | None = None
    status: str
    modification_count: int
    created_at: str


class ScenarioDetail(ScenarioSummary):
    modifications: list[ModificationDetail] = []
    updated_at: str | None = None


class ScenarioListResponse(BaseModel):
    items: list[ScenarioSummary]
    total: int


# -- Modification Schemas -----------------------------------------------------


class ModificationCreatePayload(BaseModel):
    modification_type: ModificationType
    element_id: str = Field(..., min_length=1, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict)


class ModificationDetail(BaseModel):
    id: str
    scenario_id: str
    modification_type: str
    element_id: str
    payload: dict[str, Any] | None = None
    applied_at: str


class ModificationListResponse(BaseModel):
    items: list[ModificationDetail]
    total: int


# Forward-reference resolution
ScenarioDetail.model_rebuild()
