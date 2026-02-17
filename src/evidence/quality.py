"""Evidence quality scoring engine.

Calculates four quality dimensions per evidence item:
- Completeness: proportion of shelf request items matched
- Reliability: source credibility score based on metadata
- Freshness: decay function based on document date vs current date
- Consistency: agreement with other evidence in the same engagement
"""

from __future__ import annotations

import math
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    EvidenceItem,
    ShelfDataRequestItem,
    ShelfRequestItemStatus,
)

# Weights for composite quality score calculation
QUALITY_WEIGHTS = {
    "completeness": 0.30,
    "reliability": 0.25,
    "freshness": 0.25,
    "consistency": 0.20,
}

# Freshness decay half-life in days (documents lose half their freshness after this many days)
FRESHNESS_HALF_LIFE_DAYS = 365

# Reliability score mapping by source type / metadata indicators
RELIABILITY_BY_SOURCE: dict[str, float] = {
    "official": 1.0,
    "verified": 0.9,
    "internal": 0.8,
    "third_party": 0.7,
    "client_provided": 0.6,
    "unknown": 0.4,
}


def calculate_freshness(source_date: date | datetime | None, reference_date: date | None = None) -> float:
    """Calculate freshness score using exponential decay.

    Score decays from 1.0 based on how old the document is relative
    to the half-life period.

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
    if days_old < 0:
        return 1.0  # Future date treated as fresh

    # Exponential decay: score = exp(-lambda * days_old)
    # where lambda = ln(2) / half_life
    decay_constant = math.log(2) / FRESHNESS_HALF_LIFE_DAYS
    return math.exp(-decay_constant * days_old)


def calculate_reliability(metadata: dict | None) -> float:
    """Calculate reliability score based on evidence metadata.

    Examines metadata for source type, verification status, and
    other credibility indicators.

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

    # Count fulfilled items
    received_result = await session.execute(
        select(func.count())
        .select_from(ShelfDataRequestItem)
        .join(
            ShelfDataRequestItem.request,
        )
        .where(
            ShelfDataRequestItem.category == evidence_item.category,
            ShelfDataRequestItem.status == ShelfRequestItemStatus.RECEIVED,
        )
    )
    received_items = received_result.scalar() or 0

    return received_items / total_items


async def calculate_consistency(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> float:
    """Calculate consistency with other evidence in the same engagement.

    For MVP, measures whether there are multiple evidence items in the
    same category (more items = higher confidence in consistency).

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

    # More related evidence items increases consistency (diminishing returns)
    # score = 1 - 1/(1 + count), approaches 1.0 as count increases
    return 1.0 - 1.0 / (1.0 + related_count)


async def score_evidence(
    session: AsyncSession,
    evidence_item: EvidenceItem,
) -> dict[str, float]:
    """Calculate all quality dimensions for an evidence item.

    Updates the evidence item's quality scores in place.

    Args:
        session: Database session.
        evidence_item: The evidence item to score.

    Returns:
        Dictionary with all score dimensions and composite score.
    """
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

    composite = (
        QUALITY_WEIGHTS["completeness"] * completeness
        + QUALITY_WEIGHTS["reliability"] * reliability
        + QUALITY_WEIGHTS["freshness"] * freshness
        + QUALITY_WEIGHTS["consistency"] * consistency
    )

    return {
        "completeness": evidence_item.completeness_score,
        "reliability": evidence_item.reliability_score,
        "freshness": evidence_item.freshness_score,
        "consistency": evidence_item.consistency_score,
        "composite": round(composite, 4),
    }
