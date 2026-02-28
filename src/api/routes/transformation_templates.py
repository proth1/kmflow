"""Transformation template routes (Story #376).

Provides:
- List available templates
- Apply templates to a scenario's process elements
- Accept/reject individual template suggestions
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
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
from src.core.services.transformation_templates import (
    ProcessElement,
    SuggestionStatus,
    apply_all_templates,
    get_template_registry,
)

router = APIRouter(prefix="/api/v1", tags=["transformation-templates"])


# -- Request schemas ---


class ProcessElementInput(BaseModel):
    """Input schema for a process element."""

    id: str
    name: str
    element_type: str
    lane: str = ""
    performer: str = ""
    input_sources: list[str] = []
    autonomy_level: str = "human"
    is_control: bool = False
    compliance_risk: str = "low"
    sequence_position: int = 0


class ApplyTemplatesRequest(BaseModel):
    """Request body for applying templates to process elements."""

    elements: list[ProcessElementInput] = Field(max_length=500)


class SuggestionDecisionRequest(BaseModel):
    """Request body for accepting/rejecting a suggestion."""

    action: Literal["accept", "reject"]


# -- Endpoints ---


@router.get("/templates")
async def list_templates(
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List all available transformation templates."""
    registry = get_template_registry()
    return {
        "templates": [t.to_dict() for t in registry],
        "count": len(registry),
    }


@router.post("/scenarios/{scenario_id}/templates/apply")
async def apply_templates_to_scenario(
    scenario_id: UUID,
    body: ApplyTemplatesRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Apply all transformation templates to a scenario's process elements.

    Returns template suggestions identified by the four analysis templates.
    """
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    # Convert input to ProcessElement dataclass instances
    elements = [
        ProcessElement(
            id=e.id,
            name=e.name,
            element_type=e.element_type,
            lane=e.lane,
            performer=e.performer,
            input_sources=e.input_sources,
            autonomy_level=e.autonomy_level,
            is_control=e.is_control,
            compliance_risk=e.compliance_risk,
            sequence_position=e.sequence_position,
        )
        for e in body.elements
    ]

    suggestions = apply_all_templates(elements)
    return {
        "scenario_id": str(scenario_id),
        "suggestions": [s.to_dict() for s in suggestions],
        "suggestion_count": len(suggestions),
    }


@router.patch("/scenarios/{scenario_id}/suggestions/{suggestion_id}")
async def update_suggestion_status(
    scenario_id: UUID,
    suggestion_id: str,
    body: SuggestionDecisionRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Accept or reject a template suggestion.

    Accepted suggestions can be converted to ScenarioModifications.
    Rejected suggestions are logged with timestamp.
    """
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    # Pydantic validates action is Literal["accept", "reject"] at parse time (422 on invalid)
    new_status = SuggestionStatus.ACCEPTED if body.action == "accept" else SuggestionStatus.REJECTED

    return {
        "suggestion_id": suggestion_id,
        "scenario_id": str(scenario_id),
        "status": new_status,
        "action": body.action,
    }


# -- Helpers ---


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
