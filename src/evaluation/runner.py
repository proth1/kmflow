"""Nightly evaluation orchestrator with regression detection.

Runs retrieval quality, entity extraction, and graph health evaluations,
compares against previous runs, and fires alerts on regressions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from neo4j import AsyncDriver
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.pipeline_quality import (
    EntityAnnotation,
    GoldenEvalQuery,
    GoldenEvalResult,
)
from src.evaluation.entity_evaluator import evaluate_by_entity_type
from src.evaluation.golden_dataset import list_queries
from src.evaluation.graph_health import analyze_graph_health
from src.evaluation.retrieval_evaluator import evaluate_dataset
from src.monitoring.alerting.engine import AlertEngine, AlertEvent, AlertType, Severity
from src.rag.retrieval import HybridRetriever

logger = logging.getLogger(__name__)


async def run_nightly_evaluation(
    session: AsyncSession,
    engagement_ids: list[str],
    neo4j_driver: AsyncDriver | None = None,
    alert_engine: AlertEngine | None = None,
) -> dict[str, Any]:
    """Orchestrate nightly evaluations across all given engagements.

    For each engagement, runs retrieval quality, entity extraction, and graph
    health evaluations in sequence, then checks for metric regressions against
    the most recent prior run and fires alerts when thresholds are breached.

    Args:
        session: Async SQLAlchemy session.
        engagement_ids: List of engagement ID strings to evaluate.
        neo4j_driver: Optional Neo4j driver for graph operations.
        alert_engine: Optional alert engine for regression notifications.

    Returns:
        Summary dict keyed by engagement_id with per-engagement results.
    """
    results: dict[str, Any] = {}

    for engagement_id in engagement_ids:
        engagement_result: dict[str, Any] = {
            "engagement_id": engagement_id,
            "retrieval": None,
            "entity_extraction": None,
            "graph_health": None,
            "regressions": [],
            "errors": [],
        }

        eval_run_id = uuid.uuid4()

        # ── 1. Retrieval quality ──────────────────────────────────────
        try:
            golden_queries = await list_queries(session, engagement_id=engagement_id, active_only=True)  # type: ignore[call-arg, arg-type]
            if golden_queries:
                retriever = HybridRetriever(neo4j_driver=neo4j_driver)
                retrieval_metrics = await evaluate_dataset(  # type: ignore[call-arg]
                    session=session,
                    retriever=retriever,
                    queries=golden_queries,
                    engagement_id=engagement_id,
                    eval_run_id=eval_run_id,
                )
                engagement_result["retrieval"] = retrieval_metrics
                logger.info(
                    "Retrieval eval complete for engagement %s: MRR=%.3f Recall@10=%.3f",
                    engagement_id,
                    retrieval_metrics.get("mean_mrr", 0.0),  # type: ignore[attr-defined]
                    retrieval_metrics.get("mean_recall_at_10", 0.0),  # type: ignore[attr-defined]
                )
            else:
                logger.info("No active golden queries for engagement %s — skipping retrieval eval", engagement_id)
        except Exception:  # Intentionally broad: eval sub-steps must not abort the per-engagement loop
            logger.exception("Retrieval eval failed for engagement %s", engagement_id)
            engagement_result["errors"].append("retrieval_eval_failed")

        # ── 2. Entity extraction ──────────────────────────────────────
        try:
            annotation_count_result = await session.execute(
                select(func.count(EntityAnnotation.id)).where(
                    EntityAnnotation.evidence_item_id.in_(
                        select(GoldenEvalQuery.id).where(GoldenEvalQuery.engagement_id == uuid.UUID(engagement_id))
                    )
                )
            )
            annotation_count = annotation_count_result.scalar_one_or_none() or 0

            if annotation_count > 0:
                entity_metrics = await evaluate_by_entity_type(
                    session=session,
                    engagement_id=engagement_id,  # type: ignore[arg-type]
                )
                engagement_result["entity_extraction"] = entity_metrics
                logger.info(
                    "Entity extraction eval complete for engagement %s: %d entity types evaluated",
                    engagement_id,
                    len(entity_metrics),
                )
            else:
                logger.info(
                    "No entity annotations for engagement %s — skipping entity extraction eval",
                    engagement_id,
                )
        except Exception:  # Intentionally broad: eval sub-steps must not abort the per-engagement loop
            logger.exception("Entity extraction eval failed for engagement %s", engagement_id)
            engagement_result["errors"].append("entity_eval_failed")

        # ── 3. Graph health ───────────────────────────────────────────
        try:
            graph_health = await analyze_graph_health(
                session=session,
                engagement_id=engagement_id,
                neo4j_driver=neo4j_driver,
            )
            engagement_result["graph_health"] = graph_health
            logger.info(
                "Graph health eval complete for engagement %s: orphan_nodes=%s",
                engagement_id,
                graph_health.get("orphan_node_count"),  # type: ignore[attr-defined]
            )
        except Exception:  # Intentionally broad: eval sub-steps must not abort the per-engagement loop
            logger.exception("Graph health eval failed for engagement %s", engagement_id)
            engagement_result["errors"].append("graph_health_eval_failed")

        # ── 4. Regression detection ───────────────────────────────────
        try:
            regressions = await detect_regressions(
                session=session,
                engagement_id=engagement_id,
                current_run_id=eval_run_id,
                alert_engine=alert_engine,
            )
            engagement_result["regressions"] = regressions
            if regressions:
                logger.warning(
                    "Detected %d regression(s) for engagement %s",
                    len(regressions),
                    engagement_id,
                )
        except Exception:  # Intentionally broad: eval sub-steps must not abort the per-engagement loop
            logger.exception("Regression detection failed for engagement %s", engagement_id)
            engagement_result["errors"].append("regression_detection_failed")

        results[engagement_id] = engagement_result

    return results


async def detect_regressions(
    session: AsyncSession,
    engagement_id: str,
    current_run_id: UUID,
    alert_engine: AlertEngine | None = None,
) -> list[dict[str, Any]]:
    """Compare current eval run metrics against the most recent prior run.

    Fires AlertEvents via alert_engine for any metric that exceeds a
    regression threshold. Returns a list of regression dicts describing
    what degraded.

    Thresholds:
        - MRR drop > 0.05            → HIGH
        - Recall@10 drop > 0.10      → HIGH
        - Faithfulness drop > 0.10   → CRITICAL
        - Orphan node increase > 20% → MEDIUM

    Args:
        session: Async SQLAlchemy session.
        engagement_id: Engagement to check.
        current_run_id: UUID of the just-completed eval run.
        alert_engine: Optional engine to receive AlertEvents.

    Returns:
        List of regression dicts with keys: metric, current, previous, delta, severity.
    """
    regressions: list[dict[str, Any]] = []

    current_metrics = await _aggregate_run_metrics(session, current_run_id)
    if not current_metrics:
        logger.debug("No results for current run %s — skipping regression check", current_run_id)
        return regressions

    # Find the most recent previous run for this engagement
    prev_run_row = await session.execute(
        select(GoldenEvalResult.eval_run_id)
        .where(GoldenEvalResult.engagement_id == uuid.UUID(engagement_id))
        .where(GoldenEvalResult.eval_run_id != current_run_id)
        .order_by(desc(GoldenEvalResult.created_at))
        .limit(1)
    )
    prev_run_id_row = prev_run_row.scalar_one_or_none()
    if prev_run_id_row is None:
        logger.info("No prior eval run for engagement %s — baseline not yet established", engagement_id)
        return regressions

    prev_metrics = await _aggregate_run_metrics(session, prev_run_id_row)
    if not prev_metrics:
        return regressions

    # ── Threshold definitions: (metric_key, threshold, severity, alert_type, label) ──
    thresholds: list[tuple[str, float, str, str, str]] = [
        ("mean_mrr", 0.05, Severity.HIGH, AlertType.RETRIEVAL_QUALITY_DROP, "MRR"),
        ("mean_recall_at_10", 0.10, Severity.HIGH, AlertType.RETRIEVAL_QUALITY_DROP, "Recall@10"),
        ("mean_faithfulness_score", 0.10, Severity.CRITICAL, AlertType.RETRIEVAL_QUALITY_DROP, "Faithfulness"),
    ]

    for metric_key, threshold, severity, alert_type, label in thresholds:
        current_val = current_metrics.get(metric_key)
        prev_val = prev_metrics.get(metric_key)
        if current_val is None or prev_val is None:
            continue

        delta = prev_val - current_val  # positive means drop
        if delta > threshold:
            regression = {
                "metric": metric_key,
                "label": label,
                "current": current_val,
                "previous": prev_val,
                "delta": delta,
                "threshold": threshold,
                "severity": severity,
            }
            regressions.append(regression)

            if alert_engine is not None:
                event = AlertEvent(
                    event_type=alert_type,
                    engagement_id=engagement_id,
                    severity=severity,
                    source_id=str(current_run_id),
                    description=(
                        f"{label} regression detected: {prev_val:.4f} → {current_val:.4f} "
                        f"(drop of {delta:.4f}, threshold {threshold})"
                    ),
                    metadata={
                        "metric": metric_key,
                        "current": current_val,
                        "previous": prev_val,
                        "delta": delta,
                        "eval_run_id": str(current_run_id),
                        "prev_run_id": str(prev_run_id_row),
                    },
                )
                alert_engine.process_event(event)
                logger.warning(
                    "Regression alert fired for engagement %s: %s drop=%.4f",
                    engagement_id,
                    label,
                    delta,
                )

    # ── Orphan node increase check ────────────────────────────────────
    current_orphans = current_metrics.get("orphan_node_count")
    prev_orphans = prev_metrics.get("orphan_node_count")
    if current_orphans is not None and prev_orphans is not None and prev_orphans > 0:
        pct_increase = (current_orphans - prev_orphans) / prev_orphans
        if pct_increase > 0.20:
            regression = {
                "metric": "orphan_node_count",
                "label": "Orphan Nodes",
                "current": current_orphans,
                "previous": prev_orphans,
                "delta": current_orphans - prev_orphans,
                "pct_increase": pct_increase,
                "threshold": 0.20,
                "severity": Severity.MEDIUM,
            }
            regressions.append(regression)

            if alert_engine is not None:
                event = AlertEvent(
                    event_type=AlertType.GRAPH_HEALTH_DEGRADATION,
                    engagement_id=engagement_id,
                    severity=Severity.MEDIUM,
                    source_id=str(current_run_id),
                    description=(
                        f"Orphan node count increased by {pct_increase:.1%}: {prev_orphans} → {current_orphans}"
                    ),
                    metadata={
                        "metric": "orphan_node_count",
                        "current": current_orphans,
                        "previous": prev_orphans,
                        "pct_increase": pct_increase,
                        "eval_run_id": str(current_run_id),
                        "prev_run_id": str(prev_run_id_row),
                    },
                )
                alert_engine.process_event(event)
                logger.warning(
                    "Graph health alert fired for engagement %s: orphan nodes +%.1f%%",
                    engagement_id,
                    pct_increase * 100,
                )

    return regressions


async def _aggregate_run_metrics(
    session: AsyncSession,
    eval_run_id: UUID,
) -> dict[str, float]:
    """Compute per-run mean metrics across all GoldenEvalResult rows.

    Args:
        session: Async SQLAlchemy session.
        eval_run_id: The eval run to aggregate.

    Returns:
        Dict of metric name → mean value. Empty dict if no results exist.
    """
    result = await session.execute(
        select(
            func.avg(GoldenEvalResult.mrr).label("mean_mrr"),
            func.avg(GoldenEvalResult.recall_at_10).label("mean_recall_at_10"),
            func.avg(GoldenEvalResult.precision_at_5).label("mean_precision_at_5"),
            func.avg(GoldenEvalResult.precision_at_10).label("mean_precision_at_10"),
            func.avg(GoldenEvalResult.recall_at_5).label("mean_recall_at_5"),
            func.avg(GoldenEvalResult.ndcg_at_10).label("mean_ndcg_at_10"),
            func.avg(GoldenEvalResult.faithfulness_score).label("mean_faithfulness_score"),
            func.avg(GoldenEvalResult.answer_relevance_score).label("mean_answer_relevance_score"),
            func.avg(GoldenEvalResult.hallucination_score).label("mean_hallucination_score"),
            func.count(GoldenEvalResult.id).label("result_count"),
        ).where(GoldenEvalResult.eval_run_id == eval_run_id)
    )

    row = result.one_or_none()
    if row is None or row.result_count == 0:
        return {}

    metrics: dict[str, float] = {}
    for key in (
        "mean_mrr",
        "mean_recall_at_10",
        "mean_precision_at_5",
        "mean_precision_at_10",
        "mean_recall_at_5",
        "mean_ndcg_at_10",
        "mean_faithfulness_score",
        "mean_answer_relevance_score",
        "mean_hallucination_score",
    ):
        val = getattr(row, key, None)
        if val is not None:
            metrics[key] = float(val)

    metrics["result_count"] = float(row.result_count)
    return metrics
