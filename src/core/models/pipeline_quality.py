"""Pipeline quality measurement models.

Tables for pipeline stage metrics, user feedback, golden evaluation datasets,
evaluation results, entity annotations, and knowledge graph health snapshots.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PipelineStageMetric(Base):
    """Timing and throughput metrics for each pipeline stage execution."""

    __tablename__ = "pipeline_stage_metrics"
    __table_args__ = (
        Index("ix_pipeline_stage_metrics_engagement_stage", "engagement_id", "stage"),
        Index("ix_pipeline_stage_metrics_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CopilotFeedback(Base):
    """User feedback on copilot answers (thumbs up/down, corrections)."""

    __tablename__ = "copilot_feedback"
    __table_args__ = (
        Index("ix_copilot_feedback_engagement_id", "engagement_id"),
        Index("ix_copilot_feedback_copilot_message_id", "copilot_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    copilot_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("copilot_messages.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=thumbs down, 5=thumbs up
    correction_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_hallucination: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GoldenEvalQuery(Base):
    """Golden dataset queries for offline retrieval evaluation."""

    __tablename__ = "golden_eval_queries"
    __table_args__ = (Index("ix_golden_eval_queries_engagement_id", "engagement_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_source_ids: Mapped[dict] = mapped_column(JSON, nullable=False)  # list of evidence_item UUIDs
    query_type: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)  # easy/medium/hard
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # manual/correction/synthetic
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GoldenEvalResult(Base):
    """Results from a single golden query evaluation run."""

    __tablename__ = "golden_eval_results"
    __table_args__ = (
        Index("ix_golden_eval_results_eval_run_id", "eval_run_id"),
        Index("ix_golden_eval_results_query_id", "query_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("golden_eval_queries.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    precision_at_5: Mapped[float] = mapped_column(Float, nullable=False)
    precision_at_10: Mapped[float] = mapped_column(Float, nullable=False)
    recall_at_5: Mapped[float] = mapped_column(Float, nullable=False)
    recall_at_10: Mapped[float] = mapped_column(Float, nullable=False)
    mrr: Mapped[float] = mapped_column(Float, nullable=False)
    ndcg_at_10: Mapped[float] = mapped_column(Float, nullable=False)
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieved_source_ids: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    generation_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityAnnotation(Base):
    """Ground-truth entity annotations for extraction quality evaluation."""

    __tablename__ = "entity_annotations"
    __table_args__ = (Index("ix_entity_annotations_evidence_item_id", "evidence_item_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False
    )
    fragment_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annotator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GraphHealthSnapshot(Base):
    """Point-in-time snapshot of knowledge graph health metrics."""

    __tablename__ = "graph_health_snapshots"
    __table_args__ = (
        Index("ix_graph_health_snapshots_engagement_id", "engagement_id"),
        Index("ix_graph_health_snapshots_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False)
    orphan_node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    connected_components: Mapped[int] = mapped_column(Integer, nullable=False)
    largest_component_size: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_degree: Mapped[float] = mapped_column(Float, nullable=False)
    invalid_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_rel_type_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_required_props: Mapped[int] = mapped_column(Integer, nullable=False)
    nodes_by_label: Mapped[dict] = mapped_column(JSON, nullable=False)
    relationships_by_type: Mapped[dict] = mapped_column(JSON, nullable=False)
    entity_types_present: Mapped[dict] = mapped_column(JSON, nullable=False)
    entity_types_missing: Mapped[dict] = mapped_column(JSON, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    low_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
