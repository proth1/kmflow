"""Pydantic schemas for TOM (Target Operating Model) routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models import (
    ProcessMaturity,
    TOMDimension,
    TOMGapType,
)


class DimensionInput(BaseModel):
    """Schema for a single TOM dimension input."""

    dimension_type: TOMDimension
    maturity_target: int = Field(..., ge=1, le=5)
    description: str | None = None


class TOMCreate(BaseModel):
    """Schema for creating a target operating model."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


class TOMUpdate(BaseModel):
    """Schema for updating a TOM (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


class DimensionResponse(BaseModel):
    """Schema for a TOM dimension in responses."""

    model_config = {"from_attributes": True}

    dimension_type: TOMDimension
    maturity_target: int
    description: str | None


class TOMResponse(BaseModel):
    """Schema for TOM responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    version: int
    dimensions: list[DimensionResponse] | None = None
    maturity_targets: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class TOMList(BaseModel):
    """Schema for listing TOMs."""

    items: list[TOMResponse]
    total: int


class TOMVersionResponse(BaseModel):
    """Schema for a TOM version history entry."""

    model_config = {"from_attributes": True}

    version_number: int
    snapshot: dict[str, Any]
    changed_by: str | None
    created_at: datetime


class TOMVersionList(BaseModel):
    """Schema for listing TOM versions."""

    tom_id: UUID
    current_version: int
    versions: list[TOMVersionResponse]


class GapCreate(BaseModel):
    """Schema for creating a gap analysis result."""

    engagement_id: UUID
    tom_id: UUID
    gap_type: TOMGapType
    dimension: TOMDimension
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str | None = None
    recommendation: str | None = None
    business_criticality: int | None = Field(None, ge=1, le=5)
    risk_exposure: int | None = Field(None, ge=1, le=5)
    regulatory_impact: int | None = Field(None, ge=1, le=5)
    remediation_cost: int | None = Field(None, ge=1, le=5)


class GapResponse(BaseModel):
    """Schema for gap analysis result responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    tom_id: UUID
    gap_type: TOMGapType
    dimension: TOMDimension
    severity: float
    confidence: float
    rationale: str | None
    recommendation: str | None
    priority_score: float
    composite_score: float
    business_criticality: int | None
    risk_exposure: int | None
    regulatory_impact: int | None
    remediation_cost: int | None
    created_at: datetime


class GapList(BaseModel):
    """Schema for listing gap results."""

    items: list[GapResponse]
    total: int


class BestPracticeCreate(BaseModel):
    """Schema for creating a best practice."""

    title: str = Field("", max_length=512)
    domain: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    description: str
    source: str | None = None
    tom_dimension: TOMDimension
    maturity_level_applicable: int | None = Field(None, ge=1, le=5)


class BestPracticeResponse(BaseModel):
    """Schema for best practice responses."""

    model_config = {"from_attributes": True}

    id: UUID
    title: str
    domain: str
    industry: str
    description: str
    source: str | None
    tom_dimension: TOMDimension
    maturity_level_applicable: int | None
    created_at: datetime


class BenchmarkCreate(BaseModel):
    """Schema for creating a benchmark."""

    metric_name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    p25: float
    p50: float
    p75: float
    p90: float
    source: str | None = None


class BenchmarkResponse(BaseModel):
    """Schema for benchmark responses."""

    model_config = {"from_attributes": True}

    id: UUID
    metric_name: str
    industry: str
    p25: float
    p50: float
    p75: float
    p90: float
    source: str | None
    created_at: datetime


class TOMImport(BaseModel):
    """Schema for importing a TOM."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    dimensions: list[DimensionInput] | None = None
    maturity_targets: dict[str, Any] | None = None


class RationaleResponse(BaseModel):
    """Response for a single gap rationale generation."""

    gap_id: UUID
    rationale: str
    recommendation: str


class BulkRationaleResponse(BaseModel):
    """Response for bulk rationale generation."""

    engagement_id: UUID
    gaps_processed: int
    results: list[RationaleResponse]


class BestPracticeList(BaseModel):
    """Schema for listing best practices."""

    items: list[BestPracticeResponse]
    total: int


class BenchmarkList(BaseModel):
    """Schema for listing benchmarks."""

    items: list[BenchmarkResponse]
    total: int


class SeedResponse(BaseModel):
    """Schema for seed operation response."""

    best_practices_seeded: int
    benchmarks_seeded: int


class AlignmentResponse(BaseModel):
    """Schema for alignment analysis response."""

    engagement_id: str
    tom_id: str
    overall_alignment: float
    maturity_scores: dict[str, float]
    gaps_detected: int
    gaps_persisted: int
    gaps: list[dict[str, Any]]


class MaturityScoresResponse(BaseModel):
    """Schema for maturity scores response."""

    engagement_id: str
    maturity_scores: dict[str, float]


class PrioritizedGapsResponse(BaseModel):
    """Schema for prioritized gaps response."""

    engagement_id: str
    gaps: list[dict[str, Any]]
    total: int


class ConformanceDeviationResponse(BaseModel):
    """Schema for a single conformance deviation."""

    element_name: str
    deviation_type: str
    severity: float
    description: str


class ConformanceCheckResponse(BaseModel):
    """Schema for conformance check response."""

    pov_model_id: str
    reference_model_id: str
    fitness_score: float
    matching_elements: int
    total_reference_elements: int
    deviations: list[ConformanceDeviationResponse]


class ConformanceModelSummary(BaseModel):
    """Schema for a model in the conformance summary."""

    id: str
    scope: str
    confidence_score: float
    element_count: int


class ConformanceSummaryResponse(BaseModel):
    """Schema for conformance summary response."""

    engagement_id: str
    completed_models: int
    models: list[ConformanceModelSummary]


class RoadmapPhaseResponse(BaseModel):
    """Schema for a roadmap phase."""

    phase_number: int
    name: str
    duration_months: int
    initiative_count: int
    initiatives: list[dict[str, Any]]


class RoadmapResponse(BaseModel):
    """Schema for roadmap generation response."""

    engagement_id: str
    tom_id: str
    total_initiatives: int
    estimated_duration_months: int
    phases: list[RoadmapPhaseResponse]


class RoadmapSummaryResponse(BaseModel):
    """Schema for roadmap summary response."""

    engagement_id: str
    total_gaps: int
    gaps_by_dimension: dict[str, int]


class GapCountByType(BaseModel):
    """Gap count for a specific gap type, broken down by severity buckets."""

    gap_type: str
    total: int
    critical: int
    high: int
    medium: int
    low: int


class DimensionAlignmentScore(BaseModel):
    """Alignment score for a single TOM dimension."""

    dimension: str
    score: float
    below_threshold: bool


class RecommendationEntry(BaseModel):
    """A prioritized recommendation from gap analysis."""

    gap_id: str
    title: str
    gap_type: str
    dimension: str
    severity: float
    priority_score: float
    recommendation: str | None
    rationale: str | None


class GapDashboardResponse(BaseModel):
    """Aggregated gap analysis dashboard data."""

    engagement_id: str
    total_gaps: int
    gap_counts: list[GapCountByType]
    dimension_scores: list[DimensionAlignmentScore]
    recommendations: list[RecommendationEntry]
    maturity_heatmap: dict[str, dict[str, int]]


class PercentileRankingResponse(BaseModel):
    """Percentile ranking of a client metric against industry benchmarks."""

    metric_name: str
    client_value: float
    percentile: float
    percentile_label: str
    distribution: dict[str, float]


class BenchmarkRankingResponse(BaseModel):
    """Response containing one or more percentile rankings."""

    engagement_id: str
    rankings: list[PercentileRankingResponse]


class PracticeMatchResponse(BaseModel):
    """A best practice matched to a gap finding."""

    practice_id: str
    practice_title: str
    practice_domain: str
    practice_industry: str
    gap_id: str
    relevance_score: float
    match_reason: str


class GapRecommendationsResponse(BaseModel):
    """Recommendations for a gap finding."""

    gap_id: str
    gap_dimension: str
    recommendations: list[PracticeMatchResponse]


class MaturityComputeRequest(BaseModel):
    """Request body for computing maturity scores."""

    governance_map: dict[str, dict[str, Any]] | None = None


class MaturityScoreResponse(BaseModel):
    """Response for a single maturity score."""

    model_config = {"from_attributes": True}

    id: UUID
    process_model_id: UUID
    process_area_name: str
    maturity_level: ProcessMaturity
    level_number: int
    evidence_dimensions: dict[str, Any] | None
    recommendations: list[str] | None
    scored_at: datetime


class MaturityComputeResponse(BaseModel):
    """Response for a batch maturity computation."""

    engagement_id: UUID
    scores_computed: int
    scores: list[MaturityScoreResponse]


class MaturityHeatmapEntry(BaseModel):
    """A single entry in the maturity heatmap."""

    process_model_id: UUID
    process_area_name: str
    maturity_level: ProcessMaturity
    level_number: int


class MaturityHeatmapResponse(BaseModel):
    """Full maturity heatmap response."""

    engagement_id: UUID
    process_areas: list[MaturityHeatmapEntry]
    overall_engagement_maturity: float
    process_area_count: int


class AlignmentRunTriggerResponse(BaseModel):
    """Response for triggering an alignment scoring run."""

    run_id: UUID
    status: str
    message: str


class AlignmentResultEntry(BaseModel):
    """A single per-activity, per-dimension alignment result."""

    model_config = {"from_attributes": True}

    id: UUID
    activity_id: UUID
    dimension_type: TOMDimension
    gap_type: TOMGapType
    deviation_score: float
    alignment_evidence: dict[str, Any] | None


class AlignmentRunResultsResponse(BaseModel):
    """Paginated results for an alignment run."""

    run_id: UUID
    status: str
    items: list[AlignmentResultEntry]
    total: int


class RoadmapRecommendationDetail(BaseModel):
    """A recommendation within a roadmap phase."""

    gap_id: str
    title: str
    dimension: str
    gap_type: str
    composite_score: float
    effort_weeks: float
    remediation_cost: int
    rationale_summary: str
    depends_on: list[str] = Field(default_factory=list)


class PrioritizedPhaseResponse(BaseModel):
    """A phase in the prioritized roadmap."""

    phase_number: int
    name: str
    duration_weeks_estimate: int
    recommendation_count: int
    recommendation_ids: list[str]
    recommendations: list[RoadmapRecommendationDetail]


class PrioritizedRoadmapResponse(BaseModel):
    """Full prioritized roadmap response."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    status: str
    total_initiatives: int
    estimated_duration_weeks: int
    phases: list[PrioritizedPhaseResponse]
    generated_at: datetime


class GenerateRoadmapResponse(BaseModel):
    """Response for roadmap generation."""

    roadmap_id: UUID
    engagement_id: UUID
    status: str
    total_initiatives: int
    estimated_duration_weeks: int
    phase_count: int
