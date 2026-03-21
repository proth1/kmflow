"""Pydantic schemas for dashboard API routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Core Dashboard Schemas
# ---------------------------------------------------------------------------


class GapCountBySeverity(BaseModel):
    """Gap counts grouped by severity."""

    high: int = 0
    medium: int = 0
    low: int = 0


class RecentActivityEntry(BaseModel):
    """A recent audit log entry."""

    id: str
    action: str
    actor: str
    details: str | None = None
    created_at: datetime | None = None


class DashboardResponse(BaseModel):
    """Aggregated engagement dashboard data."""

    engagement_id: str
    engagement_name: str
    evidence_coverage_pct: float = Field(..., description="Overall evidence coverage percentage (0-100)")
    overall_confidence: float = Field(..., description="Overall confidence score from latest POV (0.0-1.0)")
    gap_counts: GapCountBySeverity
    evidence_item_count: int
    process_model_count: int
    recent_activity: list[RecentActivityEntry]


class CategoryCoverage(BaseModel):
    """Evidence coverage for a single category."""

    category: str
    requested_count: int
    received_count: int
    coverage_pct: float = Field(..., description="Coverage percentage for this category (0-100)")
    below_threshold: bool = Field(default=False, description="True if coverage is below 50%")


class EvidenceCoverageResponse(BaseModel):
    """Detailed evidence coverage breakdown."""

    engagement_id: str
    overall_coverage_pct: float
    categories: list[CategoryCoverage]


class ConfidenceBucket(BaseModel):
    """Element count for a confidence level."""

    level: str
    min_score: float
    max_score: float
    count: int


class WeakElement(BaseModel):
    """A process element with low confidence."""

    id: str
    name: str
    element_type: str
    confidence_score: float


class ConfidenceDistributionResponse(BaseModel):
    """Confidence distribution across process elements."""

    engagement_id: str
    model_id: str | None = None
    overall_confidence: float
    distribution: list[ConfidenceBucket]
    weakest_elements: list[WeakElement]


# ---------------------------------------------------------------------------
# Persona Dashboard Schemas
# ---------------------------------------------------------------------------


class BrightnessDistribution(BaseModel):
    """Brightness distribution across process elements."""

    bright_pct: float = Field(0.0, description="Percentage of BRIGHT elements")
    dim_pct: float = Field(0.0, description="Percentage of DIM elements")
    dark_pct: float = Field(0.0, description="Percentage of DARK elements")
    total_elements: int = 0


class TOMAlignmentEntry(BaseModel):
    """TOM alignment score for a single dimension."""

    dimension: str
    alignment_pct: float = Field(..., description="Alignment percentage (0-100)")


class EngagementLeadDashboard(BaseModel):
    """Full KPI dashboard for Engagement Lead persona."""

    engagement_id: str
    evidence_coverage_pct: float
    overall_confidence: float
    brightness_distribution: BrightnessDistribution
    tom_alignment: list[TOMAlignmentEntry]
    gap_counts: GapCountBySeverity
    seed_list_coverage_pct: float
    dark_room_shrink_rate: float


class ProcessingStatusCounts(BaseModel):
    """Evidence processing status counts."""

    pending: int = 0
    validated: int = 0
    active: int = 0
    expired: int = 0
    archived: int = 0


class ConflictQueueItem(BaseModel):
    """A conflict object in the resolution queue."""

    id: str
    mismatch_type: str
    severity: float
    resolution_status: str
    created_at: datetime | None = None


class ProcessAnalystDashboard(BaseModel):
    """Dashboard for Process Analyst persona."""

    engagement_id: str
    processing_status: ProcessingStatusCounts
    relationship_mapping_pct: float
    conflict_queue: list[ConflictQueueItem]
    total_conflicts: int
    unresolved_conflicts: int


class DecisionHistoryItem(BaseModel):
    """A validation decision in SME history."""

    id: str
    decision: str
    created_at: datetime | None = None


class SmeDashboard(BaseModel):
    """Dashboard for SME persona."""

    engagement_id: str
    pending_review_count: int
    total_annotation_count: int
    confidence_impact: float
    decision_history: list[DecisionHistoryItem]


class GapFindingSummary(BaseModel):
    """Gap finding for client view (no internal scores)."""

    id: str
    gap_type: str
    dimension: str
    recommendation: str | None = None


class ClientStakeholderDashboard(BaseModel):
    """Read-only dashboard for Client Stakeholder persona."""

    engagement_id: str
    overall_confidence: float
    brightness_distribution: BrightnessDistribution
    gap_findings: list[GapFindingSummary]
    total_recommendations: int
