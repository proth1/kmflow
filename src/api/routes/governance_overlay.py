"""Governance overlay routes for process models.

Provides the governance overlay API that decorates process model activities
with their governance coverage status (governed, partially governed, ungoverned).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.governance_overlay import GovernanceOverlayService
from src.core.models import EngagementMember, ProcessModel, User, UserRole
from src.core.permissions import require_permission
from src.semantic.graph import KnowledgeGraphService

router = APIRouter(prefix="/api/v1/process-models", tags=["governance-overlay"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GovernanceEntityRef(BaseModel):
    """Reference to a governance entity (policy, control, or regulation)."""

    id: str
    name: str


class ActivityGovernanceEntry(BaseModel):
    """Governance overlay entry for a single activity."""

    activity_id: str
    activity_name: str
    governance_status: str
    policy: GovernanceEntityRef | None = None
    control: GovernanceEntityRef | None = None
    regulation: GovernanceEntityRef | None = None


class GovernanceGapEntry(BaseModel):
    """An ungoverned activity gap."""

    activity_id: str
    activity_name: str
    gap_type: str


class GovernanceOverlayResponse(BaseModel):
    """Full governance overlay for a process model."""

    process_model_id: UUID
    engagement_id: UUID
    activities: list[ActivityGovernanceEntry]
    governance_gaps: list[GovernanceGapEntry]
    overall_coverage_percentage: float
    total_activities: int
    governed_count: int
    partially_governed_count: int
    ungoverned_count: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{process_model_id}/governance-overlay",
    response_model=GovernanceOverlayResponse,
)
async def get_governance_overlay(
    process_model_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
) -> dict[str, Any]:
    """Compute governance overlay for a process model.

    Returns per-activity governance status (governed, partially_governed,
    ungoverned) with full governance chain details and gap summary.
    """
    # Verify process model exists and get engagement_id
    pm_result = await session.execute(select(ProcessModel).where(ProcessModel.id == process_model_id))
    pm = pm_result.scalar_one_or_none()
    if not pm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process model not found",
        )

    # Engagement-scoped access check (IDOR prevention)
    if user.role != UserRole.PLATFORM_ADMIN:
        member_result = await session.execute(
            select(EngagementMember).where(
                EngagementMember.engagement_id == pm.engagement_id,
                EngagementMember.user_id == user.id,
            )
        )
        if member_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this engagement",
            )

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    overlay_service = GovernanceOverlayService(graph_service)

    result = await overlay_service.compute_overlay(str(process_model_id), str(pm.engagement_id))

    return result
