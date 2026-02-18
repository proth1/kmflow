"""TOM Alignment Engine.

Implements graph traversal gap detection, embedding-based deviation scoring,
maturity scoring, and gap prioritization for TOM alignment analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    GapAnalysisResult,
    ProcessMaturity,
    TargetOperatingModel,
    TOMDimension,
    TOMGapType,
)
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Dimension weights for gap prioritization
DIMENSION_WEIGHTS: dict[str, float] = {
    TOMDimension.PROCESS_ARCHITECTURE: 1.0,
    TOMDimension.PEOPLE_AND_ORGANIZATION: 0.9,
    TOMDimension.TECHNOLOGY_AND_DATA: 0.85,
    TOMDimension.GOVERNANCE_STRUCTURES: 0.95,
    TOMDimension.PERFORMANCE_MANAGEMENT: 0.7,
    TOMDimension.RISK_AND_COMPLIANCE: 1.0,
}

# Maturity level numeric values for scoring
MATURITY_SCORES: dict[str, float] = {
    ProcessMaturity.INITIAL: 1.0,
    ProcessMaturity.MANAGED: 2.0,
    ProcessMaturity.DEFINED: 3.0,
    ProcessMaturity.QUANTITATIVELY_MANAGED: 4.0,
    ProcessMaturity.OPTIMIZING: 5.0,
}


@dataclass
class AlignmentResult:
    """Result of a TOM alignment analysis.

    Attributes:
        engagement_id: The engagement analyzed.
        tom_id: The TOM compared against.
        gaps: List of detected gaps.
        maturity_scores: Per-dimension maturity scores.
        overall_alignment: Overall alignment percentage (0-100).
    """

    engagement_id: str = ""
    tom_id: str = ""
    gaps: list[dict[str, Any]] = field(default_factory=list)
    maturity_scores: dict[str, float] = field(default_factory=dict)
    overall_alignment: float = 0.0


class TOMAlignmentEngine:
    """Engine for TOM alignment analysis.

    Compares current-state process knowledge against target operating
    model specifications to detect gaps and score maturity.
    """

    def __init__(self, graph_service: KnowledgeGraphService) -> None:
        self._graph = graph_service

    async def run_alignment(
        self,
        session: AsyncSession,
        engagement_id: str,
        tom_id: str,
    ) -> AlignmentResult:
        """Run full TOM alignment analysis.

        1. Fetch TOM specifications
        2. Query current-state graph for each dimension
        3. Detect gaps between target and current state
        4. Score maturity per dimension
        5. Prioritize gaps

        Args:
            session: Database session.
            engagement_id: The engagement to analyze.
            tom_id: The TOM to compare against.

        Returns:
            AlignmentResult with gaps and maturity scores.
        """
        result = AlignmentResult(engagement_id=engagement_id, tom_id=tom_id)

        # Fetch TOM
        tom_result = await session.execute(select(TargetOperatingModel).where(TargetOperatingModel.id == tom_id))
        tom = tom_result.scalar_one_or_none()
        if not tom:
            logger.warning("TOM %s not found", tom_id)
            return result

        # Get graph stats to assess current state
        stats = await self._graph.get_stats(engagement_id)

        # Assess each dimension
        for dimension in TOMDimension:
            target = (tom.maturity_targets or {}).get(dimension, "defined")
            current_score = self._assess_dimension_maturity(dimension, stats)
            target_score = MATURITY_SCORES.get(target, 3.0)

            result.maturity_scores[dimension] = current_score

            gap_type = self._classify_gap(current_score, target_score)
            if gap_type != TOMGapType.NO_GAP:
                severity = self._calculate_severity(current_score, target_score)
                confidence = min(0.5 + stats.node_count * 0.01, 1.0)
                priority = self.calculate_priority(severity, confidence, dimension)

                result.gaps.append(
                    {
                        "dimension": dimension,
                        "gap_type": gap_type,
                        "current_maturity": current_score,
                        "target_maturity": target_score,
                        "severity": severity,
                        "confidence": confidence,
                        "priority_score": priority,
                    }
                )

        # Calculate overall alignment
        if result.maturity_scores:
            total_target = sum(
                MATURITY_SCORES.get((tom.maturity_targets or {}).get(d, "defined"), 3.0) for d in TOMDimension
            )
            total_current = sum(result.maturity_scores.values())
            result.overall_alignment = round(min(total_current / total_target * 100, 100), 2) if total_target > 0 else 0

        return result

    async def persist_gaps(
        self,
        session: AsyncSession,
        alignment_result: AlignmentResult,
    ) -> list[GapAnalysisResult]:
        """Persist gap analysis results to the database.

        Args:
            session: Database session.
            alignment_result: Result from run_alignment().

        Returns:
            List of persisted GapAnalysisResult records.
        """
        persisted: list[GapAnalysisResult] = []
        for gap_data in alignment_result.gaps:
            gap = GapAnalysisResult(
                engagement_id=alignment_result.engagement_id,
                tom_id=alignment_result.tom_id,
                gap_type=gap_data["gap_type"],
                dimension=gap_data["dimension"],
                severity=gap_data["severity"],
                confidence=gap_data["confidence"],
                rationale=f"Current maturity {gap_data['current_maturity']:.1f} vs target {gap_data['target_maturity']:.1f}",
                recommendation=self._generate_recommendation(gap_data["dimension"], gap_data["gap_type"]),
            )
            session.add(gap)
            persisted.append(gap)

        await session.flush()
        return persisted

    def _assess_dimension_maturity(
        self,
        dimension: str,
        stats: Any,
    ) -> float:
        """Assess current maturity for a TOM dimension based on graph evidence.

        Uses heuristics based on graph node/relationship density.

        Args:
            dimension: The TOM dimension to assess.
            stats: Graph statistics for the engagement.

        Returns:
            Maturity score (1.0-5.0).
        """
        node_count = stats.node_count

        # Base score from evidence density
        if node_count == 0:
            return 1.0
        elif node_count < 10:
            base = 1.5
        elif node_count < 50:
            base = 2.5
        elif node_count < 100:
            base = 3.5
        else:
            base = 4.0

        # Dimension-specific adjustments
        if dimension == TOMDimension.PROCESS_ARCHITECTURE:
            process_count = stats.nodes_by_label.get("Process", 0) + stats.nodes_by_label.get("Activity", 0)
            if process_count > 20:
                base = min(base + 0.5, 5.0)
        elif dimension == TOMDimension.GOVERNANCE_STRUCTURES:
            policy_count = stats.nodes_by_label.get("Policy", 0)
            if policy_count > 5:
                base = min(base + 0.5, 5.0)
        elif dimension == TOMDimension.TECHNOLOGY_AND_DATA:
            system_count = stats.nodes_by_label.get("System", 0)
            if system_count > 5:
                base = min(base + 0.5, 5.0)

        return round(base, 1)

    def _classify_gap(self, current: float, target: float) -> str:
        """Classify the gap type based on current vs target maturity."""
        diff = target - current
        if diff <= 0:
            return TOMGapType.NO_GAP
        elif diff < 1.0:
            return TOMGapType.DEVIATION
        elif diff < 2.0:
            return TOMGapType.PARTIAL_GAP
        else:
            return TOMGapType.FULL_GAP

    def _calculate_severity(self, current: float, target: float) -> float:
        """Calculate gap severity as normalized difference."""
        diff = target - current
        return round(min(diff / 4.0, 1.0), 4)

    @staticmethod
    def calculate_priority(severity: float, confidence: float, dimension: str) -> float:
        """Calculate gap priority score.

        Formula: severity * confidence * dimension_weight

        Args:
            severity: Gap severity (0-1).
            confidence: Detection confidence (0-1).
            dimension: TOM dimension for weighting.

        Returns:
            Priority score (0-1).
        """
        weight = DIMENSION_WEIGHTS.get(dimension, 0.8)
        return round(severity * confidence * weight, 4)

    def _generate_recommendation(self, dimension: str, gap_type: str) -> str:
        """Generate a recommendation based on gap type and dimension."""
        recommendations = {
            TOMDimension.PROCESS_ARCHITECTURE: "Map and document process flows; implement standard process notation",
            TOMDimension.PEOPLE_AND_ORGANIZATION: "Define roles and responsibilities; establish training programs",
            TOMDimension.TECHNOLOGY_AND_DATA: "Assess technology stack; implement data governance framework",
            TOMDimension.GOVERNANCE_STRUCTURES: "Establish governance committees; define decision-making frameworks",
            TOMDimension.PERFORMANCE_MANAGEMENT: "Define KPIs and SLAs; implement monitoring dashboards",
            TOMDimension.RISK_AND_COMPLIANCE: "Conduct risk assessment; implement control framework",
        }
        base = recommendations.get(TOMDimension(dimension), "Conduct detailed assessment")
        if gap_type == TOMGapType.FULL_GAP:
            return f"CRITICAL: {base}"
        elif gap_type == TOMGapType.PARTIAL_GAP:
            return f"HIGH: {base}"
        return base
