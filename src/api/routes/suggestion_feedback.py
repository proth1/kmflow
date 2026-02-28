"""LLM suggestion feedback and traceability routes (Story #390).

Provides:
- Traceability chain: modification → suggestion → audit log
- Rejection feedback listing for an engagement
- Exclusion prompt generation for rejected patterns
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    EngagementMember,
    SimulationScenario,
    User,
    UserRole,
)
from src.core.permissions import require_permission
from src.core.services.suggestion_feedback import (
    build_exclusion_prompt,
    build_traceability_chain,
    get_rejection_patterns,
)

router = APIRouter(prefix="/api/v1", tags=["suggestion-feedback"])


@router.get("/scenarios/{scenario_id}/modifications/{modification_id}/traceability")
async def get_modification_traceability(
    scenario_id: UUID,
    modification_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get full traceability chain for a modification.

    Returns: modification → AlternativeSuggestion → LLMAuditLog entry.
    """
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    chain = await build_traceability_chain(session, scenario_id, modification_id)
    if chain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Modification not found in this scenario",
        )
    return chain


@router.get("/engagements/{engagement_id}/rejection-feedback")
async def list_rejection_feedback(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List all rejected suggestion patterns for an engagement."""
    await _check_engagement_member(session, user, engagement_id)

    patterns = await get_rejection_patterns(session, engagement_id)
    return {
        "engagement_id": str(engagement_id),
        "rejection_count": len(patterns),
        "patterns": patterns,
    }


@router.get("/engagements/{engagement_id}/rejection-feedback/exclusion-prompt")
async def get_exclusion_prompt(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Generate exclusion prompt text from rejected patterns.

    This text is injected into the LLM system prompt before generating
    new suggestions to avoid repeating previously rejected patterns.
    """
    await _check_engagement_member(session, user, engagement_id)

    patterns = await get_rejection_patterns(session, engagement_id)
    prompt_text = build_exclusion_prompt(patterns)
    return {
        "engagement_id": str(engagement_id),
        "pattern_count": len(patterns),
        "exclusion_prompt": prompt_text,
    }


# -- Helpers -------------------------------------------------------------------


async def _get_scenario(session: AsyncSession, scenario_id: UUID) -> SimulationScenario:
    """Load a scenario or 404."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found",
        )
    return scenario


async def _check_engagement_member(session: AsyncSession, user: User, engagement_id: UUID) -> None:
    """Verify user is a member of the engagement. Platform admins bypass."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return
    result = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this engagement",
        )
