"""Pydantic schemas for governance API routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.core.models import (
    ComplianceLevel,
    ControlEffectiveness,
    DataClassification,
    DataLayer,
)

# ---------------------------------------------------------------------------
# Catalog Schemas
# ---------------------------------------------------------------------------


class CatalogEntryCreate(BaseModel):
    """Request body for creating a catalog entry."""

    dataset_name: str
    dataset_type: str
    layer: DataLayer
    engagement_id: uuid.UUID | None = None
    schema_definition: dict[str, Any] | None = None
    owner: str | None = None
    classification: DataClassification = DataClassification.INTERNAL
    quality_sla: dict[str, Any] | None = None
    retention_days: int | None = None
    description: str | None = None


class CatalogEntryUpdate(BaseModel):
    """Request body for updating a catalog entry (all fields optional)."""

    dataset_name: str | None = None
    dataset_type: str | None = None
    layer: DataLayer | None = None
    schema_definition: dict[str, Any] | None = None
    owner: str | None = None
    classification: DataClassification | None = None
    quality_sla: dict[str, Any] | None = None
    retention_days: int | None = None
    description: str | None = None


class CatalogEntryResponse(BaseModel):
    """Response schema for a data catalog entry."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    dataset_name: str
    dataset_type: str
    layer: DataLayer
    engagement_id: uuid.UUID | None
    schema_definition: dict[str, Any] | None
    owner: str | None
    classification: DataClassification
    quality_sla: dict[str, Any] | None
    retention_days: int | None
    description: str | None
    row_count: int | None
    size_bytes: int | None
    delta_table_path: str | None
    created_at: datetime
    updated_at: datetime


class CatalogEntryList(BaseModel):
    """Response schema for listing catalog entries."""

    items: list[CatalogEntryResponse]
    total: int


# ---------------------------------------------------------------------------
# Policy Schemas
# ---------------------------------------------------------------------------


class PolicyViolationResponse(BaseModel):
    """Response schema for a single policy violation."""

    policy_name: str
    severity: str
    message: str
    entry_id: uuid.UUID


class PolicyEvaluateRequest(BaseModel):
    """Request body for policy evaluation."""

    entry_id: uuid.UUID


class PolicyEvaluateResponse(BaseModel):
    """Response schema for a policy evaluation run."""

    entry_id: uuid.UUID
    compliant: bool
    violation_count: int
    violations: list[PolicyViolationResponse]


# ---------------------------------------------------------------------------
# SLA Schemas
# ---------------------------------------------------------------------------


class SLAViolationResponse(BaseModel):
    """Response schema for a quality SLA violation."""

    metric: str
    threshold: float
    actual: float
    message: str


class SLACheckResponse(BaseModel):
    """Response schema for a quality SLA check."""

    entry_id: uuid.UUID
    passing: bool
    evidence_count: int
    checked_at: datetime
    violations: list[SLAViolationResponse]


# ---------------------------------------------------------------------------
# Migration Schemas
# ---------------------------------------------------------------------------


class MigrationResultResponse(BaseModel):
    """Response schema for a migration run."""

    engagement_id: str
    items_processed: int
    items_skipped: int
    items_failed: int
    bronze_written: int
    silver_written: int
    catalog_entries_created: int
    lineage_records_created: int
    errors: list[str]
    dry_run: bool


# ---------------------------------------------------------------------------
# Governance Health Schemas
# ---------------------------------------------------------------------------


class CatalogEntrySLAStatus(BaseModel):
    """SLA status for a single catalog entry."""

    entry_id: uuid.UUID
    name: str
    classification: str
    sla_passing: bool
    violation_count: int


class GovernanceHealthResponse(BaseModel):
    """Aggregate governance health summary for an engagement."""

    engagement_id: uuid.UUID
    total_entries: int
    passing_count: int
    failing_count: int
    compliance_percentage: float
    entries: list[CatalogEntrySLAStatus]


# ---------------------------------------------------------------------------
# Gap Detection Schemas
# ---------------------------------------------------------------------------


class GapDetectRequest(BaseModel):
    """Request body for triggering gap detection."""

    auto_generate_shelf_requests: bool = False


class GapFindingResponse(BaseModel):
    """Response for a single gap finding."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    engagement_id: uuid.UUID
    activity_id: uuid.UUID
    regulation_id: uuid.UUID | None
    gap_type: str
    severity: str
    status: str
    description: str | None
    resolved_at: datetime | None
    created_at: datetime


class GapDetectionResultResponse(BaseModel):
    """Response for a gap detection run."""

    engagement_id: uuid.UUID
    new_gaps: int
    resolved_gaps: int
    total_open: int
    findings: list[GapFindingResponse]


class GapListResponse(BaseModel):
    """Response for listing gap findings."""

    engagement_id: uuid.UUID
    findings: list[GapFindingResponse]
    total: int


# ---------------------------------------------------------------------------
# Compliance Assessment Schemas
# ---------------------------------------------------------------------------


class ComplianceAssessmentResponse(BaseModel):
    """Response for a single compliance assessment record."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    activity_id: uuid.UUID
    engagement_id: uuid.UUID
    state: ComplianceLevel
    control_coverage_percentage: float
    total_required_controls: int
    controls_with_evidence: int
    gaps: dict[str, Any] | None
    assessed_at: datetime
    assessed_by: str | None


class ComplianceTrendResponse(BaseModel):
    """Response for a compliance trend query."""

    activity_id: uuid.UUID
    assessments: list[ComplianceAssessmentResponse]
    total: int


# ---------------------------------------------------------------------------
# Control Effectiveness Scoring Schemas
# ---------------------------------------------------------------------------


class EffectivenessScoreResponse(BaseModel):
    """Response for a single effectiveness score record."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    control_id: uuid.UUID
    engagement_id: uuid.UUID
    effectiveness: ControlEffectiveness
    execution_rate: float
    evidence_source_ids: list[uuid.UUID] | None
    recommendation: str | None
    scored_at: datetime
    scored_by: str | None


class EffectivenessScoreHistoryResponse(BaseModel):
    """Response for effectiveness score history."""

    control_id: uuid.UUID
    scores: list[EffectivenessScoreResponse]
    total: int
