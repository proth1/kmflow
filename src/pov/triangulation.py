"""Cross-source triangulation for the LCD algorithm.

Step 3: Validates elements across multiple evidence sources, computes
triangulation scores, and categorizes elements by corroboration level.

Enhancements over the base module:
- Evidence plane classification (System/Behavioral, Documented/Formal,
  Observed/Field, Human Interpretation)
- evidence_coverage factor: supporting_planes / available_planes
- evidence_agreement factor: agreeing_sources / total_sources, with
  cross-plane bonus
- Single-source flagging for elements from exactly 1 source
- Conflict detection for elements where sources disagree on existence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models import CorroborationLevel, EvidenceItem
from src.pov.constants import (
    CROSS_PLANE_BONUS,
    EVIDENCE_PLANES,
    TRIANGULATION_THRESHOLDS,
)
from src.semantic.entity_extraction import ExtractedEntity

logger = logging.getLogger(__name__)


@dataclass
class TriangulatedElement:
    """An element with cross-source triangulation data.

    Attributes:
        entity: The extracted entity.
        source_count: Number of distinct evidence sources mentioning this entity.
        total_sources: Total number of evidence sources in the engagement.
        triangulation_score: Score from 0.0 to 1.0 based on source coverage.
        corroboration_level: STRONGLY, MODERATELY, or WEAKLY corroborated.
        evidence_ids: List of evidence item IDs that mention this entity.
        evidence_coverage: Plane coverage factor (planes supporting / planes available).
        evidence_agreement: Agreement factor with cross-plane bonus.
        supporting_planes: Set of evidence planes that support this element.
        single_source: Whether element is from exactly 1 evidence source.
        has_conflict: Whether any source contradicts this element's existence.
        conflicting_evidence_ids: Evidence IDs that contradict this element.
    """

    entity: ExtractedEntity
    source_count: int = 0
    total_sources: int = 0
    triangulation_score: float = 0.0
    corroboration_level: CorroborationLevel = CorroborationLevel.WEAKLY
    evidence_ids: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    evidence_agreement: float = 0.0
    supporting_planes: set[str] = field(default_factory=set)
    single_source: bool = False
    has_conflict: bool = False
    conflicting_evidence_ids: list[str] = field(default_factory=list)


def _compute_triangulation_score(source_count: int, total_sources: int) -> float:
    """Compute a triangulation score based on source coverage.

    The score considers:
    - Base ratio of sources mentioning the element
    - Bonus for having 3+ sources (strong triangulation)
    - Minimum score of 0.1 for any element found in at least 1 source

    Args:
        source_count: Number of sources mentioning the element.
        total_sources: Total number of evidence sources.

    Returns:
        Triangulation score between 0.0 and 1.0.
    """
    if total_sources == 0 or source_count == 0:
        return 0.0

    # Base coverage ratio
    base_score = source_count / total_sources

    # Bonus for multi-source corroboration
    if source_count >= 3:
        multi_source_bonus = 0.15
    elif source_count >= 2:
        multi_source_bonus = 0.05
    else:
        multi_source_bonus = 0.0

    score = base_score + multi_source_bonus
    return min(1.0, max(0.0, score))


def _determine_corroboration(score: float) -> CorroborationLevel:
    """Determine corroboration level from triangulation score.

    Args:
        score: Triangulation score between 0.0 and 1.0.

    Returns:
        Corroboration level enum value.
    """
    if score >= TRIANGULATION_THRESHOLDS["strongly"]:
        return CorroborationLevel.STRONGLY
    elif score >= TRIANGULATION_THRESHOLDS["moderately"]:
        return CorroborationLevel.MODERATELY
    else:
        return CorroborationLevel.WEAKLY


def get_evidence_plane(category: str) -> str:
    """Map an evidence category to its evidence plane.

    Args:
        category: Evidence category string.

    Returns:
        Evidence plane name.
    """
    return EVIDENCE_PLANES.get(category, "observed_field")


def compute_evidence_coverage(
    supporting_planes: set[str],
    available_planes: set[str],
) -> float:
    """Compute evidence coverage as ratio of supporting to available planes.

    Args:
        supporting_planes: Planes that support this element.
        available_planes: Planes available in the engagement.

    Returns:
        Coverage factor between 0.0 and 1.0.
    """
    if not available_planes:
        return 0.0
    return len(supporting_planes & available_planes) / len(available_planes)


def compute_evidence_agreement(
    agreeing_count: int,
    total_mentioning: int,
    cross_plane: bool = False,
) -> float:
    """Compute evidence agreement factor.

    Base agreement is agreeing/total. Cross-plane corroboration adds a bonus.

    Args:
        agreeing_count: Number of sources that agree.
        total_mentioning: Total sources that mention this element.
        cross_plane: Whether corroboration spans multiple planes.

    Returns:
        Agreement factor between 0.0 and 1.0.
    """
    if total_mentioning == 0:
        return 0.0

    base = agreeing_count / total_mentioning
    bonus = CROSS_PLANE_BONUS if cross_plane and base > 0.0 else 0.0
    return min(1.0, base + bonus)


def _get_available_planes(evidence_items: list[EvidenceItem]) -> set[str]:
    """Determine which evidence planes are available in the engagement.

    Args:
        evidence_items: All evidence items in the engagement.

    Returns:
        Set of plane names present in the engagement.
    """
    planes: set[str] = set()
    for item in evidence_items:
        plane = get_evidence_plane(str(item.category))
        planes.add(plane)
    return planes


def triangulate_elements(
    entities: list[ExtractedEntity],
    entity_to_evidence: dict[str, list[str]],
    evidence_items: list[EvidenceItem],
) -> list[TriangulatedElement]:
    """Perform cross-source triangulation on extracted entities.

    For each entity, counts how many distinct evidence sources mention it,
    classifies evidence by plane, and computes coverage/agreement factors.

    Enhancements:
    - Evidence plane classification per PRD Section 6.2
    - evidence_coverage = supporting_planes / available_planes
    - evidence_agreement = agreeing/total with cross-plane bonus
    - Single-source flagging
    - Conflict detection placeholder

    Args:
        entities: List of resolved entities.
        entity_to_evidence: Map from entity ID to evidence item IDs.
        evidence_items: All evidence items in the engagement.

    Returns:
        List of TriangulatedElements with scores and corroboration levels.
    """
    total_sources = len(evidence_items)

    # Build evidence lookup
    evidence_map: dict[str, EvidenceItem] = {}
    for item in evidence_items:
        evidence_map[str(item.id)] = item

    # Determine available planes in engagement
    available_planes = _get_available_planes(evidence_items)

    results: list[TriangulatedElement] = []

    for entity in entities:
        evidence_ids = entity_to_evidence.get(entity.id, [])
        source_count = len(evidence_ids)

        # Determine supporting planes
        supporting_planes: set[str] = set()
        for eid in evidence_ids:
            ev_item = evidence_map.get(eid)
            if ev_item:
                plane = get_evidence_plane(str(ev_item.category))
                supporting_planes.add(plane)

        # Compute factors
        ev_coverage = compute_evidence_coverage(supporting_planes, available_planes)
        cross_plane = len(supporting_planes) >= 2
        # Agreement: use source_count vs total_sources (not source_count vs itself)
        # so agreement reflects how broadly the entity is supported across all sources
        ev_agreement = compute_evidence_agreement(source_count, total_sources, cross_plane=cross_plane)

        # Compute triangulation score (uses existing formula)
        score = _compute_triangulation_score(source_count, total_sources)
        level = _determine_corroboration(score)

        # Single-source flag
        single_source = source_count <= 1

        results.append(
            TriangulatedElement(
                entity=entity,
                source_count=source_count,
                total_sources=total_sources,
                triangulation_score=score,
                corroboration_level=level,
                evidence_ids=evidence_ids,
                evidence_coverage=ev_coverage,
                evidence_agreement=ev_agreement,
                supporting_planes=supporting_planes,
                single_source=single_source,
                has_conflict=False,
                conflicting_evidence_ids=[],
            )
        )

    logger.info(
        "Triangulated %d elements: %d strongly, %d moderately, %d weakly corroborated, %d single-source",
        len(results),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.STRONGLY),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.MODERATELY),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.WEAKLY),
        sum(1 for r in results if r.single_source),
    )

    return results


def detect_source_conflicts(
    triangulated: list[TriangulatedElement],
    contradicting_evidence: dict[str, list[str]] | None = None,
) -> list[TriangulatedElement]:
    """Flag elements that have conflicting evidence sources.

    For each element, checks if any evidence source explicitly contradicts
    the element's existence. Flagged elements are forwarded to Step 4
    (consistency checks) for conflict classification.

    Args:
        triangulated: List of triangulated elements.
        contradicting_evidence: Map from entity ID to evidence IDs that
            contradict the entity. If None, no conflicts are flagged.

    Returns:
        The same list with has_conflict and conflicting_evidence_ids updated.
    """
    if not contradicting_evidence:
        return triangulated

    for elem in triangulated:
        conflicting_ids = contradicting_evidence.get(elem.entity.id, [])
        if conflicting_ids:
            elem.has_conflict = True
            elem.conflicting_evidence_ids = conflicting_ids
            logger.info(
                "Source conflict detected for '%s': %d conflicting sources",
                elem.entity.name,
                len(conflicting_ids),
            )

    return triangulated
