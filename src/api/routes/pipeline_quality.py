"""Pipeline quality dashboard API routes.

Provides endpoints for monitoring pipeline stage performance, retrieval
evaluation metrics, entity extraction quality, graph health, and copilot
satisfaction across an engagement.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.pipeline_quality import (
    DashboardResponse,
    EntitySummary,
    GraphHealthResponse,
    RetrievalSummary,
    RetrievalTrend,
    SatisfactionSummary,
    StageDetail,
    StageSummary,
)
from src.core.models import User
from src.core.models.pipeline_quality import (
    CopilotFeedback,
    EntityAnnotation,
    GoldenEvalResult,
    GraphHealthSnapshot,
    PipelineStageMetric,
)
from src.core.permissions import require_engagement_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/quality", tags=["pipeline-quality"])


# -- Helpers ------------------------------------------------------------------


def _graph_snapshot_to_dict(snap: GraphHealthSnapshot) -> dict[str, Any]:
    return {
        "id": str(snap.id),
        "engagement_id": str(snap.engagement_id),
        "node_count": snap.node_count,
        "relationship_count": snap.relationship_count,
        "orphan_node_count": snap.orphan_node_count,
        "connected_components": snap.connected_components,
        "largest_component_size": snap.largest_component_size,
        "avg_degree": snap.avg_degree,
        "invalid_label_count": snap.invalid_label_count,
        "invalid_rel_type_count": snap.invalid_rel_type_count,
        "missing_required_props": snap.missing_required_props,
        "nodes_by_label": snap.nodes_by_label,
        "relationships_by_type": snap.relationships_by_type,
        "entity_types_present": snap.entity_types_present,
        "entity_types_missing": snap.entity_types_missing,
        "avg_confidence": snap.avg_confidence,
        "low_confidence_count": snap.low_confidence_count,
        "analysis_duration_ms": snap.analysis_duration_ms,
        "created_at": snap.created_at.isoformat(),
    }


# -- Routes -------------------------------------------------------------------


@router.get("/pipeline/{engagement_id}/stages", response_model=list[StageSummary])
async def get_pipeline_stages(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get aggregated metrics for each pipeline stage in an engagement."""
    result = await session.execute(
        select(
            PipelineStageMetric.stage,
            func.count(PipelineStageMetric.id).label("execution_count"),
            func.avg(PipelineStageMetric.duration_ms).label("avg_duration_ms"),
            func.sum(PipelineStageMetric.input_count).label("total_input"),
            func.sum(PipelineStageMetric.output_count).label("total_output"),
            func.sum(PipelineStageMetric.error_count).label("total_errors"),
        )
        .where(PipelineStageMetric.engagement_id == engagement_id)
        .group_by(PipelineStageMetric.stage)
        .order_by(PipelineStageMetric.stage)
    )
    rows = result.all()

    summaries = []
    for row in rows:
        execution_count = row.execution_count or 0
        total_errors = row.total_errors or 0
        error_rate = total_errors / execution_count if execution_count > 0 else 0.0
        summaries.append(
            {
                "stage": row.stage,
                "execution_count": execution_count,
                "avg_duration_ms": round(row.avg_duration_ms or 0.0, 3),
                "total_input": row.total_input or 0,
                "total_output": row.total_output or 0,
                "total_errors": total_errors,
                "error_rate": round(error_rate, 4),
            }
        )
    return summaries


@router.get("/pipeline/{engagement_id}/stage/{stage_name}", response_model=StageDetail)
async def get_pipeline_stage_detail(
    engagement_id: UUID,
    stage_name: str,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the 100 most recent executions for a specific pipeline stage."""
    result = await session.execute(
        select(PipelineStageMetric)
        .where(
            PipelineStageMetric.engagement_id == engagement_id,
            PipelineStageMetric.stage == stage_name,
        )
        .order_by(PipelineStageMetric.started_at.desc())
        .limit(100)
    )
    metrics = list(result.scalars().all())

    return {
        "stage": stage_name,
        "executions": [
            {
                "started_at": m.started_at.isoformat(),
                "duration_ms": m.duration_ms,
                "input_count": m.input_count,
                "output_count": m.output_count,
                "error_count": m.error_count,
                "error_type": m.error_type,
            }
            for m in metrics
        ],
    }


@router.get("/retrieval/{engagement_id}/summary", response_model=RetrievalSummary)
async def get_retrieval_summary(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get aggregated retrieval metrics for the latest evaluation run."""
    # Identify the latest eval_run_id for this engagement
    latest_run_result = await session.execute(
        select(GoldenEvalResult.eval_run_id, func.max(GoldenEvalResult.created_at).label("latest"))
        .where(GoldenEvalResult.engagement_id == engagement_id)
        .group_by(GoldenEvalResult.eval_run_id)
        .order_by(func.max(GoldenEvalResult.created_at).desc())
        .limit(1)
    )
    latest_run_row = latest_run_result.first()

    if latest_run_row is None:
        return {
            "eval_run_id": None,
            "query_count": 0,
            "avg_mrr": 0.0,
            "avg_precision_at_5": 0.0,
            "avg_precision_at_10": 0.0,
            "avg_recall_at_5": 0.0,
            "avg_recall_at_10": 0.0,
            "avg_ndcg_at_10": 0.0,
            "avg_faithfulness": None,
            "avg_hallucination": None,
            "evaluated_at": None,
        }

    eval_run_id = latest_run_row.eval_run_id
    evaluated_at = latest_run_row.latest

    agg_result = await session.execute(
        select(
            func.count(GoldenEvalResult.id).label("query_count"),
            func.avg(GoldenEvalResult.mrr).label("avg_mrr"),
            func.avg(GoldenEvalResult.precision_at_5).label("avg_precision_at_5"),
            func.avg(GoldenEvalResult.precision_at_10).label("avg_precision_at_10"),
            func.avg(GoldenEvalResult.recall_at_5).label("avg_recall_at_5"),
            func.avg(GoldenEvalResult.recall_at_10).label("avg_recall_at_10"),
            func.avg(GoldenEvalResult.ndcg_at_10).label("avg_ndcg_at_10"),
            func.avg(GoldenEvalResult.faithfulness_score).label("avg_faithfulness"),
            func.avg(GoldenEvalResult.hallucination_score).label("avg_hallucination"),
        ).where(
            GoldenEvalResult.engagement_id == engagement_id,
            GoldenEvalResult.eval_run_id == eval_run_id,
        )
    )
    agg = agg_result.first()
    if agg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No evaluation results found")

    return {
        "eval_run_id": str(eval_run_id),
        "query_count": agg.query_count or 0,  # type: ignore[union-attr]
        "avg_mrr": round(agg.avg_mrr or 0.0, 4),  # type: ignore[union-attr]
        "avg_precision_at_5": round(agg.avg_precision_at_5 or 0.0, 4),  # type: ignore[union-attr]
        "avg_precision_at_10": round(agg.avg_precision_at_10 or 0.0, 4),  # type: ignore[union-attr]
        "avg_recall_at_5": round(agg.avg_recall_at_5 or 0.0, 4),  # type: ignore[union-attr]
        "avg_recall_at_10": round(agg.avg_recall_at_10 or 0.0, 4),  # type: ignore[union-attr]
        "avg_ndcg_at_10": round(agg.avg_ndcg_at_10 or 0.0, 4),  # type: ignore[union-attr]
        "avg_faithfulness": round(agg.avg_faithfulness, 4) if agg.avg_faithfulness is not None else None,  # type: ignore[union-attr]
        "avg_hallucination": round(agg.avg_hallucination, 4) if agg.avg_hallucination is not None else None,  # type: ignore[union-attr]
        "evaluated_at": evaluated_at.isoformat() if evaluated_at else None,
    }


@router.get("/retrieval/{engagement_id}/trends", response_model=list[RetrievalTrend])
async def get_retrieval_trends(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get per-run retrieval metrics for the 30 most recent evaluation runs."""
    result = await session.execute(
        select(
            GoldenEvalResult.eval_run_id,
            func.avg(GoldenEvalResult.mrr).label("avg_mrr"),
            func.avg(GoldenEvalResult.recall_at_10).label("avg_recall_at_10"),
            func.avg(GoldenEvalResult.precision_at_5).label("avg_precision_at_5"),
            func.max(GoldenEvalResult.created_at).label("evaluated_at"),
        )
        .where(GoldenEvalResult.engagement_id == engagement_id)
        .group_by(GoldenEvalResult.eval_run_id)
        .order_by(func.max(GoldenEvalResult.created_at).desc())
        .limit(30)
    )
    rows = result.all()

    return [
        {
            "eval_run_id": str(row.eval_run_id),
            "avg_mrr": round(row.avg_mrr or 0.0, 4),
            "avg_recall_at_10": round(row.avg_recall_at_10 or 0.0, 4),
            "avg_precision_at_5": round(row.avg_precision_at_5 or 0.0, 4),
            "evaluated_at": row.evaluated_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/entities/{engagement_id}/summary", response_model=EntitySummary)
async def get_entity_summary(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get entity annotation quality metrics grouped by entity type."""
    # Total and verified counts come from entity_annotations joined through evidence_items
    # EntityAnnotation has evidence_item_id → evidence_items.engagement_id
    from src.core.models import EvidenceItem  # avoid circular at module level

    total_result = await session.execute(
        select(
            func.count(EntityAnnotation.id).label("total"),
            func.sum(func.cast(EntityAnnotation.is_verified, type_=func.count(EntityAnnotation.id).type)).label(
                "verified"
            ),
        )
        .join(EvidenceItem, EntityAnnotation.evidence_item_id == EvidenceItem.id)
        .where(EvidenceItem.engagement_id == engagement_id)
    )
    totals = total_result.first()

    # Per-type breakdown
    type_result = await session.execute(
        select(
            EntityAnnotation.entity_type,
            func.count(EntityAnnotation.id).label("annotation_count"),
            func.sum(func.cast(EntityAnnotation.is_verified, type_=func.count(EntityAnnotation.id).type)).label(
                "verified_count"
            ),
        )
        .join(EvidenceItem, EntityAnnotation.evidence_item_id == EvidenceItem.id)
        .where(EvidenceItem.engagement_id == engagement_id)
        .group_by(EntityAnnotation.entity_type)
        .order_by(EntityAnnotation.entity_type)
    )
    type_rows = type_result.all()

    return {
        "total_annotations": totals.total or 0 if totals else 0,
        "total_verified": int(totals.verified or 0) if totals else 0,
        "extraction_results": [
            {
                "entity_type": row.entity_type,
                "annotation_count": row.annotation_count or 0,
                "verified_count": int(row.verified_count or 0),
            }
            for row in type_rows
        ],
    }


@router.get("/graph/{engagement_id}/health", response_model=GraphHealthResponse)
async def get_graph_health(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the most recent graph health snapshot for an engagement."""
    result = await session.execute(
        select(GraphHealthSnapshot)
        .where(GraphHealthSnapshot.engagement_id == engagement_id)
        .order_by(GraphHealthSnapshot.created_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()

    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No graph health snapshot found for this engagement",
        )

    return _graph_snapshot_to_dict(snap)


@router.get("/graph/{engagement_id}/health/trends", response_model=list[GraphHealthResponse])
async def get_graph_health_trends(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get the 30 most recent graph health snapshots for trend analysis."""
    result = await session.execute(
        select(GraphHealthSnapshot)
        .where(GraphHealthSnapshot.engagement_id == engagement_id)
        .order_by(GraphHealthSnapshot.created_at.desc())
        .limit(30)
    )
    snapshots = list(result.scalars().all())

    return [_graph_snapshot_to_dict(snap) for snap in snapshots]


@router.get("/copilot/{engagement_id}/satisfaction", response_model=SatisfactionSummary)
async def get_copilot_satisfaction(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get aggregated copilot user satisfaction metrics for an engagement."""
    result = await session.execute(
        select(
            func.count(CopilotFeedback.id).label("total_feedback"),
            func.avg(CopilotFeedback.rating).label("avg_rating"),
            func.sum(func.cast(CopilotFeedback.rating >= 4, type_=func.count(CopilotFeedback.id).type)).label(
                "thumbs_up_count"
            ),
            func.sum(func.cast(CopilotFeedback.rating <= 2, type_=func.count(CopilotFeedback.id).type)).label(
                "thumbs_down_count"
            ),
            func.sum(func.cast(CopilotFeedback.is_hallucination, type_=func.count(CopilotFeedback.id).type)).label(
                "hallucination_reports"
            ),
            func.sum(
                func.cast(CopilotFeedback.correction_text.isnot(None), type_=func.count(CopilotFeedback.id).type)
            ).label("correction_count"),
        ).where(CopilotFeedback.engagement_id == engagement_id)
    )
    row = result.first()

    if row is None or row.total_feedback == 0:
        return {
            "total_feedback": 0,
            "avg_rating": 0.0,
            "thumbs_up_count": 0,
            "thumbs_down_count": 0,
            "hallucination_reports": 0,
            "correction_count": 0,
        }

    return {
        "total_feedback": row.total_feedback or 0,
        "avg_rating": round(row.avg_rating or 0.0, 2),
        "thumbs_up_count": int(row.thumbs_up_count or 0),
        "thumbs_down_count": int(row.thumbs_down_count or 0),
        "hallucination_reports": int(row.hallucination_reports or 0),
        "correction_count": int(row.correction_count or 0),
    }


@router.get("/dashboard/{engagement_id}", response_model=DashboardResponse)
async def get_dashboard(
    engagement_id: UUID,
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a combined pipeline quality dashboard for an engagement.

    Aggregates stages, retrieval metrics, entity summary, graph health, and
    copilot satisfaction into a single response. Each section is fetched
    independently so a partial failure in one section does not break the rest.
    """
    stages: list[dict[str, Any]] = []
    retrieval: dict[str, Any] | None = None
    entities: dict[str, Any] | None = None
    graph_health: dict[str, Any] | None = None
    satisfaction: dict[str, Any] | None = None

    try:
        stages = await get_pipeline_stages(engagement_id, _engagement_user, session)
    except Exception:
        logger.exception("Dashboard: failed to fetch pipeline stages for engagement %s", engagement_id)

    try:
        retrieval = await get_retrieval_summary(engagement_id, _engagement_user, session)
    except Exception:
        logger.exception("Dashboard: failed to fetch retrieval summary for engagement %s", engagement_id)

    try:
        entities = await get_entity_summary(engagement_id, _engagement_user, session)
    except Exception:
        logger.exception("Dashboard: failed to fetch entity summary for engagement %s", engagement_id)

    try:
        graph_health = await get_graph_health(engagement_id, _engagement_user, session)
    except HTTPException:
        # 404 is expected when no snapshot exists — treat as empty, not an error
        pass
    except Exception:
        logger.exception("Dashboard: failed to fetch graph health for engagement %s", engagement_id)

    try:
        satisfaction = await get_copilot_satisfaction(engagement_id, _engagement_user, session)
    except Exception:
        logger.exception("Dashboard: failed to fetch satisfaction summary for engagement %s", engagement_id)

    return {
        "stages": stages,
        "retrieval": retrieval,
        "entities": entities,
        "graph_health": graph_health,
        "satisfaction": satisfaction,
    }
