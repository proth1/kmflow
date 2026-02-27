"""Survey session and bot routes (Story #319).

Provides endpoints for survey session lifecycle management,
probe generation, and claim creation.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.models.seed_term import SeedTerm, TermStatus
from src.core.models.survey import CertaintyTier, ProbeType
from src.core.models.survey_session import SurveySessionStatus
from src.core.permissions import require_engagement_access, require_permission
from src.core.services.survey_bot_service import SurveyBotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["survey-sessions"])


# ── Schemas ────────────────────────────────────────────────────────────


class CreateSessionPayload(BaseModel):
    """Payload for creating a survey session."""

    respondent_role: str = Field(..., min_length=1, max_length=255)


class CreateClaimPayload(BaseModel):
    """Payload for creating a survey claim."""

    probe_type: ProbeType
    claim_text: str = Field(..., min_length=1)
    certainty_tier: CertaintyTier
    proof_expectation: str | None = None
    related_seed_terms: list[str] | None = None


# ── Session Lifecycle ──────────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/survey-sessions",
    status_code=status.HTTP_201_CREATED,
)
async def create_survey_session(
    engagement_id: UUID,
    payload: CreateSessionPayload,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Create a new survey session for an engagement."""
    service = SurveyBotService(session)
    return await service.create_session(
        engagement_id=engagement_id,
        respondent_role=payload.respondent_role,
    )


@router.get("/engagements/{engagement_id}/survey-sessions")
async def list_survey_sessions(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    status_filter: SurveySessionStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List survey sessions for an engagement."""
    service = SurveyBotService(session)
    return await service.list_sessions(
        engagement_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/engagements/{engagement_id}/survey-sessions/{session_id}")
async def get_survey_session(
    engagement_id: UUID,
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get a single survey session."""
    service = SurveyBotService(session)
    session_obj = await service.get_session(session_id)
    if session_obj is None or session_obj.engagement_id != engagement_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey session not found",
        )
    return {
        "id": str(session_obj.id),
        "engagement_id": str(session_obj.engagement_id),
        "respondent_role": session_obj.respondent_role,
        "status": session_obj.status.value,
        "claims_count": session_obj.claims_count,
        "summary": session_obj.summary,
        "created_at": session_obj.created_at.isoformat(),
        "completed_at": session_obj.completed_at.isoformat()
        if session_obj.completed_at
        else None,
    }


@router.patch(
    "/engagements/{engagement_id}/survey-sessions/{session_id}/complete"
)
async def complete_survey_session(
    engagement_id: UUID,
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Mark a survey session as complete and generate summary."""
    service = SurveyBotService(session)

    # Verify session belongs to engagement
    session_obj = await service.get_session(session_id)
    if session_obj is None or session_obj.engagement_id != engagement_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey session not found",
        )

    result = await service.complete_session(session_id)
    if result.get("error") == "invalid_status":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Session is already {result['current_status']}",
        )
    return result


# ── Probe Generation ──────────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/survey-sessions/{session_id}/generate-probes"
)
async def generate_session_probes(
    engagement_id: UUID,
    session_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate probes for a session from active seed terms."""
    from sqlalchemy import select

    service = SurveyBotService(session)

    # Verify session
    session_obj = await service.get_session(session_id)
    if session_obj is None or session_obj.engagement_id != engagement_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey session not found",
        )

    # Get active seed terms for the engagement
    stmt = (
        select(SeedTerm)
        .where(
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        )
        .order_by(SeedTerm.term)
    )
    result = await session.execute(stmt)
    terms = result.scalars().all()

    term_dicts = [
        {"id": str(t.id), "term": t.term, "domain": t.domain, "category": t.category.value}
        for t in terms
    ]

    probes = service.generate_probes_for_terms(
        term_dicts, session_id=session_id
    )

    return {
        "session_id": str(session_id),
        "terms_used": len(term_dicts),
        "probes_generated": len(probes),
        "probes": probes,
    }


# ── Claim Creation ────────────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/survey-sessions/{session_id}/claims",
    status_code=status.HTTP_201_CREATED,
)
async def create_session_claim(
    engagement_id: UUID,
    session_id: UUID,
    payload: CreateClaimPayload,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Create a survey claim from an SME response."""
    service = SurveyBotService(session)

    # Verify session belongs to engagement
    session_obj = await service.get_session(session_id)
    if session_obj is None or session_obj.engagement_id != engagement_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Survey session not found",
        )

    if session_obj.status != SurveySessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot add claims to a non-active session",
        )

    return await service.create_claim(
        engagement_id=engagement_id,
        session_id=session_id,
        probe_type=payload.probe_type,
        respondent_role=session_obj.respondent_role,
        claim_text=payload.claim_text,
        certainty_tier=payload.certainty_tier,
        proof_expectation=payload.proof_expectation,
        related_seed_terms=payload.related_seed_terms,
    )
