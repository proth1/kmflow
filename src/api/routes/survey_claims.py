"""Survey claim CRUD and certainty tier management routes (Story #322).

Provides endpoints for querying claims with filtering, updating certainty
tiers with history tracking, and auto-generating shelf data requests
from SUSPECTED claims.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.models.survey import CertaintyTier, ProbeType, SurveyClaim
from src.core.permissions import require_engagement_access, require_permission
from src.core.services.survey_claim_service import SurveyClaimService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["survey-claims"])


# ── Helpers ────────────────────────────────────────────────────────────


async def _get_claim_engagement_id(claim_id: UUID, session: AsyncSession) -> UUID:
    """Look up a claim's engagement_id, raising 404 if not found."""
    stmt = select(SurveyClaim.engagement_id).where(SurveyClaim.id == claim_id)
    result = await session.execute(stmt)
    engagement_id = result.scalar_one_or_none()
    if engagement_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return engagement_id


# ── Schemas ────────────────────────────────────────────────────────────


class UpdateCertaintyTierPayload(BaseModel):
    """Payload for updating a claim's certainty tier."""

    certainty_tier: CertaintyTier


# ── Endpoints ──────────────────────────────────────────────────────────


@router.get("/engagements/{engagement_id}/survey-claims")
async def list_survey_claims(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    certainty_tier: CertaintyTier | None = Query(None),
    probe_type: ProbeType | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List survey claims with optional filters and pagination."""
    service = SurveyClaimService(session)
    return await service.query_claims(
        engagement_id,
        certainty_tier=certainty_tier,
        probe_type=probe_type,
        limit=limit,
        offset=offset,
    )


@router.get("/engagements/{engagement_id}/survey-claims/{claim_id}")
async def get_survey_claim(
    engagement_id: UUID,
    claim_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get a single survey claim by ID."""
    service = SurveyClaimService(session)
    claim = await service.get_claim(claim_id)
    if claim is None or claim.engagement_id != engagement_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return {
        "id": str(claim.id),
        "engagement_id": str(claim.engagement_id),
        "session_id": str(claim.session_id),
        "probe_type": claim.probe_type.value,
        "respondent_role": claim.respondent_role,
        "claim_text": claim.claim_text,
        "certainty_tier": claim.certainty_tier.value,
        "proof_expectation": claim.proof_expectation,
        "created_at": claim.created_at.isoformat(),
    }


@router.patch("/engagements/{engagement_id}/survey-claims/{claim_id}")
async def update_survey_claim(
    engagement_id: UUID,
    claim_id: UUID,
    payload: UpdateCertaintyTierPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Update a claim's certainty tier with history tracking."""
    service = SurveyClaimService(session)
    result = await service.update_certainty_tier(
        claim_id=claim_id,
        new_tier=payload.certainty_tier,
        changed_by=user.id,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if result.get("error") == "no_change":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Claim already at tier {result['current_tier']}",
        )
    return result


@router.post(
    "/engagements/{engagement_id}/survey-claims/{claim_id}/shelf-data-request",
    status_code=status.HTTP_201_CREATED,
)
async def create_shelf_data_request_from_claim(
    engagement_id: UUID,
    claim_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Auto-generate a shelf data request from a SUSPECTED claim."""
    service = SurveyClaimService(session)
    result = await service.create_shelf_data_request(claim_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    if result.get("error") == "not_suspected":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Shelf data requests can only be generated for SUSPECTED claims",
        )
    if result.get("error") == "no_proof_expectation":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Claim has no proof_expectation field",
        )
    return result


@router.get("/engagements/{engagement_id}/survey-claims/{claim_id}/history")
async def get_claim_history(
    engagement_id: UUID,
    claim_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get the certainty tier transition history for a claim."""
    service = SurveyClaimService(session)
    claim = await service.get_claim(claim_id)
    if claim is None or claim.engagement_id != engagement_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    history = await service.get_claim_history(claim_id)
    return {"claim_id": str(claim_id), "history": history}
