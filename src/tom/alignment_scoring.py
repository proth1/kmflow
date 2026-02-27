"""Per-activity TOM alignment scoring service.

Scores each process activity against each TOM dimension using:
1. Graph traversal: ALIGNS_TO edges → NO_GAP
2. Embedding similarity: cosine similarity → FULL_GAP / PARTIAL_GAP / NO_GAP

Thresholds (configurable):
  >= 0.85 → NO_GAP
  0.4 <= x < 0.85 → PARTIAL_GAP (deviation_score = 1.0 - similarity)
  < 0.4  → FULL_GAP (deviation_score = 1.0)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models import (
    AlignmentRunStatus,
    ProcessElement,
    ProcessElementType,
    ProcessModel,
    ProcessModelStatus,
    TargetOperatingModel,
    TOMAlignmentResult,
    TOMAlignmentRun,
    TOMDimension,
    TOMGapType,
)

logger = logging.getLogger(__name__)

# Similarity thresholds
THRESHOLD_NO_GAP = 0.85
THRESHOLD_PARTIAL_GAP = 0.40


@dataclass
class ActivityScore:
    """A single per-activity, per-dimension alignment score."""

    activity_id: str
    activity_name: str
    dimension_type: TOMDimension
    gap_type: TOMGapType
    deviation_score: float
    alignment_evidence: dict[str, Any] = field(default_factory=dict)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def classify_similarity(similarity: float) -> tuple[TOMGapType, float]:
    """Classify similarity score into gap type and deviation score.

    Returns:
        (gap_type, deviation_score) tuple.
    """
    if similarity >= THRESHOLD_NO_GAP:
        return TOMGapType.NO_GAP, 0.0
    elif similarity >= THRESHOLD_PARTIAL_GAP:
        return TOMGapType.PARTIAL_GAP, round(1.0 - similarity, 4)
    else:
        return TOMGapType.FULL_GAP, 1.0


class AlignmentScoringService:
    """Scores process activities against TOM dimensions.

    Uses graph traversal for ALIGNS_TO edges and embedding similarity
    as a fallback for unlinked activities.
    """

    def __init__(
        self,
        graph_service: Any,
        embedding_service: Any | None = None,
    ) -> None:
        self._graph = graph_service
        self._embedding = embedding_service

    async def run_scoring(
        self,
        session: AsyncSession,
        run: TOMAlignmentRun,
    ) -> list[TOMAlignmentResult]:
        """Execute alignment scoring for a run.

        Fetches activities from the latest POV, TOM dimensions from the TOM,
        then scores each activity against each applicable dimension.

        Args:
            session: Database session.
            run: The alignment run record (status will be updated).

        Returns:
            List of persisted TOMAlignmentResult records.
        """
        run.status = AlignmentRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await session.flush()

        try:
            results = await self._score_activities(session, run)
            run.status = AlignmentRunStatus.COMPLETE
            run.completed_at = datetime.now(UTC)
            return results
        except Exception as exc:
            logger.exception("Alignment run %s failed", run.id)
            run.status = AlignmentRunStatus.FAILED
            run.completed_at = datetime.now(UTC)
            # Store only the exception class name to avoid leaking internal details
            run.error_message = f"Scoring failed: {type(exc).__name__}"
            raise

    async def _score_activities(
        self,
        session: AsyncSession,
        run: TOMAlignmentRun,
    ) -> list[TOMAlignmentResult]:
        """Core scoring logic."""
        # Fetch latest completed POV for the engagement
        pov_result = await session.execute(
            select(ProcessModel)
            .where(
                ProcessModel.engagement_id == run.engagement_id,
                ProcessModel.status == ProcessModelStatus.COMPLETED,
            )
            .order_by(ProcessModel.version.desc())
            .limit(1)
        )
        pov = pov_result.scalar_one_or_none()
        if not pov:
            logger.warning("No completed POV for engagement %s", run.engagement_id)
            return []

        # Fetch activities from the POV
        activities_result = await session.execute(
            select(ProcessElement).where(
                ProcessElement.model_id == pov.id,
                ProcessElement.element_type == ProcessElementType.ACTIVITY,
            )
        )
        activities = list(activities_result.scalars().all())
        if not activities:
            return []

        # Fetch TOM with dimension records
        tom_result = await session.execute(
            select(TargetOperatingModel)
            .where(TargetOperatingModel.id == run.tom_id)
            .options(selectinload(TargetOperatingModel.dimension_records))
        )
        tom = tom_result.scalar_one_or_none()
        if not tom:
            return []

        # Check graph for ALIGNS_TO edges
        aligned_pairs = await self._get_aligned_pairs(str(run.engagement_id))

        # Get TOM dimension descriptions for embedding comparison
        dim_descriptions = {}
        for dr in (tom.dimension_records or []):
            if dr.description:
                dim_descriptions[dr.dimension_type] = dr.description

        # Generate embeddings if service available and needed
        activity_embeddings: dict[str, list[float]] = {}
        dim_embeddings: dict[str, list[float]] = {}
        if self._embedding and dim_descriptions:
            activity_texts = [a.name for a in activities]
            dim_texts = list(dim_descriptions.values())
            all_texts = activity_texts + dim_texts

            if all_texts:
                all_embs = await self._embedding.embed_texts_async(all_texts)
                for i, act in enumerate(activities):
                    activity_embeddings[str(act.id)] = all_embs[i]
                for i, dim_type in enumerate(dim_descriptions.keys()):
                    dim_embeddings[dim_type] = all_embs[len(activity_texts) + i]

        # Score each activity against each dimension
        results: list[TOMAlignmentResult] = []
        for activity in activities:
            for dimension in TOMDimension:
                score = self._score_single(
                    activity=activity,
                    dimension=dimension,
                    aligned_pairs=aligned_pairs,
                    activity_emb=activity_embeddings.get(str(activity.id)),
                    dim_emb=dim_embeddings.get(dimension),
                    dim_description=dim_descriptions.get(dimension),
                )

                result = TOMAlignmentResult(
                    run_id=run.id,
                    activity_id=activity.id,
                    dimension_type=score.dimension_type,
                    gap_type=score.gap_type,
                    deviation_score=score.deviation_score,
                    alignment_evidence=score.alignment_evidence,
                )
                session.add(result)
                results.append(result)

        await session.flush()
        return results

    def _score_single(
        self,
        *,
        activity: ProcessElement,
        dimension: TOMDimension,
        aligned_pairs: set[tuple[str, str]],
        activity_emb: list[float] | None,
        dim_emb: list[float] | None,
        dim_description: str | None,
    ) -> ActivityScore:
        """Score a single activity against a single dimension."""
        activity_id_str = str(activity.id)

        # Check graph alignment first
        if (activity_id_str, dimension) in aligned_pairs:
            return ActivityScore(
                activity_id=activity_id_str,
                activity_name=activity.name,
                dimension_type=dimension,
                gap_type=TOMGapType.NO_GAP,
                deviation_score=0.0,
                alignment_evidence={"method": "graph_alignment", "edge_type": "ALIGNS_TO"},
            )

        # Fall back to embedding similarity
        if activity_emb and dim_emb:
            similarity = cosine_similarity(activity_emb, dim_emb)
            gap_type, deviation_score = classify_similarity(similarity)
            return ActivityScore(
                activity_id=activity_id_str,
                activity_name=activity.name,
                dimension_type=dimension,
                gap_type=gap_type,
                deviation_score=deviation_score,
                alignment_evidence={
                    "method": "embedding_similarity",
                    "similarity_score": round(similarity, 4),
                    "activity_description": activity.name,
                    "tom_specification": dim_description or "",
                },
            )

        # No embedding available → FULL_GAP by default
        return ActivityScore(
            activity_id=activity_id_str,
            activity_name=activity.name,
            dimension_type=dimension,
            gap_type=TOMGapType.FULL_GAP,
            deviation_score=1.0,
            alignment_evidence={"method": "no_data", "reason": "No embedding or graph alignment available"},
        )

    async def _get_aligned_pairs(self, engagement_id: str) -> set[tuple[str, str]]:
        """Query graph for ALIGNS_TO edges in the engagement.

        Returns a set of (activity_id, dimension) tuples that are aligned.
        """
        try:
            query = (
                "MATCH (a)-[:ALIGNS_TO]->(t) "
                "WHERE a.engagement_id = $engagement_id "
                "RETURN a.id AS activity_id, t.dimension AS dimension"
            )
            records = await self._graph.run_query(query, {"engagement_id": engagement_id})
            return {
                (r["activity_id"], r["dimension"])
                for r in records
                if r.get("activity_id") and r.get("dimension")
            }
        except Exception:
            logger.warning("Failed to query ALIGNS_TO edges for engagement %s", engagement_id)
            return set()
