"""Evidence aggregation for the LCD algorithm.

Step 1: Filters evidence by engagement and scope, collects validated items
and their fragments for downstream processing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.models import EvidenceFragment, EvidenceItem, ValidationStatus

logger = logging.getLogger(__name__)


@dataclass
class AggregatedEvidence:
    """Collection of evidence items and fragments for POV generation.

    Attributes:
        engagement_id: The engagement being processed.
        scope: The scope filter applied.
        evidence_items: List of validated evidence items.
        fragments: List of evidence fragments from validated items.
        evidence_count: Number of evidence items collected.
        fragment_count: Number of fragments collected.
    """

    engagement_id: str = ""
    scope: str = ""
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    fragments: list[EvidenceFragment] = field(default_factory=list)
    evidence_count: int = 0
    fragment_count: int = 0


async def aggregate_evidence(
    session: AsyncSession,
    engagement_id: str,
    scope: str | None = None,
) -> AggregatedEvidence:
    """Aggregate validated evidence for an engagement.

    Filters evidence items by engagement ID and validation status.
    Optionally filters by scope (matched against category or name).
    Loads related fragments eagerly for downstream processing.

    Args:
        session: Async database session.
        engagement_id: The engagement to aggregate evidence for.
        scope: Optional scope filter (matched against category name).

    Returns:
        AggregatedEvidence containing items and fragments.
    """
    query = (
        select(EvidenceItem)
        .options(selectinload(EvidenceItem.fragments))
        .where(EvidenceItem.engagement_id == engagement_id)
        .where(EvidenceItem.validation_status.in_([ValidationStatus.VALIDATED, ValidationStatus.ACTIVE]))
        .where(EvidenceItem.duplicate_of_id.is_(None))
    )

    # Apply scope filter if provided
    if scope:
        # Scope filters by category name (case-insensitive partial match)
        query = query.where(EvidenceItem.category.ilike(f"%{scope}%") | EvidenceItem.name.ilike(f"%{scope}%"))

    result = await session.execute(query)
    evidence_items = list(result.scalars().unique().all())

    # Collect all fragments from loaded evidence items
    all_fragments: list[EvidenceFragment] = []
    for item in evidence_items:
        all_fragments.extend(item.fragments)

    aggregated = AggregatedEvidence(
        engagement_id=engagement_id,
        scope=scope or "all",
        evidence_items=evidence_items,
        fragments=all_fragments,
        evidence_count=len(evidence_items),
        fragment_count=len(all_fragments),
    )

    logger.info(
        "Aggregated %d evidence items (%d fragments) for engagement %s, scope '%s'",
        aggregated.evidence_count,
        aggregated.fragment_count,
        engagement_id,
        scope or "all",
    )

    return aggregated
