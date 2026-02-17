"""Cross-source triangulation for the LCD algorithm.

Step 3: Validates elements across multiple evidence sources, computes
triangulation scores, and categorizes elements by corroboration level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models import CorroborationLevel, EvidenceItem
from src.pov.constants import TRIANGULATION_THRESHOLDS
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
    """

    entity: ExtractedEntity
    source_count: int = 0
    total_sources: int = 0
    triangulation_score: float = 0.0
    corroboration_level: CorroborationLevel = CorroborationLevel.WEAKLY
    evidence_ids: list[str] = field(default_factory=list)


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


def triangulate_elements(
    entities: list[ExtractedEntity],
    entity_to_evidence: dict[str, list[str]],
    evidence_items: list[EvidenceItem],
) -> list[TriangulatedElement]:
    """Perform cross-source triangulation on extracted entities.

    For each entity, counts how many distinct evidence sources mention it
    and computes a triangulation score based on coverage across sources.

    Args:
        entities: List of resolved entities.
        entity_to_evidence: Map from entity ID to evidence item IDs.
        evidence_items: All evidence items in the engagement.

    Returns:
        List of TriangulatedElements with scores and corroboration levels.
    """
    total_sources = len(evidence_items)
    results: list[TriangulatedElement] = []

    for entity in entities:
        evidence_ids = entity_to_evidence.get(entity.id, [])
        source_count = len(evidence_ids)

        score = _compute_triangulation_score(source_count, total_sources)
        level = _determine_corroboration(score)

        results.append(
            TriangulatedElement(
                entity=entity,
                source_count=source_count,
                total_sources=total_sources,
                triangulation_score=score,
                corroboration_level=level,
                evidence_ids=evidence_ids,
            )
        )

    logger.info(
        "Triangulated %d elements: %d strongly, %d moderately, %d weakly corroborated",
        len(results),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.STRONGLY),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.MODERATELY),
        sum(1 for r in results if r.corroboration_level == CorroborationLevel.WEAKLY),
    )

    return results
