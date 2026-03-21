"""Pydantic schemas for POV (Process Point of View) routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.pov.orchestrator import TOTAL_STEPS


class POVGenerateRequest(BaseModel):
    """Request to trigger POV generation."""

    engagement_id: str = Field(..., description="Engagement UUID")
    scope: str = Field(default="all", description="Scope filter for evidence")
    generated_by: str = Field(default="consensus_algorithm", description="Generator identifier")


class POVGenerateResponse(BaseModel):
    """Response for POV generation trigger."""

    job_id: str
    status: str
    message: str


class ProcessModelResponse(BaseModel):
    """Response schema for a process model."""

    model_config = {"from_attributes": True}

    id: str
    engagement_id: str
    version: int
    scope: str
    status: str
    confidence_score: float
    bpmn_xml: str | None = None
    element_count: int
    evidence_count: int
    contradiction_count: int
    metadata_json: dict | None = None
    generated_at: datetime | None = None
    generated_by: str


class ProcessElementResponse(BaseModel):
    """Response schema for a process element."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    element_type: str
    name: str
    confidence_score: float
    triangulation_score: float
    corroboration_level: str
    evidence_count: int
    evidence_ids: list[str] | None = None
    metadata_json: dict | None = None


class ProcessElementList(BaseModel):
    """Paginated list of process elements."""

    items: list[ProcessElementResponse]
    total: int


class ContradictionResponse(BaseModel):
    """Response schema for a contradiction."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    element_name: str
    field_name: str
    values: list[dict[str, str]] | None = None
    resolution_value: str | None = None
    resolution_reason: str | None = None
    evidence_ids: list[str] | None = None


class EvidenceGapResponse(BaseModel):
    """Response schema for an evidence gap."""

    model_config = {"from_attributes": True}

    id: str
    model_id: str
    gap_type: str
    description: str
    severity: str
    recommendation: str | None = None
    related_element_id: str | None = None


class ProcessElementDetailResponse(BaseModel):
    """Detailed response for a process element including brightness and grade."""

    id: str
    model_id: str
    element_type: str
    name: str
    confidence_score: float
    triangulation_score: float
    corroboration_level: str
    evidence_count: int
    evidence_ids: list[str] | None = None
    evidence_grade: str = "U"
    brightness_classification: str = "dark"
    mvc_threshold_passed: bool = False
    metadata_json: dict | None = None


class ElementEvidenceItem(BaseModel):
    """An evidence item linked to a process element."""

    id: str
    title: str
    category: str
    grade: str
    source: str | None = None
    created_at: str | None = None


class ElementEvidenceResponse(BaseModel):
    """Response for element-level evidence query."""

    element_id: str
    element_name: str
    evidence_items: list[ElementEvidenceItem]
    total: int


class EngagementBPMNResponse(BaseModel):
    """Response for engagement-scoped latest BPMN model."""

    engagement_id: str
    model_id: str
    version: int
    bpmn_xml: str
    confidence_score: float
    element_count: int
    elements: list[ProcessElementDetailResponse]


class DashboardKPIs(BaseModel):
    """Dashboard KPIs for an engagement's process model."""

    engagement_id: str
    model_version: int
    overall_confidence: float
    element_count: int
    brightness_distribution: dict[str, int]
    brightness_percentages: dict[str, float]
    evidence_coverage: float
    gap_count: int
    critical_gap_count: int


class EvidenceMapEntry(BaseModel):
    """An entry in the evidence-to-element mapping."""

    evidence_id: str
    element_names: list[str]
    element_ids: list[str]


class BPMNResponse(BaseModel):
    """Response containing BPMN XML and element confidence metadata."""

    model_id: str
    bpmn_xml: str
    element_confidences: dict[str, float] = {}


class JobStatusResponse(BaseModel):
    """Response for job status check."""

    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class ProgressResponse(BaseModel):
    """Response for POV generation progress tracking."""

    task_id: str
    status: str
    current_step: int
    step_name: str
    completion_percentage: int
    total_steps: int = TOTAL_STEPS
    completed_steps: list[dict[str, Any]] | None = None
    failed_step: dict[str, Any] | None = None
    total_duration_ms: int = 0


class VersionSummary(BaseModel):
    """Summary of a single POV version."""

    model_id: str
    version: int
    status: str
    confidence_score: float
    element_count: int
    generated_at: datetime | None = None


class VersionDiffResponse(BaseModel):
    """Version diff between two POV generations."""

    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    unchanged_count: int = 0
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []


class VersionHistoryResponse(BaseModel):
    """Response for version history listing."""

    engagement_id: str
    versions: list[VersionSummary]
    total_versions: int
    diff: VersionDiffResponse | None = None


class ElementConfidenceEntry(BaseModel):
    """Confidence data for a single process element."""

    score: float
    brightness: str
    grade: str


class ConfidenceMapResponse(BaseModel):
    """Map of element_id to confidence data for heatmap rendering."""

    engagement_id: str
    model_version: int
    elements: dict[str, ElementConfidenceEntry]
    total_elements: int


class ConfidenceSummaryResponse(BaseModel):
    """Summary statistics of confidence distribution."""

    engagement_id: str
    model_version: int
    total_elements: int
    bright_count: int
    bright_percentage: float
    dim_count: int
    dim_percentage: float
    dark_count: int
    dark_percentage: float
    overall_confidence: float


class ReverseElementEntry(BaseModel):
    """A process element that references a given evidence item."""

    element_id: str
    element_name: str
    element_type: str
    confidence_score: float
    brightness_classification: str


class ReverseEvidenceLookupResponse(BaseModel):
    """Process elements that reference a specific evidence item."""

    evidence_id: str
    elements: list[ReverseElementEntry]
    total: int


class DarkElementEntry(BaseModel):
    """A dark (unsupported) process element."""

    element_id: str
    element_name: str
    element_type: str
    confidence_score: float
    evidence_count: int
    suggested_actions: list[str]


class DarkElementsResponse(BaseModel):
    """List of process elements with no supporting evidence."""

    engagement_id: str
    model_version: int
    dark_elements: list[DarkElementEntry]
    total: int


class MissingFormEntry(BaseModel):
    """A missing knowledge form entry in a dark segment."""

    form_number: int
    form_name: str
    recommended_probes: list[str]
    probe_type: str


class DarkSegmentEntry(BaseModel):
    """A single Dark Room backlog entry."""

    element_id: str
    element_name: str
    current_confidence: float
    brightness: str
    estimated_confidence_uplift: float
    missing_knowledge_forms: list[MissingFormEntry]
    missing_form_count: int
    covered_form_count: int


class DarkRoomResponse(BaseModel):
    """Response for the Dark Room backlog."""

    engagement_id: str
    dark_threshold: float
    total_count: int
    items: list[DarkSegmentEntry]


class IlluminationActionEntry(BaseModel):
    """A single illumination action."""

    id: str
    element_id: str
    element_name: str
    action_type: str
    target_knowledge_form: int
    target_form_name: str
    status: str
    linked_item_id: str | None = None


class IlluminationPlanResponse(BaseModel):
    """Response for creating an illumination plan."""

    engagement_id: str
    element_id: str
    actions_created: int
    actions: list[IlluminationActionEntry]


class IlluminationProgressResponse(BaseModel):
    """Response for illumination progress."""

    engagement_id: str
    element_id: str
    total_actions: int
    completed_actions: int
    pending_actions: int
    in_progress_actions: int
    all_complete: bool
    actions: list[dict]


class ActionStatusUpdateRequest(BaseModel):
    """Request to update an illumination action's status."""

    status: Literal["pending", "in_progress", "complete"]
    linked_item_id: str | None = None


class ActionStatusUpdateResponse(BaseModel):
    """Response after updating an action's status."""

    id: str
    element_id: str
    action_type: str
    target_knowledge_form: int
    status: str
    linked_item_id: str | None = None


class SegmentCompletionResponse(BaseModel):
    """Response for segment completion check."""

    element_id: str
    all_complete: bool
    total_actions: int
    completed_actions: int
    should_recalculate: bool
