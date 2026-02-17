"""Contradiction detection and resolution for the LCD algorithm.

Step 5: Detects conflicting values for the same element across different
evidence sources. Resolves contradictions using recency and quality scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.models import EvidenceItem
from src.pov.consensus import ConsensusElement
from src.pov.constants import EVIDENCE_TYPE_WEIGHTS

logger = logging.getLogger(__name__)


@dataclass
class DetectedContradiction:
    """A contradiction detected between evidence sources.

    Attributes:
        element_name: Name of the element with conflicting data.
        field_name: The field that has conflicting values.
        values: List of conflicting value entries with source info.
        resolution_value: The resolved value chosen.
        resolution_reason: Explanation for why this value was chosen.
        evidence_ids: Evidence item IDs involved in the contradiction.
    """

    element_name: str = ""
    field_name: str = ""
    values: list[dict[str, str]] = field(default_factory=list)
    resolution_value: str = ""
    resolution_reason: str = ""
    evidence_ids: list[str] = field(default_factory=list)


def _compute_source_priority(
    evidence_item: EvidenceItem,
) -> float:
    """Compute a priority score for an evidence source.

    Combines evidence type weight, quality score, and freshness for
    determining which source should win in a contradiction.

    Args:
        evidence_item: The evidence item to score.

    Returns:
        Priority score between 0.0 and 1.0.
    """
    category = str(evidence_item.category)
    type_weight = EVIDENCE_TYPE_WEIGHTS.get(category, 0.3)
    quality = evidence_item.quality_score
    freshness = evidence_item.freshness_score

    # Weighted combination: type(0.4) + quality(0.3) + freshness(0.3)
    return type_weight * 0.4 + quality * 0.3 + freshness * 0.3


def detect_contradictions(
    consensus_elements: list[ConsensusElement],
    evidence_items: list[EvidenceItem],
) -> list[DetectedContradiction]:
    """Detect contradictions in element definitions across sources.

    Looks for elements with the same name but different confidence scores
    or different metadata across evidence sources. In a real implementation,
    this would compare specific field values extracted from each source.

    For the MVP, we detect contradictions when:
    - An element has significantly different confidence scores across sources
    - Multiple evidence sources provide conflicting entity types

    Args:
        consensus_elements: Elements with consensus data.
        evidence_items: All evidence items for resolution.

    Returns:
        List of detected contradictions with resolutions.
    """
    # Build evidence lookup
    evidence_map: dict[str, EvidenceItem] = {}
    for item in evidence_items:
        evidence_map[str(item.id)] = item

    contradictions: list[DetectedContradiction] = []

    # Group elements by name to find conflicting definitions
    elements_by_name: dict[str, list[ConsensusElement]] = {}
    for elem in consensus_elements:
        name = elem.triangulated.entity.name.lower()
        if name not in elements_by_name:
            elements_by_name[name] = []
        elements_by_name[name].append(elem)

    # Check for contradictions within each name group
    for _name, group in elements_by_name.items():
        if len(group) <= 1:
            continue

        # Check for type conflicts (same name, different entity types)
        types_seen: dict[str, list[ConsensusElement]] = {}
        for elem in group:
            etype = elem.triangulated.entity.entity_type
            if etype not in types_seen:
                types_seen[etype] = []
            types_seen[etype].append(elem)

        if len(types_seen) > 1:
            # Type conflict detected
            all_evidence_ids: list[str] = []
            values: list[dict[str, str]] = []
            for etype, elems in types_seen.items():
                for e in elems:
                    all_evidence_ids.extend(e.triangulated.evidence_ids)
                    values.append(
                        {
                            "value": etype,
                            "source_count": str(len(e.triangulated.evidence_ids)),
                        }
                    )

            # Resolve by picking the type with highest weighted evidence
            best_type = ""
            best_score = -1.0
            for etype, elems in types_seen.items():
                type_score = sum(e.weighted_vote_score for e in elems)
                if type_score > best_score:
                    best_score = type_score
                    best_type = etype

            contradictions.append(
                DetectedContradiction(
                    element_name=group[0].triangulated.entity.name,
                    field_name="element_type",
                    values=values,
                    resolution_value=best_type,
                    resolution_reason=f"Resolved by weighted vote score (highest: {best_score:.2f})",
                    evidence_ids=list(set(all_evidence_ids)),
                )
            )

    # Also check for confidence divergence within single elements
    for elem in consensus_elements:
        ev_ids = elem.triangulated.evidence_ids
        if len(ev_ids) < 2:
            continue

        # Check quality score divergence across sources
        scores: list[tuple[str, float]] = []
        for ev_id in ev_ids:
            item = evidence_map.get(ev_id)
            if item:
                scores.append((ev_id, item.quality_score))

        if len(scores) >= 2:
            min_score = min(s[1] for s in scores)
            max_score = max(s[1] for s in scores)

            # Flag if quality divergence exceeds threshold
            if max_score - min_score > 0.4:
                best_ev = max(scores, key=lambda s: s[1])
                contradictions.append(
                    DetectedContradiction(
                        element_name=elem.triangulated.entity.name,
                        field_name="quality_divergence",
                        values=[{"evidence_id": s[0], "quality_score": f"{s[1]:.2f}"} for s in scores],
                        resolution_value=f"Prioritize evidence {best_ev[0]}",
                        resolution_reason=(
                            f"Quality divergence of {max_score - min_score:.2f} "
                            f"exceeds threshold. Using highest-quality source "
                            f"(score: {best_ev[1]:.2f})"
                        ),
                        evidence_ids=[s[0] for s in scores],
                    )
                )

    logger.info("Detected %d contradictions", len(contradictions))
    return contradictions
