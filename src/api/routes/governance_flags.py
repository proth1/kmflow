"""Governance flag detection routes (Story #381).

Endpoint to run governance checks on a suggestion's role changes.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.governance.flag_detector import GovernanceFlagDetector
from src.core.models import AlternativeSuggestion, User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["governance-flags"])


class GovernanceCheckRequest(BaseModel):
    """Request payload for governance flag detection."""

    role_changes: list[dict[str, Any]] = []
    affected_element_ids: list[str] = []
    regulated_elements: dict[str, list[str]] | None = None


@router.post(
    "/engagements/{engagement_id}/scenarios/{scenario_id}/suggestions/{suggestion_id}/governance-check",
)
async def check_governance_flags(
    engagement_id: UUID,
    scenario_id: UUID,
    suggestion_id: UUID,
    payload: GovernanceCheckRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Run governance checks on a suggestion and update its governance_flags."""
    result = await session.execute(
        select(AlternativeSuggestion)
        .where(AlternativeSuggestion.id == suggestion_id)
        .where(AlternativeSuggestion.scenario_id == scenario_id)
        .where(AlternativeSuggestion.engagement_id == engagement_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    detector = GovernanceFlagDetector(
        regulated_elements=payload.regulated_elements or {},
    )
    flags = detector.check({
        "role_changes": payload.role_changes,
        "affected_element_ids": payload.affected_element_ids,
    })

    flag_dicts = [f.to_dict() for f in flags]
    suggestion.governance_flags = flag_dicts if flag_dicts else None
    await session.commit()

    return {
        "suggestion_id": str(suggestion_id),
        "governance_flags": flag_dicts,
        "flag_count": len(flag_dicts),
    }
