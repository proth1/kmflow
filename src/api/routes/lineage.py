"""Evidence lineage API routes.

Exposes the transformation history and provenance chain for evidence items.
Supports the data governance requirement that every piece of evidence can
answer: "Where did this come from? How was it processed?"
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import EvidenceItem, User
from src.core.permissions import require_permission
from src.datalake.lineage import get_lineage_by_id, get_lineage_chain

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/engagements/{engagement_id}/evidence",
    tags=["lineage"],
)


# -- Schemas ------------------------------------------------------------------


class TransformationStep(BaseModel):
    """A single step in the transformation chain."""

    step: str
    action: str | None = None
    source: str | None = None
    file_name: str | None = None
    timestamp: str | None = None


class LineageResponse(BaseModel):
    """Response schema for a single lineage record."""

    model_config = {"from_attributes": True}

    id: UUID
    evidence_item_id: UUID
    source_system: str
    source_url: str | None
    source_identifier: str | None
    transformation_chain: list[dict[str, Any]] | None
    version: int
    version_hash: str | None
    parent_version_id: UUID | None
    refresh_schedule: str | None
    last_refreshed_at: Any | None
    created_at: Any


class LineageChainResponse(BaseModel):
    """Full lineage chain for an evidence item."""

    evidence_item_id: UUID
    evidence_name: str
    source_system: str | None
    total_versions: int
    lineage: list[LineageResponse]


# -- Routes -------------------------------------------------------------------


@router.get("/{evidence_id}/lineage", response_model=LineageChainResponse)
async def get_evidence_lineage(
    engagement_id: UUID,
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get the full lineage chain for an evidence item.

    Returns the provenance information, transformation history, and
    version chain for the specified evidence item.

    Args:
        engagement_id: The engagement scope.
        evidence_id: The evidence item to get lineage for.
    """
    from sqlalchemy import select

    # Verify evidence item exists and belongs to engagement
    result = await session.execute(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.engagement_id == engagement_id,
        )
    )
    evidence_item = result.scalar_one_or_none()
    if not evidence_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found in engagement {engagement_id}",
        )

    # Get lineage chain
    lineage_records = await get_lineage_chain(session, evidence_id)

    return {
        "evidence_item_id": evidence_id,
        "evidence_name": evidence_item.name,
        "source_system": evidence_item.source_system,
        "total_versions": len(lineage_records),
        "lineage": lineage_records,
    }


@router.get("/{evidence_id}/lineage/{lineage_id}", response_model=LineageResponse)
async def get_lineage_record(
    engagement_id: UUID,
    evidence_id: UUID,
    lineage_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Any:
    """Get a specific lineage record by ID.

    Args:
        engagement_id: The engagement scope.
        evidence_id: The evidence item (for URL consistency).
        lineage_id: The lineage record ID.
    """
    from sqlalchemy import select

    # Verify evidence item belongs to engagement
    result = await session.execute(
        select(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.engagement_id == engagement_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found in engagement {engagement_id}",
        )

    lineage = await get_lineage_by_id(session, lineage_id)
    if not lineage or lineage.evidence_item_id != evidence_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lineage record {lineage_id} not found for evidence {evidence_id}",
        )

    return lineage
