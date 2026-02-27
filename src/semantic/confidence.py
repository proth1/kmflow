"""Three-dimensional confidence scoring service.

Implements PRD v2.1 Section 6.3 two-stage confidence formula:
  Stage 1a: strength = coverage * 0.55 + agreement * 0.45
  Stage 1b: quality  = quality * 0.40 + reliability * 0.35 + recency * 0.25
  Stage 2:  final    = min(strength, quality)

Brightness is derived from score + evidence grade with coherence constraint.
"""

from __future__ import annotations

import logging

from src.api.schemas.confidence import ConfidenceScore
from src.pov.constants import (
    BRIGHTNESS_BRIGHT_THRESHOLD,
    BRIGHTNESS_DIM_THRESHOLD,
    GRADES_CAPPED_AT_DIM,
    QUALITY_WEIGHTS,
    STRENGTH_WEIGHTS,
)

logger = logging.getLogger(__name__)


def compute_strength(coverage: float, agreement: float) -> float:
    """Compute the strength sub-score.

    Args:
        coverage: Evidence coverage score (0-1).
        agreement: Evidence agreement score (0-1).

    Returns:
        Strength sub-score (0-1).
    """
    return STRENGTH_WEIGHTS["coverage"] * coverage + STRENGTH_WEIGHTS["agreement"] * agreement


def compute_quality(quality: float, reliability: float, recency: float) -> float:
    """Compute the quality sub-score.

    Args:
        quality: Evidence quality score (0-1).
        reliability: Source reliability score (0-1).
        recency: Evidence recency score (0-1).

    Returns:
        Quality sub-score (0-1).
    """
    return (
        QUALITY_WEIGHTS["quality"] * quality
        + QUALITY_WEIGHTS["reliability"] * reliability
        + QUALITY_WEIGHTS["recency"] * recency
    )


def compute_confidence(
    coverage: float,
    agreement: float,
    quality: float,
    reliability: float,
    recency: float,
) -> tuple[float, float, float]:
    """Compute the two-stage confidence score.

    Args:
        coverage: Evidence coverage (0-1).
        agreement: Evidence agreement (0-1).
        quality: Evidence quality (0-1).
        reliability: Source reliability (0-1).
        recency: Evidence recency (0-1).

    Returns:
        Tuple of (final_score, strength, quality_score).
    """
    strength = compute_strength(coverage, agreement)
    quality_score = compute_quality(quality, reliability, recency)
    final = min(strength, quality_score)
    return (
        min(1.0, max(0.0, final)),
        min(1.0, max(0.0, strength)),
        min(1.0, max(0.0, quality_score)),
    )


def determine_evidence_grade(
    evidence_count: int,
    source_plane_count: int,
    has_sme_validation: bool,
) -> str:
    """Determine evidence grade based on assessment criteria.

    Grade A: SME-validated + 2+ evidence planes
    Grade B: Multi-source, partially validated (2+ sources, some validation)
    Grade C: Multiple sources but unvalidated (2+ sources, no validation)
    Grade D: Single-source unvalidated claim
    Grade U: No evidence

    Args:
        evidence_count: Number of evidence items.
        source_plane_count: Number of distinct evidence planes/categories.
        has_sme_validation: Whether an SME has validated the evidence.

    Returns:
        Grade string: "A", "B", "C", "D", or "U".
    """
    if evidence_count == 0:
        return "U"

    if has_sme_validation and source_plane_count >= 2:
        return "A"

    if evidence_count >= 2 and has_sme_validation:
        return "B"

    if evidence_count >= 2:
        return "C"

    return "D"


def derive_brightness(score: float, grade: str) -> str:
    """Derive brightness classification with coherence constraint.

    Score-based: BRIGHT >= 0.75, DIM >= 0.40, DARK < 0.40
    Coherence: Grade D or U caps brightness at DIM.

    Args:
        score: Confidence score (0-1).
        grade: Evidence grade (A/B/C/D/U).

    Returns:
        Brightness classification: "bright", "dim", or "dark".
    """
    if score >= BRIGHTNESS_BRIGHT_THRESHOLD:
        score_brightness = "bright"
    elif score >= BRIGHTNESS_DIM_THRESHOLD:
        score_brightness = "dim"
    else:
        score_brightness = "dark"

    grade_brightness = "dim" if grade in GRADES_CAPPED_AT_DIM else "bright"

    order = {"dark": 0, "dim": 1, "bright": 2}
    return min(score_brightness, grade_brightness, key=lambda b: order[b])


def score_element(
    coverage: float,
    agreement: float,
    quality: float,
    reliability: float,
    recency: float,
    evidence_count: int,
    source_plane_count: int,
    has_sme_validation: bool,
) -> ConfidenceScore:
    """Score a process element using the three-dimensional confidence model.

    Args:
        coverage: Evidence coverage (0-1).
        agreement: Evidence agreement (0-1).
        quality: Evidence quality (0-1).
        reliability: Source reliability (0-1).
        recency: Evidence recency (0-1).
        evidence_count: Number of evidence items.
        source_plane_count: Number of distinct evidence planes.
        has_sme_validation: Whether SME validation exists.

    Returns:
        ConfidenceScore with all three dimensions computed.
    """
    final_score, strength, quality_score = compute_confidence(coverage, agreement, quality, reliability, recency)
    grade = determine_evidence_grade(evidence_count, source_plane_count, has_sme_validation)

    result = ConfidenceScore(
        confidence_score=final_score,
        strength_score=strength,
        quality_score=quality_score,
        evidence_grade=grade,
    )

    logger.debug(
        "Scored element: score=%.3f (str=%.3f, qual=%.3f), grade=%s, brightness=%s, mvc=%s",
        final_score,
        strength,
        quality_score,
        grade,
        result.brightness_classification,
        result.mvc_threshold_passed,
    )

    return result
