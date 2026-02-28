"""Claim write-back routes for ingesting SurveyClaims into Neo4j (Story #324).

Provides endpoints for ingesting claims into the knowledge graph,
creating SUPPORTS/CONTRADICTS edges, and recomputing activity confidence.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.models.survey import SurveyClaim
from src.core.permissions import require_engagement_access, require_permission
from src.semantic.claim_write_back import ClaimWriteBackService
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["claim-write-back"])


# ── Schemas ────────────────────────────────────────────────────────────


class IngestClaimPayload(BaseModel):
    """Payload for ingesting a single claim into the knowledge graph."""

    claim_id: uuid.UUID
    target_activity_id: str | None = None


class BatchIngestPayload(BaseModel):
    """Payload for batch ingesting claims."""

    claim_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    target_activity_ids: dict[str, str] | None = Field(
        None,
        description="Mapping of claim_id (string) -> activity_id",
    )


class RecomputeConfidencePayload(BaseModel):
    """Payload for recomputing activity confidence."""

    activity_id: str


# ── Ingest Single Claim ───────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/claims/ingest",
    status_code=status.HTTP_201_CREATED,
)
async def ingest_claim(
    engagement_id: uuid.UUID,
    payload: IngestClaimPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Ingest a single SurveyClaim into the Neo4j knowledge graph.

    Creates a Claim node, links it to the target activity via
    SUPPORTS or CONTRADICTS edge based on certainty tier.
    Auto-creates ConflictObject for contradicted claims.
    """
    # Look up the claim
    stmt = select(SurveyClaim).where(
        SurveyClaim.id == payload.claim_id,
        SurveyClaim.engagement_id == engagement_id,
    )
    result = await session.execute(stmt)
    claim = result.scalar_one_or_none()

    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found in this engagement",
        )

    graph = KnowledgeGraphService(request.app.state.neo4j_driver)
    service = ClaimWriteBackService(graph=graph, session=session)

    ingest_result = await service.ingest_claim(
        claim,
        target_activity_id=payload.target_activity_id,
    )
    await session.commit()

    return ingest_result


# ── Batch Ingest Claims ──────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/claims/batch-ingest",
    status_code=status.HTTP_201_CREATED,
)
async def batch_ingest_claims(
    engagement_id: uuid.UUID,
    payload: BatchIngestPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Batch ingest multiple SurveyClaims into the knowledge graph."""
    # Look up all claims
    stmt = select(SurveyClaim).where(
        SurveyClaim.id.in_(payload.claim_ids),
        SurveyClaim.engagement_id == engagement_id,
    )
    result = await session.execute(stmt)
    claims = list(result.scalars().all())

    if not claims:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No claims found in this engagement",
        )

    # Build target mapping: claim UUID -> activity_id
    target_map: dict[uuid.UUID, str] | None = None
    if payload.target_activity_ids:
        target_map = {uuid.UUID(k): v for k, v in payload.target_activity_ids.items()}

    graph = KnowledgeGraphService(request.app.state.neo4j_driver)
    service = ClaimWriteBackService(graph=graph, session=session)

    batch_result = await service.batch_ingest_claims(claims, target_map)
    await session.commit()

    return batch_result


# ── Recompute Activity Confidence ────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/claims/recompute-confidence",
)
async def recompute_confidence(
    engagement_id: uuid.UUID,
    payload: RecomputeConfidencePayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Recompute confidence score for an activity based on all claim weights."""
    graph = KnowledgeGraphService(request.app.state.neo4j_driver)
    service = ClaimWriteBackService(graph=graph, session=session)

    return await service.recompute_activity_confidence(
        payload.activity_id,
        engagement_id,
    )
