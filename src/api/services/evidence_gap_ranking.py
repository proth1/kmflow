"""Evidence gap ranking service with confidence uplift projection.

Computes projected confidence uplift for evidence gaps, detects
cross-scenario shared gaps, and tracks projection accuracy over time.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    BrightnessClassification,
    ScenarioModification,
    SimulationScenario,
    UpliftProjection,
)

if TYPE_CHECKING:
    from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Evidence type → coverage factor (how much of the brightness gap it fills).
# Higher factor = stronger evidence, more confidence uplift.
EVIDENCE_COVERAGE_FACTORS: dict[str, float] = {
    "document": 0.25,
    "interview": 0.35,
    "system_export": 0.30,
    "observation": 0.40,
    "process_model": 0.20,
    "regulatory": 0.15,
    "survey": 0.20,
    "audit_log": 0.30,
}

# Default factor for unknown evidence types
DEFAULT_COVERAGE_FACTOR = 0.20


class EvidenceGapRankingService:
    """Computes evidence gap rankings with confidence uplift projections."""

    def __init__(
        self,
        session: AsyncSession,
        graph_service: KnowledgeGraphService | None = None,
    ) -> None:
        self._session = session
        self._graph = graph_service

    async def compute_uplift_projections(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Compute uplift projections for all Dark/Dim elements in an engagement.

        Formula: projected_confidence = current + (coverage_factor × brightness_gap)
        where brightness_gap = 1.0 - current_confidence

        Returns list of projection dicts sorted by projected_uplift descending.
        """
        # Get elements with brightness from graph
        elements = await self._get_dark_dim_elements(engagement_id)
        if not elements:
            return []

        projections: list[dict[str, Any]] = []
        for elem in elements:
            current = elem["confidence"]
            brightness = elem["brightness"]
            brightness_gap = 1.0 - current

            if brightness_gap <= 0:
                continue

            for evidence_type, factor in EVIDENCE_COVERAGE_FACTORS.items():
                uplift = round(factor * brightness_gap, 4)
                projected = round(current + uplift, 4)

                proj = {
                    "id": str(uuid.uuid4()),
                    "engagement_id": engagement_id,
                    "element_id": elem["element_id"],
                    "element_name": elem["element_name"],
                    "evidence_type": evidence_type,
                    "current_confidence": current,
                    "projected_confidence": projected,
                    "projected_uplift": uplift,
                    "brightness": brightness,
                }
                projections.append(proj)

        # Sort by uplift descending
        projections.sort(key=lambda p: p["projected_uplift"], reverse=True)
        return projections

    async def persist_projections(
        self, engagement_id: str, projections: list[dict[str, Any]]
    ) -> int:
        """Persist uplift projections to the database."""
        count = 0
        for proj in projections:
            record = UpliftProjection(
                id=uuid.UUID(proj["id"]),
                engagement_id=uuid.UUID(engagement_id),
                element_id=proj["element_id"],
                element_name=proj["element_name"],
                evidence_type=proj["evidence_type"],
                current_confidence=proj["current_confidence"],
                projected_confidence=proj["projected_confidence"],
                projected_uplift=proj["projected_uplift"],
                brightness=proj["brightness"],
            )
            self._session.add(record)
            count += 1

        await self._session.flush()
        return count

    async def get_cross_scenario_gaps(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Detect elements that appear as gaps across multiple scenarios.

        An element that is modified in multiple scenarios is a shared gap —
        fixing it improves all scenarios.
        """
        eng_uuid = uuid.UUID(engagement_id)

        # Find element_ids that appear in modifications across multiple scenarios
        subq = (
            select(
                ScenarioModification.element_id,
                ScenarioModification.element_name,
                func.count(func.distinct(ScenarioModification.scenario_id)).label("scenario_count"),
            )
            .join(
                SimulationScenario,
                SimulationScenario.id == ScenarioModification.scenario_id,
            )
            .where(SimulationScenario.engagement_id == eng_uuid)
            .group_by(ScenarioModification.element_id, ScenarioModification.element_name)
            .having(func.count(func.distinct(ScenarioModification.scenario_id)) > 1)
        )

        result = await self._session.execute(subq)
        rows = result.all()

        # For each shared gap, sum uplift projections across scenarios
        gaps: list[dict[str, Any]] = []
        for row in rows:
            # Get total projected uplift for this element
            uplift_result = await self._session.execute(
                select(func.sum(UpliftProjection.projected_uplift))
                .where(
                    UpliftProjection.engagement_id == eng_uuid,
                    UpliftProjection.element_id == row.element_id,
                )
            )
            total_uplift = uplift_result.scalar() or 0.0

            gaps.append({
                "element_id": row.element_id,
                "element_name": row.element_name,
                "scenario_count": row.scenario_count,
                "label": "improves all scenarios" if row.scenario_count >= 2 else "shared gap",
                "combined_estimated_uplift": round(total_uplift, 4),
            })

        gaps.sort(key=lambda g: g["combined_estimated_uplift"], reverse=True)
        return gaps

    async def compute_uplift_accuracy(
        self, engagement_id: str
    ) -> dict[str, Any]:
        """Compute Pearson correlation between projected and actual uplift.

        Requires minimum 10 resolved projections. Returns correlation
        coefficient and whether it meets the 0.7 target.
        """
        eng_uuid = uuid.UUID(engagement_id)

        result = await self._session.execute(
            select(UpliftProjection.projected_uplift, UpliftProjection.actual_uplift)
            .where(
                UpliftProjection.engagement_id == eng_uuid,
                UpliftProjection.actual_uplift.is_not(None),
            )
        )
        pairs = result.all()

        if len(pairs) < 10:
            return {
                "engagement_id": engagement_id,
                "resolved_count": len(pairs),
                "correlation": None,
                "meets_target": False,
                "target": 0.7,
                "insufficient_data": True,
            }

        projected = [p[0] for p in pairs]
        actual = [p[1] for p in pairs]
        correlation = self._pearson_correlation(projected, actual)

        return {
            "engagement_id": engagement_id,
            "resolved_count": len(pairs),
            "correlation": round(correlation, 4),
            "meets_target": correlation >= 0.7,
            "target": 0.7,
            "insufficient_data": False,
        }

    @staticmethod
    def _pearson_correlation(x: list[float], y: list[float]) -> float:
        """Compute Pearson correlation coefficient between two lists."""
        n = len(x)
        if n < 2:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True))
        denom_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        denom_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y)

    async def _get_dark_dim_elements(
        self, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Get Dark and Dim process elements from the graph."""
        if self._graph is None:
            return []

        query = (
            "MATCH (a:Activity) "
            "WHERE a.engagement_id = $engagement_id "
            "AND a.brightness IN $brightness_values "
            "RETURN a.id AS element_id, a.name AS element_name, "
            "a.confidence AS confidence, a.brightness AS brightness"
        )
        records = await self._graph.run_query(
            query,
            {
                "engagement_id": engagement_id,
                "brightness_values": [
                    BrightnessClassification.DARK,
                    BrightnessClassification.DIM,
                ],
            },
        )
        return [
            {
                "element_id": r["element_id"],
                "element_name": r["element_name"],
                "confidence": r.get("confidence", 0.35),
                "brightness": r.get("brightness", BrightnessClassification.DIM),
            }
            for r in records
        ]
