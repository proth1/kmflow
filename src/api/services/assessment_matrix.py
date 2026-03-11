"""Assessment Overlay Matrix computation service.

Computes composite Value and Ability-to-Execute scores for each process area
within an engagement, using data from process models, compliance assessments,
maturity scores, and simulation results.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.assessment_matrix import AssessmentMatrixEntry, Quadrant
from src.core.models.governance import ComplianceAssessment
from src.core.models.pov import ProcessElement, ProcessModel
from src.core.models.simulation import SimulationResult, SimulationScenario, SimulationStatus
from src.core.models.tom import MaturityScore, TargetOperatingModel, TOMDimensionRecord

logger = logging.getLogger(__name__)

# Quadrant thresholds (both axes are 0-100)
QUADRANT_VALUE_THRESHOLD = 50.0
QUADRANT_ABILITY_THRESHOLD = 50.0

# Axis component weights
VALUE_WEIGHTS = {
    "volume_impact": 0.30,
    "cost_savings_potential": 0.30,
    "risk_reduction": 0.25,
    "strategic_alignment": 0.15,
}

ABILITY_WEIGHTS = {
    "process_maturity": 0.30,
    "evidence_confidence": 0.30,
    "compliance_readiness": 0.20,
    "resource_availability": 0.20,
}


def classify_quadrant(value: float, ability: float) -> Quadrant:
    """Classify a point into one of four quadrants."""
    if value >= QUADRANT_VALUE_THRESHOLD and ability >= QUADRANT_ABILITY_THRESHOLD:
        return Quadrant.TRANSFORM
    elif value >= QUADRANT_VALUE_THRESHOLD and ability < QUADRANT_ABILITY_THRESHOLD:
        return Quadrant.INVEST
    elif value < QUADRANT_VALUE_THRESHOLD and ability >= QUADRANT_ABILITY_THRESHOLD:
        return Quadrant.MAINTAIN
    else:
        return Quadrant.DEPRIORITIZE


class AssessmentMatrixService:
    """Computes and persists assessment matrix entries for an engagement."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_matrix(self, engagement_id: uuid.UUID) -> list[dict[str, Any]]:
        """Compute assessment matrix from existing engagement data.

        Groups process elements by their top-level activity names (process areas),
        then scores each area on both axes using available data.

        Returns list of entry dicts (also persisted to DB).
        """
        # 1. Load process elements grouped by process area
        process_areas = await self._load_process_areas(engagement_id)
        if not process_areas:
            return []

        # 2. Load supporting data
        maturity_scores = await self._load_maturity_scores(engagement_id)
        compliance_data = await self._load_compliance_data(engagement_id)
        simulation_metrics = await self._load_simulation_metrics(engagement_id)

        # 3. Compute scores for each process area
        entries: list[dict[str, Any]] = []
        for area_name, elements in process_areas.items():
            value_components = self._compute_value_components(elements, simulation_metrics)
            ability_components = self._compute_ability_components(elements, maturity_scores, compliance_data)

            value_score = sum(value_components.get(k, 0.0) * w for k, w in VALUE_WEIGHTS.items())
            ability_score = sum(ability_components.get(k, 0.0) * w for k, w in ABILITY_WEIGHTS.items())

            # Clamp to 0-100
            value_score = max(0.0, min(100.0, value_score))
            ability_score = max(0.0, min(100.0, ability_score))

            quadrant = classify_quadrant(value_score, ability_score)

            entries.append(
                {
                    "process_area_name": area_name,
                    "value_score": round(value_score, 2),
                    "ability_to_execute": round(ability_score, 2),
                    "quadrant": quadrant,
                    "value_components": {k: round(v, 2) for k, v in value_components.items()},
                    "ability_components": {k: round(v, 2) for k, v in ability_components.items()},
                    "element_count": len(elements),
                }
            )

        # 4. Persist entries (upsert)
        await self._persist_entries(engagement_id, entries)

        return entries

    async def get_matrix(self, engagement_id: uuid.UUID) -> list[dict[str, Any]]:
        """Load existing matrix entries for an engagement."""
        stmt = (
            select(AssessmentMatrixEntry)
            .where(AssessmentMatrixEntry.engagement_id == engagement_id)
            .order_by(AssessmentMatrixEntry.value_score.desc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [self._entry_to_dict(row) for row in rows]

    # ── Data Loading ─────────────────────────────────────────────────────

    async def _load_process_areas(self, engagement_id: uuid.UUID) -> dict[str, list[ProcessElement]]:
        """Load process elements grouped by top-level activity (process area)."""
        stmt = (
            select(ProcessElement)
            .join(ProcessModel, ProcessElement.model_id == ProcessModel.id)
            .where(
                ProcessModel.engagement_id == engagement_id,
                ProcessElement.element_type.in_(["ACTIVITY", "GATEWAY", "EVENT"]),
            )
        )
        result = await self._session.execute(stmt)
        elements = result.scalars().all()

        areas: dict[str, list[ProcessElement]] = {}
        for elem in elements:
            # Group by element name prefix (first word or full name for activities)
            area_name = elem.name if elem.element_type == "ACTIVITY" else "Supporting"
            areas.setdefault(area_name, []).append(elem)

        return areas

    async def _load_maturity_scores(self, engagement_id: uuid.UUID) -> dict[str, float]:
        """Load latest maturity scores keyed by dimension type."""
        stmt = (
            select(TOMDimensionRecord.dimension_type, MaturityScore.overall_maturity)
            .join(TargetOperatingModel, TOMDimensionRecord.tom_id == TargetOperatingModel.id)
            .outerjoin(
                MaturityScore,
                MaturityScore.engagement_id == TargetOperatingModel.engagement_id,
            )
            .where(TargetOperatingModel.engagement_id == engagement_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: float(row[1] or 0) for row in result.all()}

    async def _load_compliance_data(self, engagement_id: uuid.UUID) -> dict[str, float]:
        """Load average compliance coverage per activity."""
        stmt = (
            select(
                ComplianceAssessment.activity_id,
                sa_func.avg(ComplianceAssessment.control_coverage_percentage),
            )
            .where(ComplianceAssessment.engagement_id == engagement_id)
            .group_by(ComplianceAssessment.activity_id)
        )
        result = await self._session.execute(stmt)
        return {str(row[0]): float(row[1] or 0) for row in result.all()}

    async def _load_simulation_metrics(self, engagement_id: uuid.UUID) -> dict[str, dict[str, float]]:
        """Load simulation result metrics keyed by scenario name."""
        stmt = (
            select(SimulationScenario.name, SimulationResult.metrics)
            .join(SimulationResult, SimulationResult.scenario_id == SimulationScenario.id)
            .where(
                SimulationScenario.engagement_id == engagement_id,
                SimulationResult.status == SimulationStatus.COMPLETED,
            )
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] or {} for row in result.all()}

    # ── Scoring ──────────────────────────────────────────────────────────

    def _compute_value_components(
        self,
        elements: list[ProcessElement],
        simulation_metrics: dict[str, dict[str, float]],
    ) -> dict[str, float]:
        """Compute value axis components (0-100 each)."""
        # Volume impact: derived from element count (proxy for process complexity/volume)
        element_count = len(elements)
        volume_impact = min(100.0, element_count * 15.0)

        # Cost savings potential: from simulation metrics if available
        cost_savings = 50.0  # Default midpoint
        if simulation_metrics:
            avg_fte_delta = sum(abs(m.get("fte_delta", 0)) for m in simulation_metrics.values()) / max(
                len(simulation_metrics), 1
            )
            cost_savings = min(100.0, avg_fte_delta * 20.0)

        # Risk reduction: from evidence grade of elements
        risk_scores = []
        for elem in elements:
            grade = getattr(elem, "evidence_grade", None) or "U"
            grade_score = {"A": 90, "B": 75, "C": 50, "D": 30, "U": 10}.get(grade, 10)
            risk_scores.append(grade_score)
        risk_reduction = sum(risk_scores) / max(len(risk_scores), 1)

        # Strategic alignment: from confidence scores
        confidence_scores = [(elem.confidence_score or 0) * 100 for elem in elements]
        strategic_alignment = sum(confidence_scores) / max(len(confidence_scores), 1)

        return {
            "volume_impact": volume_impact,
            "cost_savings_potential": cost_savings,
            "risk_reduction": risk_reduction,
            "strategic_alignment": strategic_alignment,
        }

    def _compute_ability_components(
        self,
        elements: list[ProcessElement],
        maturity_scores: dict[str, float],
        compliance_data: dict[str, float],
    ) -> dict[str, float]:
        """Compute ability-to-execute axis components (0-100 each)."""
        # Process maturity: from TOM maturity scores (1-5 scale → 0-100)
        if maturity_scores:
            avg_maturity = sum(maturity_scores.values()) / len(maturity_scores)
            process_maturity = (avg_maturity / 5.0) * 100.0
        else:
            process_maturity = 50.0  # Default midpoint

        # Evidence confidence: average confidence of elements
        confidence_scores = [(elem.confidence_score or 0) * 100 for elem in elements]
        evidence_confidence = sum(confidence_scores) / max(len(confidence_scores), 1)

        # Compliance readiness: from compliance coverage data
        elem_ids = [str(elem.id) for elem in elements]
        compliance_scores = [compliance_data.get(eid, 50.0) for eid in elem_ids]
        compliance_readiness = sum(compliance_scores) / max(len(compliance_scores), 1)

        # Resource availability: from brightness classification (proxy)
        brightness_scores = []
        for elem in elements:
            brightness = getattr(elem, "brightness_classification", None) or "DIM"
            score = {"BRIGHT": 90, "DIM": 50, "DARK": 20}.get(brightness, 50)
            brightness_scores.append(score)
        resource_availability = sum(brightness_scores) / max(len(brightness_scores), 1)

        return {
            "process_maturity": process_maturity,
            "evidence_confidence": evidence_confidence,
            "compliance_readiness": compliance_readiness,
            "resource_availability": resource_availability,
        }

    # ── Persistence ──────────────────────────────────────────────────────

    async def _persist_entries(
        self,
        engagement_id: uuid.UUID,
        entries: list[dict[str, Any]],
    ) -> None:
        """Upsert assessment matrix entries."""
        now = datetime.now(UTC)

        for entry_data in entries:
            # Check if entry exists
            stmt = select(AssessmentMatrixEntry).where(
                AssessmentMatrixEntry.engagement_id == engagement_id,
                AssessmentMatrixEntry.process_area_name == entry_data["process_area_name"],
            )
            result = await self._session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                await self._session.execute(
                    update(AssessmentMatrixEntry)
                    .where(AssessmentMatrixEntry.id == existing.id)
                    .values(
                        value_score=entry_data["value_score"],
                        ability_to_execute=entry_data["ability_to_execute"],
                        quadrant=entry_data["quadrant"],
                        value_components=entry_data["value_components"],
                        ability_components=entry_data["ability_components"],
                        element_count=entry_data["element_count"],
                        updated_at=now,
                    )
                )
            else:
                new_entry = AssessmentMatrixEntry(
                    engagement_id=engagement_id,
                    process_area_name=entry_data["process_area_name"],
                    value_score=entry_data["value_score"],
                    ability_to_execute=entry_data["ability_to_execute"],
                    quadrant=entry_data["quadrant"],
                    value_components=entry_data["value_components"],
                    ability_components=entry_data["ability_components"],
                    element_count=entry_data["element_count"],
                )
                self._session.add(new_entry)

        await self._session.flush()

    # ── Serialization ────────────────────────────────────────────────────

    @staticmethod
    def _entry_to_dict(entry: AssessmentMatrixEntry) -> dict[str, Any]:
        """Serialize an AssessmentMatrixEntry to a dict."""
        return {
            "id": str(entry.id),
            "process_area_name": entry.process_area_name,
            "process_area_description": entry.process_area_description,
            "value_score": entry.value_score,
            "ability_to_execute": entry.ability_to_execute,
            "quadrant": entry.quadrant.value,
            "value_components": entry.value_components,
            "ability_components": entry.ability_components,
            "element_count": entry.element_count,
            "notes": entry.notes,
            "created_at": entry.created_at.isoformat() if entry.created_at else "",
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
