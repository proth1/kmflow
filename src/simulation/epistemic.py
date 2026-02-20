"""Epistemic Action Planner for targeted evidence collection.

Ranks evidence gaps by information gain to guide the most impactful
evidence collection actions, integrating coverage analysis, gap scanning,
and cascading impact assessment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.pov.constants import DEFAULT_EVIDENCE_WEIGHT, EVIDENCE_TYPE_WEIGHTS

logger = logging.getLogger(__name__)

# Uplift calculation constants
MAX_PROJECTED_CONFIDENCE = 0.95
BASE_UPLIFT_PER_SOURCE = 0.12
UPLIFT_DECAY = 0.6  # Diminishing returns factor


@dataclass
class EpistemicActionItem:
    """A single epistemic action recommendation."""

    target_element_id: str
    target_element_name: str
    evidence_gap_description: str
    current_confidence: float
    estimated_confidence_uplift: float
    projected_confidence: float
    information_gain_score: float
    recommended_evidence_category: str
    priority: str


@dataclass
class EpistemicPlanResult:
    """Result of epistemic plan generation."""

    scenario_id: str
    actions: list[EpistemicActionItem] = field(default_factory=list)
    total_actions: int = 0
    high_priority_count: int = 0
    estimated_aggregate_uplift: float = 0.0


def calculate_confidence_uplift(
    current_confidence: float,
    source_count: int,
    type_weight: float,
) -> tuple[float, float]:
    """Calculate projected confidence uplift from collecting new evidence.

    Args:
        current_confidence: Current confidence score (0.0-1.0).
        source_count: Number of existing evidence sources.
        type_weight: Weight of the recommended evidence type.

    Returns:
        Tuple of (uplift_amount, projected_confidence).
    """
    # Diminishing returns: less uplift when more sources already exist
    decay = UPLIFT_DECAY ** max(0, source_count)
    raw_uplift = BASE_UPLIFT_PER_SOURCE * type_weight * decay

    # Gap-proportional: bigger gaps get more uplift
    gap = MAX_PROJECTED_CONFIDENCE - current_confidence
    uplift = min(raw_uplift, gap) if gap > 0 else 0.0

    projected = min(MAX_PROJECTED_CONFIDENCE, current_confidence + uplift)
    return round(uplift, 4), round(projected, 4)


def compute_information_gain(
    uplift: float,
    cascade_severity: float,
) -> float:
    """Compute information gain score from uplift and cascade severity.

    Args:
        uplift: The estimated confidence uplift.
        cascade_severity: Impact severity from cascading analysis (0.0-1.0).

    Returns:
        Composite information gain score.
    """
    # Weighted combination: uplift matters most, but cascade amplifies it
    return round(0.6 * uplift + 0.4 * (uplift * cascade_severity), 4)


def _recommend_evidence_category(gap_type: str, element_name: str) -> str:
    """Map gap type to most impactful evidence category.

    Uses EVIDENCE_TYPE_WEIGHTS to pick the highest-weighted category
    that's relevant to the gap type.
    """
    gap_lower = gap_type.lower()
    name_lower = element_name.lower()

    if "process" in gap_lower or "process" in name_lower:
        return "bpm_process_models"
    if "control" in gap_lower or "policy" in gap_lower or "governance" in name_lower:
        return "controls_evidence"
    if "regulation" in gap_lower or "compliance" in name_lower:
        return "regulatory_policy"
    if "data" in gap_lower or "structured" in name_lower:
        return "structured_data"
    if "communication" in gap_lower or "email" in name_lower:
        return "domain_communications"

    # Default to documents (high weight, general purpose)
    return "documents"


def _get_type_weight(category: str) -> float:
    """Get evidence type weight for a category."""
    return EVIDENCE_TYPE_WEIGHTS.get(category, DEFAULT_EVIDENCE_WEIGHT)


def _classify_priority(info_gain: float, current_confidence: float) -> str:
    """Classify action priority based on information gain and confidence."""
    if info_gain >= 0.04 or current_confidence < 0.3:
        return "high"
    if info_gain >= 0.02 or current_confidence < 0.5:
        return "medium"
    return "low"


class EpistemicPlannerService:
    """Generates epistemic action plans for targeted evidence collection."""

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def generate_epistemic_plan(
        self,
        scenario_id: UUID,
        engagement_id: UUID,
        session: Any,
        process_graph: dict[str, Any] | None = None,
    ) -> EpistemicPlanResult:
        """Generate an epistemic action plan for a scenario.

        Integrates evidence coverage, gap scanning, and cascading impact
        to produce a ranked list of evidence collection actions.

        Args:
            scenario_id: The scenario to analyze.
            engagement_id: The engagement for evidence lookup.
            session: Database session (unused in current impl, reserved).
            process_graph: Optional process graph for impact calculation.

        Returns:
            EpistemicPlanResult with ranked actions and aggregates.
        """
        from src.simulation.coverage import EvidenceCoverageService
        from src.simulation.impact import calculate_cascading_impact

        # 1. Compute coverage to find Dim/Dark elements
        coverage_service = EvidenceCoverageService(self._graph)
        coverage = await coverage_service.compute_coverage(
            scenario_id=scenario_id,
            engagement_id=engagement_id,
        )

        # 2. Identify elements needing evidence (dim + dark, exclude removed)
        target_elements = [
            e for e in coverage.elements
            if e.classification in ("dim", "dark") and not e.is_removed
        ]

        if not target_elements:
            return EpistemicPlanResult(scenario_id=str(scenario_id))

        # 3. Calculate cascading impact for context
        changed_names = [e.element_name for e in target_elements]
        graph_data = process_graph or {"connections": []}
        impact = calculate_cascading_impact(changed_names, graph_data)
        impact_by_element: dict[str, float] = {}
        for item in impact.get("impact_items", []):
            impact_by_element[item["element"]] = item["severity"]

        # 4. For each target, compute uplift + info gain + recommendation
        actions: list[EpistemicActionItem] = []
        for element in target_elements:
            gap_desc = (
                f"{'No evidence' if element.evidence_count == 0 else 'Weak evidence'} "
                f"for {element.element_name} "
                f"(classification: {element.classification}, "
                f"sources: {element.evidence_count})"
            )

            category = _recommend_evidence_category(
                element.classification, element.element_name
            )
            type_weight = _get_type_weight(category)

            uplift, projected = calculate_confidence_uplift(
                element.confidence, element.evidence_count, type_weight
            )

            cascade_severity = impact_by_element.get(element.element_name, 0.1)
            info_gain = compute_information_gain(uplift, cascade_severity)
            priority = _classify_priority(info_gain, element.confidence)

            actions.append(
                EpistemicActionItem(
                    target_element_id=element.element_id,
                    target_element_name=element.element_name,
                    evidence_gap_description=gap_desc,
                    current_confidence=element.confidence,
                    estimated_confidence_uplift=uplift,
                    projected_confidence=projected,
                    information_gain_score=info_gain,
                    recommended_evidence_category=category,
                    priority=priority,
                )
            )

        # 5. Rank by information gain DESC
        actions.sort(key=lambda a: a.information_gain_score, reverse=True)

        high_count = sum(1 for a in actions if a.priority == "high")
        total_uplift = sum(a.estimated_confidence_uplift for a in actions)

        return EpistemicPlanResult(
            scenario_id=str(scenario_id),
            actions=actions,
            total_actions=len(actions),
            high_priority_count=high_count,
            estimated_aggregate_uplift=round(total_uplift, 4),
        )
