"""Per-scenario simulation routes (Story #380).

Async simulation trigger and status polling for scenario modifications.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.deps import get_session
from src.core.models import (
    EngagementMember,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    User,
    UserRole,
)
from src.core.permissions import require_permission
from src.core.services.scenario_simulation import (
    ScenarioSimulationAdapter,
    apply_confidence_overlay,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["scenario-simulation"])

# Strong references to background tasks to prevent GC
_background_tasks: set[asyncio.Task[None]] = set()


@router.post(
    "/scenarios/{scenario_id}/simulate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_simulation(
    scenario_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Trigger async simulation for a scenario.

    Creates a SimulationResult in PENDING state and launches background task.
    Returns 202 with task_id for polling.
    """
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    # Create pending simulation result
    sim_result = SimulationResult(
        id=uuid.uuid4(),
        scenario_id=scenario_id,
        status=SimulationStatus.PENDING,
    )
    session.add(sim_result)
    await session.commit()
    await session.refresh(sim_result)

    # Launch simulation in background with session factory from app state
    session_factory = request.app.state.db_session_factory
    task = asyncio.create_task(
        _run_simulation_task(scenario_id, sim_result.id, session_factory)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "task_id": str(sim_result.id),
        "scenario_id": str(scenario_id),
        "status": SimulationStatus.PENDING.value,
    }


@router.get("/scenarios/{scenario_id}/simulation-status")
async def get_simulation_status(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get the latest simulation status for a scenario."""
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    result = await session.execute(
        select(SimulationResult)
        .where(SimulationResult.scenario_id == scenario_id)
        .order_by(SimulationResult.created_at.desc())
        .limit(1)
    )
    sim_result = result.scalar_one_or_none()
    if not sim_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No simulation found for this scenario",
        )
    return _result_to_dict(sim_result)


@router.get("/scenarios/{scenario_id}/simulation-results")
async def get_simulation_results(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get completed simulation results with per-element impacts."""
    scenario = await _get_scenario(session, scenario_id)
    await _check_engagement_member(session, user, scenario.engagement_id)

    result = await session.execute(
        select(SimulationResult)
        .where(SimulationResult.scenario_id == scenario_id)
        .where(SimulationResult.status == SimulationStatus.COMPLETED)
        .order_by(SimulationResult.created_at.desc())
        .limit(1)
    )
    sim_result = result.scalar_one_or_none()
    if not sim_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed simulation found for this scenario",
        )
    return _result_to_dict(sim_result)


# -- Background Task -----------------------------------------------------------


async def _run_simulation_task(
    scenario_id: UUID,
    result_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Background task to run the scenario simulation.

    Loads modifications, runs the adapter, stores results.
    Errors are captured in the SimulationResult.
    """
    async with session_factory() as session:
        try:
            # Mark as running
            result = await session.execute(
                select(SimulationResult).where(SimulationResult.id == result_id)
            )
            sim_result = result.scalar_one()
            sim_result.status = SimulationStatus.RUNNING
            sim_result.started_at = datetime.now(UTC)
            await session.commit()

            # Load modifications
            mod_result = await session.execute(
                select(ScenarioModification)
                .where(ScenarioModification.scenario_id == scenario_id)
                .order_by(ScenarioModification.applied_at)
            )
            modifications = list(mod_result.scalars().all())

            mod_dicts = [
                {
                    "modification_type": m.modification_type,
                    "element_id": m.element_id,
                    "element_name": m.element_name,
                    "change_data": m.change_data or {},
                }
                for m in modifications
            ]

            # Run simulation
            adapter = ScenarioSimulationAdapter()
            output = adapter.simulate(mod_dicts)

            # Apply confidence overlay (existing_confidence loaded per-element
            # when a confidence store is available; empty dict until then)
            overlay = apply_confidence_overlay(output.per_element_results, {})

            # Store results
            sim_result.status = SimulationStatus.COMPLETED
            sim_result.completed_at = datetime.now(UTC)
            sim_result.execution_time_ms = output.execution_time_ms
            sim_result.metrics = {
                "cycle_time_delta_pct": round(output.cycle_time_delta_pct, 2),
                "total_fte_delta": round(output.total_fte_delta, 2),
                "baseline_cycle_time_hrs": round(output.baseline_cycle_time_hrs, 2),
                "modified_cycle_time_hrs": round(output.modified_cycle_time_hrs, 2),
            }
            sim_result.impact_analysis = {
                "per_element_results": [e.to_dict() for e in output.per_element_results],
                "confidence_overlay": overlay,
            }
            await session.commit()

        except Exception:
            logger.exception("Simulation failed for scenario %s", scenario_id)
            try:
                sim_result.status = SimulationStatus.FAILED
                sim_result.error_message = "Internal simulation error"
                sim_result.completed_at = datetime.now(UTC)
                await session.commit()
            except Exception:  # Intentionally broad: error during error handling
                logger.exception("Failed to update simulation status")


# -- Helpers -------------------------------------------------------------------


async def _get_scenario(session: AsyncSession, scenario_id: UUID) -> SimulationScenario:
    """Load a scenario or 404."""
    result = await session.execute(
        select(SimulationScenario).where(SimulationScenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found",
        )
    return scenario


async def _check_engagement_member(
    session: AsyncSession, user: User, engagement_id: UUID
) -> None:
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


def _result_to_dict(r: SimulationResult) -> dict[str, Any]:
    """Serialize a SimulationResult."""
    return {
        "id": str(r.id),
        "scenario_id": str(r.scenario_id),
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
        "metrics": r.metrics,
        "impact_analysis": r.impact_analysis,
        "execution_time_ms": r.execution_time_ms,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
