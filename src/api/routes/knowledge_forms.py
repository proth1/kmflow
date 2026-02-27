"""Knowledge Forms coverage and gap detection routes.

Provides endpoints for computing the 9 universal process knowledge forms
coverage per engagement, and listing knowledge gaps.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import Engagement, User
from src.core.permissions import require_engagement_access, require_permission
from src.governance.knowledge_forms import KnowledgeFormsCoverageService
from src.semantic.graph import KnowledgeGraphService

router = APIRouter(prefix="/api/v1/engagements", tags=["knowledge-forms"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class FormCoverageEntry(BaseModel):
    """Coverage for a single knowledge form."""

    form_number: int
    form_name: str
    covered_count: int
    total_count: int
    coverage_percentage: float


class ActivityGapEntry(BaseModel):
    """A gap in an activity's knowledge form coverage."""

    form_number: int
    form_name: str


class ActivityCoverageEntry(BaseModel):
    """Per-activity coverage breakdown."""

    activity_id: str
    forms_present: list[int]
    gaps: list[ActivityGapEntry]
    completeness_score: float


class KnowledgeCoverageResponse(BaseModel):
    """Full knowledge coverage response for an engagement."""

    engagement_id: UUID
    total_activities: int
    forms: list[FormCoverageEntry]
    per_activity: list[ActivityCoverageEntry]
    overall_completeness: float


class KnowledgeGapEntry(BaseModel):
    """A single knowledge gap entry."""

    activity_id: str
    form_number: int
    form_name: str
    gap_type: str
    suggested_probe_type: str


class KnowledgeGapsResponse(BaseModel):
    """Knowledge gaps listing for an engagement."""

    engagement_id: UUID
    total_gaps: int
    gaps: list[KnowledgeGapEntry]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{engagement_id}/knowledge-coverage",
    response_model=KnowledgeCoverageResponse,
)
async def get_knowledge_coverage(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute knowledge form coverage for all activities in an engagement.

    Returns per-form coverage percentages, per-activity completeness
    scores, and an overall engagement-level completeness metric.
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    coverage_service = KnowledgeFormsCoverageService(graph_service)

    result = await coverage_service.compute_engagement_coverage(str(engagement_id))
    return result


@router.get(
    "/{engagement_id}/knowledge-gaps",
    response_model=KnowledgeGapsResponse,
)
async def get_knowledge_gaps(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List all knowledge form gaps for an engagement.

    Each gap entry includes the activity_id, form number, gap type,
    and a suggested probe type for targeted evidence acquisition.
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    coverage_service = KnowledgeFormsCoverageService(graph_service)

    gaps = await coverage_service.compute_knowledge_gaps(str(engagement_id))
    return {
        "engagement_id": engagement_id,
        "total_gaps": len(gaps),
        "gaps": gaps,
    }
