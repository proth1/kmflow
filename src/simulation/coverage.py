"""Evidence coverage classification for the Scenario Comparison Workbench.

Classifies process elements as Bright/Dim/Dark based on evidence
source count and confidence scores, per PRD Section 6.9.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.core.models import ModificationType

logger = logging.getLogger(__name__)

# PRD classification thresholds
BRIGHT_MIN_SOURCES = 3
BRIGHT_MIN_CONFIDENCE = 0.75
DIM_MIN_CONFIDENCE = 0.40
MODIFICATION_CONFIDENCE_PENALTY = 0.15


@dataclass
class ElementCoverage:
    """Evidence coverage for a single process element."""

    element_id: str
    element_name: str
    classification: str  # "bright", "dim", "dark"
    evidence_count: int
    confidence: float
    is_added: bool = False
    is_removed: bool = False
    is_modified: bool = False


@dataclass
class ScenarioCoverageResult:
    """Aggregate evidence coverage for a scenario."""

    scenario_id: str
    elements: list[ElementCoverage] = field(default_factory=list)
    bright_count: int = 0
    dim_count: int = 0
    dark_count: int = 0
    aggregate_confidence: float = 0.0


def classify_element(
    evidence_count: int,
    confidence: float,
    is_added: bool = False,
) -> str:
    """Classify an element as bright, dim, or dark.

    Args:
        evidence_count: Number of evidence sources supporting this element.
        confidence: Average confidence score (0.0-1.0).
        is_added: Whether this element was added by a modification (always dark).

    Returns:
        Classification string: "bright", "dim", or "dark".
    """
    if is_added:
        return "dark"

    if evidence_count >= BRIGHT_MIN_SOURCES and confidence >= BRIGHT_MIN_CONFIDENCE:
        return "bright"

    if evidence_count >= 1 and confidence >= DIM_MIN_CONFIDENCE:
        return "dim"

    return "dark"


class EvidenceCoverageService:
    """Computes evidence coverage for simulation scenarios."""

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def compute_coverage(
        self,
        scenario_id: UUID,
        engagement_id: UUID,
        modifications: list[Any] | None = None,
    ) -> ScenarioCoverageResult:
        """Compute Bright/Dim/Dark coverage for a scenario.

        Args:
            scenario_id: The scenario being analyzed.
            engagement_id: The engagement for evidence lookup.
            modifications: List of ScenarioModification objects.

        Returns:
            ScenarioCoverageResult with per-element classifications.
        """
        modifications = modifications or []

        # Build modification lookups
        mod_by_element: dict[str, Any] = {}
        added_elements: dict[str, Any] = {}
        removed_element_ids: set[str] = set()

        for mod in modifications:
            mod_type = (
                mod.modification_type.value
                if hasattr(mod.modification_type, "value")
                else mod.modification_type
            )
            if mod_type in (ModificationType.TASK_REMOVE, ModificationType.CONTROL_REMOVE):
                removed_element_ids.add(mod.element_id)
            elif mod_type in (ModificationType.TASK_ADD, ModificationType.CONTROL_ADD):
                added_elements[mod.element_id] = mod
            else:
                mod_by_element[mod.element_id] = mod

        # Fetch evidence from knowledge graph
        element_evidence = await self._get_element_evidence(engagement_id)

        elements: list[ElementCoverage] = []

        # Process existing elements from graph
        for record in element_evidence:
            eid = record["id"]
            ename = record["name"] or eid
            count = record["evidence_count"]
            confidence = record["avg_confidence"] or 0.0

            is_removed = eid in removed_element_ids
            is_modified = eid in mod_by_element

            # Apply modification penalty
            if is_modified:
                confidence = max(0.0, confidence - MODIFICATION_CONFIDENCE_PENALTY)

            classification = classify_element(count, confidence)

            elements.append(
                ElementCoverage(
                    element_id=eid,
                    element_name=ename,
                    classification=classification,
                    evidence_count=count,
                    confidence=round(confidence, 4),
                    is_added=False,
                    is_removed=is_removed,
                    is_modified=is_modified,
                )
            )

        # Add newly added elements (always dark)
        for eid, mod in added_elements.items():
            elements.append(
                ElementCoverage(
                    element_id=eid,
                    element_name=mod.element_name,
                    classification="dark",
                    evidence_count=0,
                    confidence=0.0,
                    is_added=True,
                    is_removed=False,
                    is_modified=False,
                )
            )

        # Compute aggregates (exclude removed elements)
        active = [e for e in elements if not e.is_removed]
        bright = sum(1 for e in active if e.classification == "bright")
        dim = sum(1 for e in active if e.classification == "dim")
        dark = sum(1 for e in active if e.classification == "dark")
        avg_confidence = (
            sum(e.confidence for e in active) / len(active) if active else 0.0
        )

        return ScenarioCoverageResult(
            scenario_id=str(scenario_id),
            elements=elements,
            bright_count=bright,
            dim_count=dim,
            dark_count=dark,
            aggregate_confidence=round(avg_confidence, 4),
        )

    async def _get_element_evidence(
        self,
        engagement_id: UUID,
    ) -> list[dict[str, Any]]:
        """Fetch element evidence counts and confidence from Neo4j."""
        query = """
            MATCH (p {engagement_id: $eid})
            WHERE p:Process OR p:Activity
            OPTIONAL MATCH (p)-[r:SUPPORTED_BY]->(e:Evidence)
            RETURN p.id AS id, p.name AS name,
                   count(e) AS evidence_count,
                   avg(r.confidence) AS avg_confidence
        """
        return await self._graph._run_query(query, {"eid": str(engagement_id)})
