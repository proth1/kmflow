"""Scenario Comparison Workbench CRUD routes (Story #373).

Dedicated scenario management endpoints with:
- Max 5 scenarios per engagement enforcement
- Modification CRUD with element_id + JSONB payload
- Scenario listing with modification_count
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.scenarios import (
    ModificationCreatePayload,
    ModificationDetail,
    ModificationListResponse,
    ScenarioCreatePayload,
    ScenarioDetail,
    ScenarioListResponse,
    ScenarioSummary,
)
from src.core.audit import log_audit
from src.core.models import (
    AuditAction,
    ScenarioModification,
    SimulationScenario,
    SimulationType,
    User,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])

MAX_SCENARIOS_PER_ENGAGEMENT = 5


# -- Helpers ------------------------------------------------------------------


def _scenario_to_summary(scenario: SimulationScenario, mod_count: int) -> dict[str, Any]:
    """Serialize a scenario to a summary dict with modification_count."""
    return {
        "id": str(scenario.id),
        "engagement_id": str(scenario.engagement_id),
        "name": scenario.name,
        "description": scenario.description,
        "status": scenario.status or "draft",
        "modification_count": mod_count,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else "",
    }


def _modification_to_detail(mod: ScenarioModification) -> dict[str, Any]:
    """Serialize a modification to a detail dict."""
    return {
        "id": str(mod.id),
        "scenario_id": str(mod.scenario_id),
        "modification_type": mod.modification_type.value
        if hasattr(mod.modification_type, "value")
        else str(mod.modification_type),
        "element_id": mod.element_id,
        "payload": mod.change_data,
        "applied_at": mod.applied_at.isoformat() if mod.applied_at else "",
    }


# -- Scenario Routes ----------------------------------------------------------


@router.post("", response_model=ScenarioSummary, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Create a new scenario with max-5-per-engagement enforcement."""
    # Enforce max scenarios per engagement
    count_result = await session.execute(
        select(func.count(SimulationScenario.id)).where(SimulationScenario.engagement_id == payload.engagement_id)
    )
    current_count = count_result.scalar() or 0

    if current_count >= MAX_SCENARIOS_PER_ENGAGEMENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum of {MAX_SCENARIOS_PER_ENGAGEMENT} scenarios per engagement reached",
        )

    scenario = SimulationScenario(
        engagement_id=payload.engagement_id,
        name=payload.name,
        description=payload.description,
        simulation_type=SimulationType.PROCESS_CHANGE,
        status="draft",
    )
    session.add(scenario)
    await log_audit(
        session,
        payload.engagement_id,
        AuditAction.SIMULATION_CREATED,
        f"Scenario created: {payload.name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(scenario)

    return _scenario_to_summary(scenario, mod_count=0)


@router.get("", response_model=ScenarioListResponse)
async def list_scenarios(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List scenarios for an engagement with modification_count."""
    # Subquery for modification counts per scenario
    mod_count_subq = (
        select(
            ScenarioModification.scenario_id,
            func.count(ScenarioModification.id).label("mod_count"),
        )
        .group_by(ScenarioModification.scenario_id)
        .subquery()
    )

    query = (
        select(SimulationScenario, func.coalesce(mod_count_subq.c.mod_count, 0).label("mod_count"))
        .outerjoin(mod_count_subq, SimulationScenario.id == mod_count_subq.c.scenario_id)
        .where(SimulationScenario.engagement_id == engagement_id)
        .order_by(SimulationScenario.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    rows = result.all()

    items = [_scenario_to_summary(row[0], row[1]) for row in rows]

    count_result = await session.execute(
        select(func.count(SimulationScenario.id)).where(SimulationScenario.engagement_id == engagement_id)
    )
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


@router.get("/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get a scenario by ID with its modifications."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    # Fetch modifications
    mod_result = await session.execute(
        select(ScenarioModification).where(ScenarioModification.scenario_id == scenario_id)
    )
    mods = list(mod_result.scalars().all())

    return {
        **_scenario_to_summary(scenario, mod_count=len(mods)),
        "modifications": [_modification_to_detail(m) for m in mods],
        "updated_at": scenario.created_at.isoformat() if scenario.created_at else None,
    }


# -- Modification Routes ------------------------------------------------------


@router.post(
    "/{scenario_id}/modifications",
    response_model=ModificationDetail,
    status_code=status.HTTP_201_CREATED,
)
async def add_modification(
    scenario_id: UUID,
    payload: ModificationCreatePayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Add a modification to a DRAFT scenario."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    if scenario.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Modifications can only be added to DRAFT scenarios",
        )

    mod = ScenarioModification(
        scenario_id=scenario_id,
        modification_type=payload.modification_type,
        element_id=payload.element_id,
        element_name=payload.element_id,  # use element_id as name fallback
        change_data=payload.payload,
    )
    session.add(mod)
    await log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SCENARIO_MODIFIED,
        f"Added {payload.modification_type} on {payload.element_id}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(mod)

    return _modification_to_detail(mod)


@router.get("/{scenario_id}/modifications", response_model=ModificationListResponse)
async def list_modifications(
    scenario_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List modifications for a scenario."""
    # Verify scenario exists
    scenario_result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    if not scenario_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    query = (
        select(ScenarioModification).where(ScenarioModification.scenario_id == scenario_id).offset(offset).limit(limit)
    )
    result = await session.execute(query)
    items = [_modification_to_detail(m) for m in result.scalars().all()]

    count_result = await session.execute(
        select(func.count(ScenarioModification.id)).where(ScenarioModification.scenario_id == scenario_id)
    )
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


@router.delete(
    "/{scenario_id}/modifications/{modification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_modification(
    scenario_id: UUID,
    modification_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> None:
    """Delete a modification from a scenario."""
    result = await session.execute(
        select(ScenarioModification).where(
            ScenarioModification.id == modification_id,
            ScenarioModification.scenario_id == scenario_id,
        )
    )
    mod = result.scalar_one_or_none()
    if not mod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Modification {modification_id} not found for scenario {scenario_id}",
        )

    # Get scenario for audit
    scenario_result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = scenario_result.scalar_one_or_none()

    await session.delete(mod)
    if scenario:
        await log_audit(
            session,
            scenario.engagement_id,
            AuditAction.SCENARIO_MODIFIED,
            f"Removed modification {modification_id}",
            actor=str(user.id),
        )
    await session.commit()
