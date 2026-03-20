"""Pydantic schemas for pipeline quality API routes."""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Pipeline Stage Schemas
# ---------------------------------------------------------------------------


class StageSummary(BaseModel):
    """Aggregated metrics for a pipeline stage."""

    stage: str
    execution_count: int
    avg_duration_ms: float
    total_input: int
    total_output: int
    total_errors: int
    error_rate: float


class StageExecution(BaseModel):
    """A single pipeline stage execution record."""

    started_at: str
    duration_ms: float
    input_count: int
    output_count: int
    error_count: int
    error_type: str | None


class StageDetail(BaseModel):
    """Stage name and its recent executions."""

    stage: str
    executions: list[StageExecution]


# ---------------------------------------------------------------------------
# Retrieval Evaluation Schemas
# ---------------------------------------------------------------------------


class RetrievalSummary(BaseModel):
    """Aggregated retrieval evaluation metrics for the latest eval run."""

    eval_run_id: str | None
    query_count: int
    avg_mrr: float
    avg_precision_at_5: float
    avg_precision_at_10: float
    avg_recall_at_5: float
    avg_recall_at_10: float
    avg_ndcg_at_10: float
    avg_faithfulness: float | None
    avg_hallucination: float | None
    evaluated_at: str | None


class RetrievalTrend(BaseModel):
    """Per-run aggregated retrieval metrics for trend charting."""

    eval_run_id: str
    avg_mrr: float
    avg_recall_at_10: float
    avg_precision_at_5: float
    evaluated_at: str


# ---------------------------------------------------------------------------
# Entity Annotation Schemas
# ---------------------------------------------------------------------------


class EntityTypeStats(BaseModel):
    """Extraction stats for a single entity type."""

    entity_type: str
    annotation_count: int
    verified_count: int


class EntitySummary(BaseModel):
    """Aggregated entity annotation quality metrics."""

    total_annotations: int
    total_verified: int
    extraction_results: list[EntityTypeStats]


# ---------------------------------------------------------------------------
# Graph Health Schema
# ---------------------------------------------------------------------------


class GraphHealthResponse(BaseModel):
    """Graph health snapshot fields."""

    id: str
    engagement_id: str
    node_count: int
    relationship_count: int
    orphan_node_count: int
    connected_components: int
    largest_component_size: int
    avg_degree: float
    invalid_label_count: int
    invalid_rel_type_count: int
    missing_required_props: int
    nodes_by_label: dict
    relationships_by_type: dict
    entity_types_present: dict
    entity_types_missing: dict
    avg_confidence: float
    low_confidence_count: int
    analysis_duration_ms: float
    created_at: str


# ---------------------------------------------------------------------------
# Copilot Satisfaction Schema
# ---------------------------------------------------------------------------


class SatisfactionSummary(BaseModel):
    """Aggregated copilot user satisfaction metrics."""

    total_feedback: int
    avg_rating: float
    thumbs_up_count: int
    thumbs_down_count: int
    hallucination_reports: int
    correction_count: int


# ---------------------------------------------------------------------------
# Combined Dashboard Schema
# ---------------------------------------------------------------------------


class DashboardResponse(BaseModel):
    """Combined pipeline quality dashboard response."""

    stages: list[StageSummary]
    retrieval: RetrievalSummary | None
    entities: EntitySummary | None
    graph_health: GraphHealthResponse | None
    satisfaction: SatisfactionSummary | None
