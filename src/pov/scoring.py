"""Confidence scoring for the LCD algorithm.

Step 6: Computes confidence scores using a 5-factor weighted formula:
  coverage(0.30) + agreement(0.25) + quality(0.20) + reliability(0.15) + recency(0.10)

Categorizes confidence levels:
  VERY_HIGH >= 0.90, HIGH >= 0.75, MEDIUM >= 0.50, LOW >= 0.25, VERY_LOW < 0.25
"""

from __future__ import annotations

import logging

from src.core.models import EvidenceItem
from src.pov.consensus import ConsensusElement
from src.pov.constants import CONFIDENCE_FACTOR_WEIGHTS, CONFIDENCE_LEVELS

logger = logging.getLogger(__name__)


def _compute_coverage(element: ConsensusElement, total_sources: int) -> float:
    """Compute coverage factor: proportion of sources mentioning this element.

    Args:
        element: The consensus element.
        total_sources: Total evidence sources in the engagement.

    Returns:
        Coverage score between 0.0 and 1.0.
    """
    if total_sources == 0:
        return 0.0
    return min(1.0, element.triangulated.source_count / total_sources)


def _compute_agreement(element: ConsensusElement) -> float:
    """Compute agreement factor: consistency of evidence across sources.

    Based on the weighted vote score which already accounts for evidence
    type weights. Higher score means more agreement from authoritative sources.

    Args:
        element: The consensus element.

    Returns:
        Agreement score between 0.0 and 1.0.
    """
    return element.weighted_vote_score


def _compute_quality(
    element: ConsensusElement,
    evidence_map: dict[str, EvidenceItem],
) -> float:
    """Compute quality factor: average quality of supporting evidence.

    Args:
        element: The consensus element.
        evidence_map: Map from evidence ID to evidence item.

    Returns:
        Quality score between 0.0 and 1.0.
    """
    scores: list[float] = []
    for ev_id in element.triangulated.evidence_ids:
        item = evidence_map.get(ev_id)
        if item:
            scores.append(item.quality_score)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _compute_reliability(
    element: ConsensusElement,
    evidence_map: dict[str, EvidenceItem],
) -> float:
    """Compute reliability factor: average reliability of supporting evidence.

    Args:
        element: The consensus element.
        evidence_map: Map from evidence ID to evidence item.

    Returns:
        Reliability score between 0.0 and 1.0.
    """
    scores: list[float] = []
    for ev_id in element.triangulated.evidence_ids:
        item = evidence_map.get(ev_id)
        if item:
            scores.append(item.reliability_score)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _compute_recency(
    element: ConsensusElement,
    evidence_map: dict[str, EvidenceItem],
) -> float:
    """Compute recency factor: average freshness of supporting evidence.

    Args:
        element: The consensus element.
        evidence_map: Map from evidence ID to evidence item.

    Returns:
        Recency score between 0.0 and 1.0.
    """
    scores: list[float] = []
    for ev_id in element.triangulated.evidence_ids:
        item = evidence_map.get(ev_id)
        if item:
            scores.append(item.freshness_score)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def classify_confidence(score: float) -> str:
    """Classify a confidence score into a named level.

    Args:
        score: Confidence score between 0.0 and 1.0.

    Returns:
        Confidence level name (VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW).
    """
    for level_name, threshold in CONFIDENCE_LEVELS:
        if score >= threshold:
            return level_name
    return "VERY_LOW"


def compute_element_confidence(
    element: ConsensusElement,
    evidence_items: list[EvidenceItem],
    total_sources: int,
) -> float:
    """Compute the final confidence score for a single element.

    Uses the 5-factor weighted formula:
      coverage(0.30) + agreement(0.25) + quality(0.20) + reliability(0.15) + recency(0.10)

    Args:
        element: The consensus element to score.
        evidence_items: All evidence items for scoring lookups.
        total_sources: Total number of evidence sources.

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    evidence_map: dict[str, EvidenceItem] = {str(item.id): item for item in evidence_items}

    coverage = _compute_coverage(element, total_sources)
    agreement = _compute_agreement(element)
    quality = _compute_quality(element, evidence_map)
    reliability = _compute_reliability(element, evidence_map)
    recency = _compute_recency(element, evidence_map)

    score = (
        CONFIDENCE_FACTOR_WEIGHTS["coverage"] * coverage
        + CONFIDENCE_FACTOR_WEIGHTS["agreement"] * agreement
        + CONFIDENCE_FACTOR_WEIGHTS["quality"] * quality
        + CONFIDENCE_FACTOR_WEIGHTS["reliability"] * reliability
        + CONFIDENCE_FACTOR_WEIGHTS["recency"] * recency
    )

    return min(1.0, max(0.0, score))


def score_all_elements(
    consensus_elements: list[ConsensusElement],
    evidence_items: list[EvidenceItem],
) -> list[tuple[ConsensusElement, float, str]]:
    """Score all consensus elements and classify confidence levels.

    Args:
        consensus_elements: Elements with consensus data.
        evidence_items: All evidence items for scoring.

    Returns:
        List of (element, score, level) tuples.
    """
    total_sources = len(evidence_items)
    results: list[tuple[ConsensusElement, float, str]] = []

    for element in consensus_elements:
        score = compute_element_confidence(element, evidence_items, total_sources)
        level = classify_confidence(score)
        results.append((element, score, level))

    avg_score = sum(r[1] for r in results) / len(results) if results else 0
    logger.info(
        "Scored %d elements, avg confidence: %.3f",
        len(results),
        avg_score,
    )

    return results
