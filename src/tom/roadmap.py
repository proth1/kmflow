"""Transformation Roadmap Generator.

Generates 4-phase transformation roadmaps from gap analysis results,
prioritizing quick wins and high-impact improvements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import GapAnalysisResult, TOMGapType

logger = logging.getLogger(__name__)


@dataclass
class RoadmapPhase:
    """A phase in the transformation roadmap.

    Attributes:
        phase_number: Phase sequence (1-4).
        name: Phase name.
        duration_months: Estimated duration in months.
        initiatives: List of initiatives in this phase.
        dependencies: IDs of initiatives this phase depends on.
    """

    phase_number: int = 1
    name: str = ""
    duration_months: int = 3
    initiatives: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class TransformationRoadmap:
    """A complete transformation roadmap.

    Attributes:
        engagement_id: The engagement this roadmap is for.
        tom_id: The target TOM.
        phases: The 4 transformation phases.
        total_initiatives: Total initiative count.
        estimated_duration_months: Total estimated duration.
    """

    engagement_id: str = ""
    tom_id: str = ""
    phases: list[RoadmapPhase] = field(default_factory=list)
    total_initiatives: int = 0
    estimated_duration_months: int = 0


class RoadmapGenerator:
    """Generator for transformation roadmaps from gap analysis results.

    Organizes gaps into 4 phases:
    1. Quick Wins (low effort, high impact)
    2. Foundation (structural changes)
    3. Transformation (major capability building)
    4. Optimization (continuous improvement)
    """

    async def generate_roadmap(
        self,
        session: AsyncSession,
        engagement_id: str,
        tom_id: str,
    ) -> TransformationRoadmap:
        """Generate a transformation roadmap from gap analysis results.

        Args:
            session: Database session.
            engagement_id: The engagement to generate for.
            tom_id: The TOM to align to.

        Returns:
            TransformationRoadmap with 4 phases.
        """
        # Fetch gap results
        gaps = await self._fetch_gaps(session, engagement_id, tom_id)

        roadmap = TransformationRoadmap(
            engagement_id=engagement_id,
            tom_id=tom_id,
        )

        # Categorize gaps into phases
        phase_1_gaps, phase_2_gaps, phase_3_gaps, phase_4_gaps = self._categorize_gaps(gaps)

        roadmap.phases = [
            RoadmapPhase(
                phase_number=1,
                name="Quick Wins",
                duration_months=3,
                initiatives=self._gaps_to_initiatives(phase_1_gaps),
            ),
            RoadmapPhase(
                phase_number=2,
                name="Foundation Building",
                duration_months=6,
                initiatives=self._gaps_to_initiatives(phase_2_gaps),
                dependencies=["phase_1"],
            ),
            RoadmapPhase(
                phase_number=3,
                name="Transformation",
                duration_months=9,
                initiatives=self._gaps_to_initiatives(phase_3_gaps),
                dependencies=["phase_2"],
            ),
            RoadmapPhase(
                phase_number=4,
                name="Optimization",
                duration_months=6,
                initiatives=self._gaps_to_initiatives(phase_4_gaps),
                dependencies=["phase_3"],
            ),
        ]

        roadmap.total_initiatives = sum(len(p.initiatives) for p in roadmap.phases)
        roadmap.estimated_duration_months = sum(p.duration_months for p in roadmap.phases)

        return roadmap

    def _categorize_gaps(
        self,
        gaps: list[GapAnalysisResult],
    ) -> tuple[list[GapAnalysisResult], list[GapAnalysisResult], list[GapAnalysisResult], list[GapAnalysisResult]]:
        """Categorize gaps into 4 phases based on type and priority."""
        phase_1: list[GapAnalysisResult] = []  # Quick wins: deviations
        phase_2: list[GapAnalysisResult] = []  # Foundation: partial gaps
        phase_3: list[GapAnalysisResult] = []  # Transformation: full gaps
        phase_4: list[GapAnalysisResult] = []  # Optimization: remaining

        for gap in gaps:
            if gap.gap_type == TOMGapType.NO_GAP:
                continue
            elif gap.gap_type == TOMGapType.DEVIATION:
                phase_1.append(gap)
            elif gap.gap_type == TOMGapType.PARTIAL_GAP:
                if gap.priority_score > 0.5:
                    phase_2.append(gap)
                else:
                    phase_4.append(gap)
            elif gap.gap_type == TOMGapType.FULL_GAP:
                phase_3.append(gap)

        return phase_1, phase_2, phase_3, phase_4

    def _gaps_to_initiatives(self, gaps: list[GapAnalysisResult]) -> list[dict[str, Any]]:
        """Convert gap results to initiative descriptions."""
        initiatives = []
        for gap in gaps:
            initiatives.append(
                {
                    "gap_id": str(gap.id),
                    "dimension": str(gap.dimension),
                    "gap_type": str(gap.gap_type),
                    "severity": gap.severity,
                    "priority_score": gap.priority_score,
                    "recommendation": gap.recommendation or "Assessment needed",
                }
            )
        return sorted(initiatives, key=lambda x: x["priority_score"], reverse=True)

    async def _fetch_gaps(
        self,
        session: AsyncSession,
        engagement_id: str,
        tom_id: str,
    ) -> list[GapAnalysisResult]:
        """Fetch gap analysis results for a TOM."""
        result = await session.execute(
            select(GapAnalysisResult)
            .where(GapAnalysisResult.engagement_id == engagement_id)
            .where(GapAnalysisResult.tom_id == tom_id)
        )
        return list(result.scalars().all())
