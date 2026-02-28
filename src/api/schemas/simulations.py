"""Pydantic schemas for simulation API routes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.models import (
    FinancialAssumptionType,
    ModificationType,
    SimulationType,
    SuggestionDisposition,
)

# -- Scenario Schemas ---------------------------------------------------------


class ScenarioCreate(BaseModel):
    engagement_id: UUID
    process_model_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=512)
    simulation_type: SimulationType
    parameters: dict[str, Any] | None = None
    description: str | None = None


class ScenarioResponse(BaseModel):
    id: str
    engagement_id: str
    process_model_id: str | None = None
    name: str
    simulation_type: str
    parameters: dict[str, Any] | None = None
    description: str | None = None
    status: str | None = None
    evidence_confidence_score: float | None = None
    created_at: str


class ScenarioList(BaseModel):
    items: list[ScenarioResponse]
    total: int


# -- Simulation Result Schemas ------------------------------------------------


class SimulationResultResponse(BaseModel):
    id: str
    scenario_id: str
    status: str
    metrics: dict[str, Any] | None = None
    impact_analysis: dict[str, Any] | None = None
    recommendations: list[str] | None = None
    execution_time_ms: int
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class SimulationResultList(BaseModel):
    items: list[SimulationResultResponse]
    total: int


# -- Modification Schemas -----------------------------------------------------


class ModificationCreate(BaseModel):
    modification_type: ModificationType
    element_id: str = Field(..., min_length=1, max_length=512)
    element_name: str = Field(..., min_length=1, max_length=512)
    change_data: dict[str, Any] | None = None
    template_key: str | None = None


class ModificationResponse(BaseModel):
    id: str
    scenario_id: str
    modification_type: str
    element_id: str
    element_name: str
    change_data: dict[str, Any] | None = None
    template_key: str | None = None
    applied_at: str


class ModificationList(BaseModel):
    items: list[ModificationResponse]
    total: int


# -- Coverage Schemas ---------------------------------------------------------


class ElementCoverageResponse(BaseModel):
    element_id: str
    element_name: str
    classification: str
    evidence_count: int
    confidence: float
    is_added: bool = False
    is_removed: bool = False
    is_modified: bool = False


class ScenarioCoverageResponse(BaseModel):
    scenario_id: str
    elements: list[ElementCoverageResponse]
    bright_count: int
    dim_count: int
    dark_count: int
    aggregate_confidence: float


# -- Comparison Schemas -------------------------------------------------------


class ScenarioComparisonEntry(BaseModel):
    scenario_id: str
    scenario_name: str
    deltas: dict[str, Any] | None = None
    assessment: str | None = None
    coverage_summary: dict[str, int] | None = None


class ScenarioComparisonResponse(BaseModel):
    baseline_id: str
    baseline_name: str
    comparisons: list[ScenarioComparisonEntry]


# -- Epistemic Plan Schemas ---------------------------------------------------


class EpistemicActionResponse(BaseModel):
    target_element_id: str
    target_element_name: str
    evidence_gap_description: str
    current_confidence: float
    estimated_confidence_uplift: float
    projected_confidence: float
    information_gain_score: float
    recommended_evidence_category: str
    priority: str
    shelf_request_id: str | None = None


class EpistemicPlanAggregates(BaseModel):
    total: int
    high_priority_count: int
    estimated_aggregate_uplift: float


class EpistemicPlanResponse(BaseModel):
    scenario_id: str
    actions: list[EpistemicActionResponse]
    aggregated_view: EpistemicPlanAggregates


# -- Financial Assumption Schemas ---------------------------------------------


class FinancialAssumptionCreate(BaseModel):
    engagement_id: UUID
    assumption_type: FinancialAssumptionType
    name: str = Field(..., min_length=1, max_length=256)
    value: float
    unit: str = Field(..., min_length=1, max_length=50)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_evidence_id: UUID | None = None
    notes: str | None = None


class FinancialAssumptionResponse(BaseModel):
    id: str
    engagement_id: str
    assumption_type: str
    name: str
    value: float
    unit: str
    confidence: float
    source_evidence_id: str | None = None
    notes: str | None = None
    created_at: str


class FinancialAssumptionListResponse(BaseModel):
    items: list[FinancialAssumptionResponse]
    total: int


# -- Suggestion Schemas -------------------------------------------------------


class SuggestionCreate(BaseModel):
    context_notes: str | None = None


class SuggestionResponse(BaseModel):
    id: str
    scenario_id: str
    suggestion_text: str
    rationale: str
    governance_flags: dict[str, Any] | None = None
    evidence_gaps: dict[str, Any] | None = None
    disposition: str
    disposition_notes: str | None = None
    created_at: str


class SuggestionListResponse(BaseModel):
    items: list[SuggestionResponse]
    total: int


class SuggestionDispositionUpdate(BaseModel):
    disposition: SuggestionDisposition
    disposition_notes: str | None = None
    modified_content: dict[str, Any] | None = None
    rejection_reason: str | None = None


# -- Financial Impact Schemas -------------------------------------------------


class CostRange(BaseModel):
    optimistic: float
    expected: float
    pessimistic: float


class SensitivityEntry(BaseModel):
    assumption_name: str
    base_value: float
    impact_range: CostRange


class FinancialImpactResponse(BaseModel):
    scenario_id: str
    cost_range: CostRange
    sensitivity_analysis: list[SensitivityEntry]
    assumption_count: int
    delta_vs_baseline: float | None = None


# -- Ranking Schemas ----------------------------------------------------------


class ScenarioRankEntry(BaseModel):
    scenario_id: str
    scenario_name: str
    composite_score: float
    evidence_score: float
    simulation_score: float
    financial_score: float
    governance_score: float


class ScenarioRankResponse(BaseModel):
    engagement_id: str
    rankings: list[ScenarioRankEntry]
    weights: dict[str, float]
