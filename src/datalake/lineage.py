"""Evidence lineage service for tracking provenance and transformation history.

Creates and manages ``EvidenceLineage`` records that track where evidence
came from, how it was transformed, and support versioning for incremental
refresh scenarios.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import EvidenceItem, EvidenceLineage

logger = logging.getLogger(__name__)


async def create_lineage_record(
    session: AsyncSession,
    evidence_item: EvidenceItem,
    source_system: str = "direct_upload",
    source_url: str | None = None,
    source_identifier: str | None = None,
    transformation_steps: list[dict[str, Any]] | None = None,
    content_hash: str | None = None,
) -> EvidenceLineage:
    """Create a lineage record for an evidence item and link it.

    This should be called during evidence ingestion after the item is
    created. It records the provenance and sets the initial transformation
    chain.

    Args:
        session: Database session.
        evidence_item: The evidence item to create lineage for.
        source_system: Where the evidence came from (e.g., 'direct_upload',
            'salesforce', 'sharepoint', 'email').
        source_url: Optional URL to the source.
        source_identifier: Optional external identifier in the source system.
        transformation_steps: Initial transformation chain entries.
        content_hash: SHA-256 of the original content for version tracking.

    Returns:
        The created EvidenceLineage record.
    """
    # Check if lineage already exists for this evidence item
    existing = await session.execute(
        select(EvidenceLineage).where(
            EvidenceLineage.evidence_item_id == evidence_item.id
        )
    )
    existing_lineage = existing.scalar_one_or_none()
    if existing_lineage:
        logger.debug("Lineage already exists for evidence item %s", evidence_item.id)
        return existing_lineage

    # Build initial transformation chain
    chain = transformation_steps or []
    if not chain:
        chain = [
            {
                "step": "ingestion",
                "action": "uploaded",
                "source": source_system,
                "file_name": evidence_item.name,
                "timestamp": evidence_item.created_at.isoformat()
                if evidence_item.created_at
                else None,
            }
        ]

    lineage = EvidenceLineage(
        evidence_item_id=evidence_item.id,
        source_system=source_system,
        source_url=source_url,
        source_identifier=source_identifier,
        transformation_chain=chain,
        version=1,
        version_hash=content_hash
        or hashlib.sha256(str(evidence_item.id).encode()).hexdigest(),
    )
    session.add(lineage)
    await session.flush()

    # Link the lineage record to the evidence item
    evidence_item.lineage_id = lineage.id
    evidence_item.source_system = source_system

    logger.info(
        "Created lineage record %s for evidence item %s (source: %s)",
        lineage.id,
        evidence_item.id,
        source_system,
    )

    return lineage


async def append_transformation(
    session: AsyncSession,
    lineage_id: uuid.UUID,
    step_name: str,
    details: dict[str, Any] | None = None,
) -> EvidenceLineage:
    """Append a transformation step to an existing lineage record.

    Used by the intelligence pipeline to record each processing step
    (parsing, entity extraction, graph building, embedding generation).

    Args:
        session: Database session.
        lineage_id: The lineage record to update.
        step_name: Name of the transformation step.
        details: Optional details about the transformation.

    Returns:
        Updated EvidenceLineage record.

    Raises:
        ValueError: If the lineage record is not found.
    """
    result = await session.execute(
        select(EvidenceLineage).where(EvidenceLineage.id == lineage_id)
    )
    lineage = result.scalar_one_or_none()
    if not lineage:
        raise ValueError(f"Lineage record {lineage_id} not found")

    chain = lineage.transformation_chain or []
    chain.append({
        "step": step_name,
        **(details or {}),
    })
    lineage.transformation_chain = chain

    return lineage


async def get_lineage_chain(
    session: AsyncSession,
    evidence_item_id: uuid.UUID,
) -> list[EvidenceLineage]:
    """Get the full lineage chain for an evidence item.

    Follows the ``parent_version_id`` chain to reconstruct the complete
    version history.

    Args:
        session: Database session.
        evidence_item_id: The evidence item to get lineage for.

    Returns:
        List of EvidenceLineage records, newest first.
    """
    result = await session.execute(
        select(EvidenceLineage)
        .where(EvidenceLineage.evidence_item_id == evidence_item_id)
        .order_by(EvidenceLineage.version.desc())
    )
    return list(result.scalars().all())


async def get_lineage_by_id(
    session: AsyncSession,
    lineage_id: uuid.UUID,
) -> EvidenceLineage | None:
    """Get a single lineage record by ID."""
    result = await session.execute(
        select(EvidenceLineage).where(EvidenceLineage.id == lineage_id)
    )
    return result.scalar_one_or_none()
