"""Duplicate detection for evidence items.

Uses SHA-256 content hashing to identify exact duplicates within
an engagement. Provides utilities for flagging and managing duplicates.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EvidenceItem


async def find_duplicates_by_hash(
    session: AsyncSession,
    content_hash: str,
    engagement_id: uuid.UUID,
    exclude_id: uuid.UUID | None = None,
) -> list[EvidenceItem]:
    """Find all evidence items with the same content hash in an engagement.

    Args:
        session: Database session.
        content_hash: SHA-256 hash to search for.
        engagement_id: The engagement to search within.
        exclude_id: Optional evidence item ID to exclude from results.

    Returns:
        List of matching EvidenceItem records.
    """
    query = select(EvidenceItem).where(
        EvidenceItem.engagement_id == engagement_id,
        EvidenceItem.content_hash == content_hash,
    )

    if exclude_id is not None:
        query = query.where(EvidenceItem.id != exclude_id)

    result = await session.execute(query)
    return list(result.scalars().all())


async def check_is_duplicate(
    session: AsyncSession,
    content_hash: str,
    engagement_id: uuid.UUID,
) -> uuid.UUID | None:
    """Check if a content hash already exists in the engagement.

    Args:
        session: Database session.
        content_hash: SHA-256 hash to check.
        engagement_id: The engagement to check within.

    Returns:
        The UUID of the existing evidence item if found, else None.
    """
    result = await session.execute(
        select(EvidenceItem.id).where(
            EvidenceItem.engagement_id == engagement_id,
            EvidenceItem.content_hash == content_hash,
        )
    )
    return result.scalar_one_or_none()


async def get_duplicate_groups(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> dict[str, list[uuid.UUID]]:
    """Get all groups of duplicate evidence in an engagement.

    Returns a mapping of content_hash -> list of evidence IDs that share
    that hash (only groups with 2+ items).

    Args:
        session: Database session.
        engagement_id: The engagement to analyze.

    Returns:
        Dictionary mapping content hash to list of evidence item IDs.
    """
    result = await session.execute(
        select(EvidenceItem.content_hash, EvidenceItem.id).where(
            EvidenceItem.engagement_id == engagement_id,
            EvidenceItem.content_hash.isnot(None),
        )
    )

    # Group by hash
    hash_groups: dict[str, list[uuid.UUID]] = {}
    for row in result:
        content_hash = row[0]
        item_id = row[1]
        if content_hash not in hash_groups:
            hash_groups[content_hash] = []
        hash_groups[content_hash].append(item_id)

    # Only return groups with duplicates (2+ items)
    return {h: ids for h, ids in hash_groups.items() if len(ids) >= 2}
