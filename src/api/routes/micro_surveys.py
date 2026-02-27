"""Micro-survey API endpoints for telemetry-triggered survey management (Story #398).

Provides POST /api/v1/micro-surveys for generating micro-surveys from deviations,
and POST /api/v1/micro-surveys/{survey_id}/respond for submitting SME responses.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import MicroSurveyStatus, ProbeType, User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/micro-surveys", tags=["micro-surveys"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GenerateMicroSurveyRequest(BaseModel):
    """Request to generate a micro-survey from a process deviation."""

    engagement_id: UUID
    deviation_id: UUID
    target_sme_role: str = "process_owner"
    anomaly_threshold: float = Field(default=2.0, gt=0)


class ProbeResponse(BaseModel):
    """A single probe response from an SME."""

    probe_type: ProbeType
    claim_text: str
    certainty_tier: str = Field(pattern=r"^(known|suspected|unknown|contradicted)$")


class SubmitResponseRequest(BaseModel):
    """Request to submit SME responses to a micro-survey."""

    responses: list[ProbeResponse]
    respondent_role: str


class MicroSurveyResponse(BaseModel):
    """Response schema for a micro-survey."""

    id: UUID
    engagement_id: UUID
    triggering_deviation_id: UUID | None = None
    target_element_id: str
    target_element_name: str
    target_sme_role: str
    anomaly_description: str
    probes: list[dict[str, str]]
    status: MicroSurveyStatus

    model_config = {"from_attributes": True}


class ClaimSummary(BaseModel):
    """Summary of a created SurveyClaim."""

    probe_type: str
    claim_text: str
    certainty_tier: str
    micro_survey_id: str


class SubmitResponseResponse(BaseModel):
    """Response for micro-survey submission."""

    claims: list[ClaimSummary]
    survey_status: MicroSurveyStatus


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=MicroSurveyResponse, status_code=status.HTTP_201_CREATED)
async def generate_micro_survey(
    body: GenerateMicroSurveyRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("survey:write")),
) -> Any:
    """Generate a micro-survey from a detected process deviation.

    Looks up the deviation, checks the anomaly threshold, and generates
    a targeted 2-3 probe micro-survey for the relevant SME.
    """
    from sqlalchemy import select

    from src.api.services.micro_survey import MicroSurveyService
    from src.core.models import ProcessDeviation

    result = await session.execute(
        select(ProcessDeviation).where(ProcessDeviation.id == body.deviation_id)
    )
    deviation = result.scalar_one_or_none()
    if deviation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deviation {body.deviation_id} not found",
        )

    service = MicroSurveyService(session)
    survey = await service.generate_micro_survey(
        engagement_id=body.engagement_id,
        deviation=deviation,
        target_sme_role=body.target_sme_role,
        anomaly_threshold=body.anomaly_threshold,
    )

    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Deviation does not exceed anomaly threshold; no survey generated",
        )

    return survey


@router.post("/{survey_id}/respond", response_model=SubmitResponseResponse)
async def submit_survey_response(
    survey_id: UUID,
    body: SubmitResponseRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("survey:write")),
) -> dict[str, Any]:
    """Submit SME responses to a micro-survey.

    Creates SurveyClaim entities linked to the micro-survey and updates
    the survey status to RESPONDED.
    """
    from src.api.services.micro_survey import MicroSurveyService

    service = MicroSurveyService(session)
    try:
        claims = await service.submit_response(
            survey_id=survey_id,
            responses=[r.model_dump() for r in body.responses],
            respondent_role=body.respondent_role,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return {
        "claims": claims,
        "survey_status": MicroSurveyStatus.RESPONDED,
    }


@router.get("", response_model=list[MicroSurveyResponse])
async def list_micro_surveys(
    engagement_id: UUID = Query(..., description="Filter by engagement"),
    status_filter: MicroSurveyStatus | None = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("survey:read")),
) -> Any:
    """List micro-surveys for an engagement with optional status filter."""
    from sqlalchemy import select

    from src.core.models import MicroSurvey

    query = select(MicroSurvey).where(MicroSurvey.engagement_id == engagement_id)
    if status_filter is not None:
        query = query.where(MicroSurvey.status == status_filter)
    query = query.order_by(MicroSurvey.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    return result.scalars().all()
