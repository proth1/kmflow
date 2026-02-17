"""Consensus building for the LCD algorithm.

Step 4: Applies weighted voting by evidence type to build a consensus
model. Elements with higher-weight evidence types contributing to them
receive higher consensus scores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models import EvidenceItem
from src.pov.constants import DEFAULT_EVIDENCE_WEIGHT, EVIDENCE_TYPE_WEIGHTS
from src.pov.triangulation import TriangulatedElement

logger = logging.getLogger(__name__)


@dataclass
class ConsensusElement:
    """An element with consensus score from weighted voting.

    Attributes:
        triangulated: The triangulated element data.
        weighted_vote_score: Score from weighted voting across evidence types.
        max_weight: Highest evidence type weight supporting this element.
        contributing_categories: Set of evidence categories supporting this element.
    """

    triangulated: TriangulatedElement
    weighted_vote_score: float = 0.0
    max_weight: float = 0.0
    contributing_categories: set[str] = field(default_factory=set)


def _get_evidence_weight(category: str) -> float:
    """Get the weight for an evidence category.

    Args:
        category: Evidence category name (from EvidenceCategory enum).

    Returns:
        Weight value between 0.0 and 1.0.
    """
    return EVIDENCE_TYPE_WEIGHTS.get(category, DEFAULT_EVIDENCE_WEIGHT)


def build_consensus(
    triangulated_elements: list[TriangulatedElement],
    evidence_items: list[EvidenceItem],
) -> list[ConsensusElement]:
    """Build consensus model using weighted voting by evidence type.

    For each triangulated element, computes a weighted vote score based
    on the evidence types that support it. Higher-weight evidence types
    (e.g., structured data, BPM models) contribute more to the consensus.

    The weighted vote score is:
        sum(weight_i) / sum(max_possible_weights) for each supporting source

    Args:
        triangulated_elements: Elements with triangulation data.
        evidence_items: All evidence items (for category lookup).

    Returns:
        List of ConsensusElements with weighted vote scores.
    """
    # Build evidence ID -> category mapping
    evidence_category_map: dict[str, str] = {}
    for item in evidence_items:
        evidence_category_map[str(item.id)] = str(item.category)

    results: list[ConsensusElement] = []

    for tri_elem in triangulated_elements:
        weighted_sum = 0.0
        max_weight = 0.0
        categories: set[str] = set()

        for ev_id in tri_elem.evidence_ids:
            category = evidence_category_map.get(ev_id, "")
            weight = _get_evidence_weight(category)
            weighted_sum += weight
            max_weight = max(max_weight, weight)
            if category:
                categories.add(category)

        # Normalize: weighted average across supporting sources
        source_count = len(tri_elem.evidence_ids)
        vote_score = weighted_sum / source_count if source_count > 0 else 0.0

        results.append(
            ConsensusElement(
                triangulated=tri_elem,
                weighted_vote_score=vote_score,
                max_weight=max_weight,
                contributing_categories=categories,
            )
        )

    logger.info(
        "Built consensus for %d elements, avg weighted score: %.3f",
        len(results),
        sum(r.weighted_vote_score for r in results) / len(results) if results else 0,
    )

    return results
