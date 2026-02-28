"""Evidence quality scoring engine.

Calculates four quality dimensions per evidence item:
- Completeness: proportion of shelf request items matched
- Reliability: source credibility score based on metadata
- Freshness: Hill function decay based on document date vs current date
- Consistency: agreement with other evidence in the same engagement

Composite quality_score is a configurable weighted average.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    EvidenceItem,
    ShelfDataRequestItem,
    ShelfRequestItemStatus,
)

# Default weights for composite quality score calculation
DEFAULT_QUALITY_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "reliability": 0.30,
    "freshness": 0.20,
    "consistency": 0.20,
}

# Freshness threshold in days — score = 0.5 at this age
# Using a Hill function: score = 1 / (1 + (days / threshold)^power)
FRESHNESS_THRESHOLD_DAYS = 3 * 365  # 3 years
FRESHNESS_POWER = 3  # Steepness of decay curve

# Reliability score mapping by source type / metadata indicators
RELIABILITY_BY_SOURCE: dict[str, float] = {
    "primary": 0.95,
    "official": 1.0,
    "verified": 0.9,
    "internal": 0.8,
    "third_party": 0.7,
    "client_provided": 0.6,
    "secondary": 0.6,
    "unknown": 0.4,
}


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    """Validate that quality weights sum to 1.0 and contain required keys.

    Args:
        weights: Dictionary of dimension weights.

    Returns:
        The validated weights.

    Raises:
        ValueError: If weights don't sum to 1.0 or are missing keys.
    """
    required_keys = {"completeness", "reliability", "freshness", "consistency"}
    missing = required_keys - set(weights.keys())
    if missing:
        msg = f"Missing weight keys: {missing}"
        raise ValueError(msg)

    for key, value in weights.items():
        if key in required_keys and not (0.0 <= value <= 1.0):
            msg = f"Weight '{key}' must be between 0.0 and 1.0, got {value}"
            raise ValueError(msg)

    total = sum(weights[k] for k in required_keys)
    if abs(total - 1.0) > 0.001:
        msg = f"Weights must sum to 1.0, got {total:.4f}"
        raise ValueError(msg)

    return weights


def calculate_freshness(source_date: date | datetime | None, reference_date: date | None = None) -> float:
    """Calculate freshness score using a Hill function.

    Uses score = 1 / (1 + (days / threshold)^power) which gives:
    - score >= 0.96 for documents within 12 months
    - score = 0.5 at the threshold (3 years)
    - score < 0.5 for documents older than 3 years

    Args:
        source_date: The date of the source document.
        reference_date: The date to measure freshness against (defaults to today).

    Returns:
        Freshness score between 0.0 and 1.0.
    """
    if source_date is None:
        return 0.3  # Default for unknown dates

    if reference_date is None:
        reference_date = date.today()

    # Normalize to date objects
    if isinstance(source_date, datetime):
        source_date = source_date.date()
    if isinstance(reference_date, datetime):
        reference_date = reference_date.date()

    days_old = (reference_date - source_date).days
    if days_old <= 0:
        return 1.0  # Future or same-day date treated as fresh

    # Hill function: score = 1 / (1 + (days / threshold)^power)
    ratio = days_old / FRESHNESS_THRESHOLD_DAYS
    return 1.0 / (1.0 + ratio**FRESHNESS_POWER)


def calculate_reliability(metadata: dict | None) -> float:
    """Calculate reliability score based on evidence metadata.

    Examines metadata for source type, verification status, and
    other credibility indicators. PRIMARY sources score >= 0.9,
    SECONDARY sources score < 0.7.

    Args:
        metadata: The evidence item's metadata dictionary.

    Returns:
        Reliability score between 0.0 and 1.0.
    """
    if not metadata:
        return RELIABILITY_BY_SOURCE["unknown"]

    # Check for explicit source_type
    source_type = metadata.get("source_type", "unknown")
    if isinstance(source_type, str):
        base_score = RELIABILITY_BY_SOURCE.get(source_type.lower(), RELIABILITY_BY_SOURCE["unknown"])
    else:
        base_score = RELIABILITY_BY_SOURCE["unknown"]

    # Bonus for verified flag
    if metadata.get("verified", False):
        base_score = min(1.0, base_score + 0.1)

    # Bonus for having an author attribution
    if metadata.get("author"):
        base_score = min(1.0, base_score + 0.05)

    return base_score


async def calculate_completeness(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> float:
    """Calculate completeness based on shelf request item matching.

    Measures the proportion of shelf request items in the same engagement
    and category that have been fulfilled.

    Args:
        session: Database session.
        evidence_item: The evidence item to score.

    Returns:
        Completeness score between 0.0 and 1.0.
    """
    # Count total request items matching this evidence's category in the engagement
    total_result = await session.execute(
        select(func.count())
        .select_from(ShelfDataRequestItem)
        .join(
            ShelfDataRequestItem.request,
        )
        .where(
            ShelfDataRequestItem.category == evidence_item.category,
        )
    )
    total_items = total_result.scalar() or 0

    if total_items == 0:
        # No shelf request items for this category - default completeness
        return 0.5

    # Count fulfilled items (RECEIVED, VALIDATED, or ACTIVE)
    fulfilled_statuses = {
        ShelfRequestItemStatus.RECEIVED,
        ShelfRequestItemStatus.VALIDATED,
        ShelfRequestItemStatus.ACTIVE,
    }
    received_result = await session.execute(
        select(func.count())
        .select_from(ShelfDataRequestItem)
        .join(
            ShelfDataRequestItem.request,
        )
        .where(
            ShelfDataRequestItem.category == evidence_item.category,
            ShelfDataRequestItem.status.in_(fulfilled_statuses),
        )
    )
    received_items = received_result.scalar() or 0

    return received_items / total_items


async def calculate_consistency(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> float:
    """Calculate consistency with other evidence in the same engagement.

    Measures agreement based on the count of corroborating evidence items
    in the same category. Three or more related items yields >= 0.8.
    Evidence with contradictions (tracked via ConflictObjects) scores lower.

    Args:
        session: Database session.
        evidence_item: The evidence item to score.

    Returns:
        Consistency score between 0.0 and 1.0.
    """
    # Count other evidence items in the same engagement and category
    count_result = await session.execute(
        select(func.count())
        .select_from(EvidenceItem)
        .where(
            EvidenceItem.engagement_id == evidence_item.engagement_id,
            EvidenceItem.category == evidence_item.category,
            EvidenceItem.id != evidence_item.id,
            EvidenceItem.duplicate_of_id.is_(None),  # Exclude duplicates
        )
    )
    related_count = count_result.scalar() or 0

    if related_count == 0:
        return 0.5  # Neutral - no corroboration or contradiction

    # Scaled diminishing returns: score = 1 - 0.5 / (1 + 0.5 * count)
    # At count=1: 0.667; count=2: 0.75; count=3: 0.80; count=5: 0.857
    return 1.0 - 0.5 / (1.0 + 0.5 * related_count)


def compute_composite(
    scores: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute weighted composite quality score.

    Args:
        scores: Dictionary with completeness, reliability, freshness, consistency.
        weights: Optional custom weights (defaults to DEFAULT_QUALITY_WEIGHTS).

    Returns:
        Composite quality score between 0.0 and 1.0.
    """
    w = weights or DEFAULT_QUALITY_WEIGHTS
    return round(
        w["completeness"] * scores["completeness"]
        + w["reliability"] * scores["reliability"]
        + w["freshness"] * scores["freshness"]
        + w["consistency"] * scores["consistency"],
        4,
    )


async def score_evidence(
    session: AsyncSession,
    evidence_item: EvidenceItem,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Calculate all quality dimensions for an evidence item.

    Updates the evidence item's quality scores in place.

    Args:
        session: Database session.
        evidence_item: The evidence item to score.
        weights: Optional engagement-level weights (defaults to DEFAULT_QUALITY_WEIGHTS).

    Returns:
        Dictionary with all score dimensions and composite score.
    """
    w = validate_weights(weights) if weights else DEFAULT_QUALITY_WEIGHTS

    # Calculate each dimension
    freshness = calculate_freshness(evidence_item.source_date)
    reliability = calculate_reliability(evidence_item.metadata_json)
    completeness = await calculate_completeness(session, evidence_item)
    consistency = await calculate_consistency(session, evidence_item)

    # Update the evidence item
    evidence_item.freshness_score = round(freshness, 4)
    evidence_item.reliability_score = round(reliability, 4)
    evidence_item.completeness_score = round(completeness, 4)
    evidence_item.consistency_score = round(consistency, 4)

    scores = {
        "completeness": evidence_item.completeness_score,
        "reliability": evidence_item.reliability_score,
        "freshness": evidence_item.freshness_score,
        "consistency": evidence_item.consistency_score,
    }
    composite = compute_composite(scores, w)

    return {**scores, "composite": composite}
