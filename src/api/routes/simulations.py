"""Simulation routes for process what-if analysis.

Provides API for creating, running, and analyzing process simulations.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import SimulationResult, SimulationScenario, SimulationStatus, SimulationType, User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])


# -- Schemas ------------------------------------------------------------------


class ScenarioCreate(BaseModel):
    engagement_id: UUID
    process_model_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=512)
    simulation_type: SimulationType
    parameters: dict[str, Any] | None = None
    description: str | None = None


class ScenarioResponse(BaseModel):
    id: str
    engagement_id: str
    process_model_id: str | None = None
    name: str
    simulation_type: str
    parameters: dict[str, Any] | None = None
    description: str | None = None
    created_at: str


class ScenarioList(BaseModel):
    items: list[ScenarioResponse]
    total: int


class SimulationResultResponse(BaseModel):
    id: str
    scenario_id: str
    status: str
    metrics: dict[str, Any] | None = None
    impact_analysis: dict[str, Any] | None = None
    recommendations: list[str] | None = None
    execution_time_ms: int
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class SimulationResultList(BaseModel):
    items: list[SimulationResultResponse]
    total: int


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


def _scenario_to_response(s: SimulationScenario) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "engagement_id": str(s.engagement_id),
        "process_model_id": str(s.process_model_id) if s.process_model_id else None,
        "name": s.name,
        "simulation_type": s.simulation_type.value
        if isinstance(s.simulation_type, SimulationType)
        else s.simulation_type,
        "parameters": s.parameters,
        "description": s.description,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


def _result_to_response(r: SimulationResult) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "scenario_id": str(r.scenario_id),
        "status": r.status.value if isinstance(r.status, SimulationStatus) else r.status,
        "metrics": r.metrics,
        "impact_analysis": r.impact_analysis,
        "recommendations": r.recommendations,
        "execution_time_ms": r.execution_time_ms,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


# -- Scenario Routes ----------------------------------------------------------


@router.post("/scenarios", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Create a new simulation scenario."""
    scenario = SimulationScenario(
        engagement_id=payload.engagement_id,
        process_model_id=payload.process_model_id,
        name=payload.name,
        simulation_type=payload.simulation_type,
        parameters=payload.parameters,
        description=payload.description,
    )
    session.add(scenario)
    await session.commit()
    await session.refresh(scenario)
    return _scenario_to_response(scenario)


@router.get("/scenarios", response_model=ScenarioList)
async def list_scenarios(
    engagement_id: UUID | None = None,
    simulation_type: SimulationType | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List simulation scenarios."""
    query = select(SimulationScenario)
    if engagement_id:
        query = query.where(SimulationScenario.engagement_id == engagement_id)
    if simulation_type:
        query = query.where(SimulationScenario.simulation_type == simulation_type)
    result = await session.execute(query)
    items = [_scenario_to_response(s) for s in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get a scenario by ID."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return _scenario_to_response(scenario)


# -- Run Simulation -----------------------------------------------------------


@router.post("/scenarios/{scenario_id}/run", response_model=SimulationResultResponse)
async def run_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Run a simulation scenario."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    from src.simulation.engine import run_simulation

    now = datetime.now(UTC)
    sim_result = SimulationResult(
        scenario_id=scenario_id,
        status=SimulationStatus.RUNNING,
        execution_time_ms=0,
        started_at=now,
    )
    session.add(sim_result)
    await session.commit()
    await session.refresh(sim_result)

    try:
        process_graph = scenario.parameters or {}
        engine_result = run_simulation(
            process_graph=process_graph.get("process_graph", {"elements": [], "connections": []}),
            parameters=scenario.parameters or {},
            simulation_type=scenario.simulation_type.value
            if isinstance(scenario.simulation_type, SimulationType)
            else scenario.simulation_type,
        )

        sim_result.status = SimulationStatus.COMPLETED
        sim_result.metrics = engine_result.get("metrics")
        sim_result.execution_time_ms = engine_result.get("execution_time_ms", 0)
        sim_result.completed_at = datetime.now(UTC)

        # Generate impact analysis
        from src.simulation.impact import calculate_cascading_impact

        changed = list((scenario.parameters or {}).get("element_changes", {}).keys())
        if changed:
            impact = calculate_cascading_impact(changed, process_graph.get("process_graph", {"connections": []}))
            sim_result.impact_analysis = impact

    except Exception as e:
        sim_result.status = SimulationStatus.FAILED
        sim_result.error_message = str(e)
        sim_result.completed_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(sim_result)
    return _result_to_response(sim_result)


# -- Result Routes ------------------------------------------------------------


@router.get("/results", response_model=SimulationResultList)
async def list_results(
    scenario_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List simulation results."""
    query = select(SimulationResult)
    if scenario_id:
        query = query.where(SimulationResult.scenario_id == scenario_id)
    result = await session.execute(query)
    items = [_result_to_response(r) for r in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.get("/results/{result_id}", response_model=SimulationResultResponse)
async def get_result(
    result_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get a simulation result by ID."""
    result = await session.execute(select(SimulationResult).where(SimulationResult.id == result_id))
    sim_result = result.scalar_one_or_none()
    if not sim_result:
        raise HTTPException(status_code=404, detail=f"Result {result_id} not found")
    return _result_to_response(sim_result)
