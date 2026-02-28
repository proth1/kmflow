"""Evidence gap ranking routes with confidence uplift projection.

Provides endpoints for computing uplift projections, detecting
cross-scenario shared gaps, and tracking projection accuracy.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.evidence_gap_ranking import EvidenceGapRankingService
from src.core.audit import log_audit
from src.core.models import AuditAction, Engagement, User
from src.core.permissions import require_engagement_access, require_permission
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements", tags=["evidence-gap-ranking"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UpliftProjectionEntry(BaseModel):
    """A single uplift projection for an evidence gap."""

    id: str
    element_id: str
    element_name: str
    evidence_type: str
    current_confidence: float
    projected_confidence: float
    projected_uplift: float
    brightness: str


class UpliftProjectionsResponse(BaseModel):
    """Response for uplift projection computation."""

    engagement_id: UUID
    projections_count: int
    projections: list[UpliftProjectionEntry]


class CrossScenarioGapEntry(BaseModel):
    """A shared gap across multiple scenarios."""

    element_id: str
    element_name: str
    scenario_count: int
    label: str
    combined_estimated_uplift: float


class CrossScenarioGapsResponse(BaseModel):
    """Response for cross-scenario shared gaps."""

    engagement_id: UUID
    shared_gaps: list[CrossScenarioGapEntry]


class UpliftAccuracyResponse(BaseModel):
    """Response for uplift accuracy / correlation."""

    engagement_id: UUID
    resolved_count: int
    correlation: float | None
    meets_target: bool
    target: float
    insufficient_data: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def _get_engagement_or_404(session: AsyncSession, engagement_id: UUID) -> Engagement:
    """Fetch engagement or raise 404."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    eng = eng_result.scalar_one_or_none()
    if not eng:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found",
        )
    return eng


@router.post(
    "/{engagement_id}/uplift-projections",
    response_model=UpliftProjectionsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def compute_uplift_projections(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute confidence uplift projections for Dark/Dim elements.

    Projects the confidence increase from obtaining each evidence type
    for each element. Persists projections for accuracy tracking.
    """
    await _get_engagement_or_404(session, engagement_id)

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    service = EvidenceGapRankingService(session, graph_service)

    projections = await service.compute_uplift_projections(str(engagement_id))
    count = await service.persist_projections(str(engagement_id), projections)

    await log_audit(
        session,
        engagement_id,
        AuditAction.EVIDENCE_VALIDATED,
        f"Computed {count} uplift projections",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "engagement_id": engagement_id,
        "projections_count": len(projections),
        "projections": projections,
    }


@router.get(
    "/{engagement_id}/cross-scenario-gaps",
    response_model=CrossScenarioGapsResponse,
)
async def get_cross_scenario_gaps(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get elements that are shared gaps across multiple scenarios.

    Returns elements modified in 2+ scenarios with combined uplift estimate.
    """
    await _get_engagement_or_404(session, engagement_id)

    service = EvidenceGapRankingService(session)
    gaps = await service.get_cross_scenario_gaps(str(engagement_id))

    return {
        "engagement_id": engagement_id,
        "shared_gaps": gaps,
    }


@router.get(
    "/{engagement_id}/uplift-accuracy",
    response_model=UpliftAccuracyResponse,
)
async def get_uplift_accuracy(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get uplift projection accuracy (Pearson correlation).

    Requires minimum 10 resolved projections. Returns correlation
    coefficient and whether it meets the 0.7 target.
    """
    await _get_engagement_or_404(session, engagement_id)

    service = EvidenceGapRankingService(session)
    accuracy = await service.compute_uplift_accuracy(str(engagement_id))

    return accuracy
