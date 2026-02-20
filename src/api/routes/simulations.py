"""Simulation routes for process what-if analysis.

Provides API for creating, running, and analyzing process simulations,
including scenario modifications, evidence coverage, and comparison.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_session
from src.core.models import (
    AuditAction,
    AuditLog,
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
    User,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])

VALID_TEMPLATE_KEYS = frozenset(
    {"consolidate_adjacent", "automate_gateway", "shift_decision_boundary", "remove_control"}
)


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
    status: str | None = None
    evidence_confidence_score: float | None = None
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


class ModificationCreate(BaseModel):
    modification_type: ModificationType
    element_id: str = Field(..., min_length=1, max_length=512)
    element_name: str = Field(..., min_length=1, max_length=512)
    change_data: dict[str, Any] | None = None
    template_key: str | None = None


class ModificationResponse(BaseModel):
    id: str
    scenario_id: str
    modification_type: str
    element_id: str
    element_name: str
    change_data: dict[str, Any] | None = None
    template_key: str | None = None
    applied_at: str


class ModificationList(BaseModel):
    items: list[ModificationResponse]
    total: int


class ElementCoverageResponse(BaseModel):
    element_id: str
    element_name: str
    classification: str
    evidence_count: int
    confidence: float
    is_added: bool = False
    is_removed: bool = False
    is_modified: bool = False


class ScenarioCoverageResponse(BaseModel):
    scenario_id: str
    elements: list[ElementCoverageResponse]
    bright_count: int
    dim_count: int
    dark_count: int
    aggregate_confidence: float


class ScenarioComparisonEntry(BaseModel):
    scenario_id: str
    scenario_name: str
    deltas: dict[str, Any] | None = None
    assessment: str | None = None
    coverage_summary: dict[str, int] | None = None


class ScenarioComparisonResponse(BaseModel):
    baseline_id: str
    baseline_name: str
    comparisons: list[ScenarioComparisonEntry]


# -- Helpers ------------------------------------------------------------------


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
        "status": s.status,
        "evidence_confidence_score": s.evidence_confidence_score,
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


def _modification_to_response(m: ScenarioModification) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "scenario_id": str(m.scenario_id),
        "modification_type": m.modification_type.value
        if isinstance(m.modification_type, ModificationType)
        else m.modification_type,
        "element_id": m.element_id,
        "element_name": m.element_name,
        "change_data": m.change_data,
        "template_key": m.template_key,
        "applied_at": m.applied_at.isoformat() if m.applied_at else "",
    }


async def _log_audit(
    session: AsyncSession,
    engagement_id: UUID,
    action: AuditAction,
    details: str | None = None,
    *,
    actor: str = "system",
) -> None:
    audit = AuditLog(engagement_id=engagement_id, action=action, actor=actor, details=details)
    session.add(audit)


async def _get_scenario_or_404(
    session: AsyncSession,
    scenario_id: UUID,
) -> SimulationScenario:
    result = await session.execute(
        select(SimulationScenario).where(SimulationScenario.id == scenario_id)
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return scenario


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
    await _log_audit(session, payload.engagement_id, AuditAction.SIMULATION_CREATED, f"Scenario: {payload.name}", actor=str(user.id))
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
    scenario = await _get_scenario_or_404(session, scenario_id)
    return _scenario_to_response(scenario)


# -- Run Simulation -----------------------------------------------------------


@router.post("/scenarios/{scenario_id}/run", response_model=SimulationResultResponse)
async def run_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Run a simulation scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)

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

    await _log_audit(session, scenario.engagement_id, AuditAction.SIMULATION_EXECUTED, f"Scenario: {scenario.name}", actor=str(user.id))
    await session.commit()
    await session.refresh(sim_result)
    return _result_to_response(sim_result)


# -- Modification Routes ------------------------------------------------------


@router.post(
    "/scenarios/{scenario_id}/modifications",
    response_model=ModificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_modification(
    scenario_id: UUID,
    payload: ModificationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Add a modification to a scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)

    if payload.template_key and payload.template_key not in VALID_TEMPLATE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid template_key '{payload.template_key}'. Must be one of: {sorted(VALID_TEMPLATE_KEYS)}",
        )

    mod = ScenarioModification(
        scenario_id=scenario_id,
        modification_type=payload.modification_type,
        element_id=payload.element_id,
        element_name=payload.element_name,
        change_data=payload.change_data,
        template_key=payload.template_key,
    )
    session.add(mod)
    await _log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SCENARIO_MODIFIED,
        f"Added {payload.modification_type} on {payload.element_name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(mod)
    return _modification_to_response(mod)


@router.get("/scenarios/{scenario_id}/modifications", response_model=ModificationList)
async def list_modifications(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List modifications for a scenario."""
    await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(ScenarioModification).where(ScenarioModification.scenario_id == scenario_id)
    )
    items = [_modification_to_response(m) for m in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.delete(
    "/scenarios/{scenario_id}/modifications/{modification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_modification(
    scenario_id: UUID,
    modification_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> None:
    """Delete a modification from a scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(ScenarioModification).where(
            ScenarioModification.id == modification_id,
            ScenarioModification.scenario_id == scenario_id,
        )
    )
    mod = result.scalar_one_or_none()
    if not mod:
        raise HTTPException(
            status_code=404,
            detail=f"Modification {modification_id} not found for scenario {scenario_id}",
        )
    await session.delete(mod)
    await _log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SCENARIO_MODIFIED,
        f"Removed modification {modification_id}",
        actor=str(user.id),
    )
    await session.commit()


# -- Evidence Coverage Route --------------------------------------------------


@router.get("/scenarios/{scenario_id}/evidence-coverage", response_model=ScenarioCoverageResponse)
async def get_evidence_coverage(
    scenario_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get Bright/Dim/Dark evidence coverage for a scenario."""
    result = await session.execute(
        select(SimulationScenario)
        .where(SimulationScenario.id == scenario_id)
        .options(selectinload(SimulationScenario.modifications))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    from src.semantic.graph import KnowledgeGraphService
    from src.simulation.coverage import EvidenceCoverageService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    coverage_service = EvidenceCoverageService(graph_service)

    coverage = await coverage_service.compute_coverage(
        scenario_id=scenario_id,
        engagement_id=scenario.engagement_id,
        modifications=scenario.modifications,
    )

    # Opportunistically update the scenario's confidence score
    scenario.evidence_confidence_score = coverage.aggregate_confidence
    await session.commit()

    return {
        "scenario_id": coverage.scenario_id,
        "elements": [
            {
                "element_id": e.element_id,
                "element_name": e.element_name,
                "classification": e.classification,
                "evidence_count": e.evidence_count,
                "confidence": e.confidence,
                "is_added": e.is_added,
                "is_removed": e.is_removed,
                "is_modified": e.is_modified,
            }
            for e in coverage.elements
        ],
        "bright_count": coverage.bright_count,
        "dim_count": coverage.dim_count,
        "dark_count": coverage.dark_count,
        "aggregate_confidence": coverage.aggregate_confidence,
    }


# -- Compare Route ------------------------------------------------------------


@router.get("/scenarios/{scenario_id}/compare", response_model=ScenarioComparisonResponse)
async def compare_scenarios(
    scenario_id: UUID,
    request: Request,
    ids: str = Query(..., description="Comma-separated scenario UUIDs to compare against"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Compare baseline scenario with alternatives side-by-side."""
    import asyncio

    # Fetch baseline
    baseline = await _get_scenario_or_404(session, scenario_id)

    # Parse comparison IDs
    try:
        compare_ids = [UUID(uid.strip()) for uid in ids.split(",") if uid.strip()]
    except ValueError as err:
        raise HTTPException(status_code=422, detail="ids must be comma-separated valid UUIDs") from err

    if not compare_ids:
        raise HTTPException(status_code=422, detail="At least one comparison scenario ID is required")

    if len(compare_ids) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 comparison scenarios allowed")

    # Batch-fetch baseline result + all comparison scenarios and results
    all_ids = compare_ids
    baseline_result_row = await session.execute(
        select(SimulationResult)
        .where(
            SimulationResult.scenario_id == scenario_id,
            SimulationResult.status == SimulationStatus.COMPLETED,
        )
        .order_by(SimulationResult.completed_at.desc())
        .limit(1)
    )
    baseline_result = baseline_result_row.scalar_one_or_none()
    baseline_metrics = baseline_result.metrics if baseline_result else {}

    # Batch-fetch all comparison scenarios with their modifications
    cmp_scenarios_row = await session.execute(
        select(SimulationScenario)
        .where(SimulationScenario.id.in_(all_ids))
        .options(selectinload(SimulationScenario.modifications))
    )
    cmp_scenarios_map = {s.id: s for s in cmp_scenarios_row.scalars().all()}

    # Batch-fetch latest completed result per comparison scenario
    from sqlalchemy import func as sa_func

    latest_subq = (
        select(
            SimulationResult.scenario_id,
            sa_func.max(SimulationResult.completed_at).label("max_completed"),
        )
        .where(
            SimulationResult.scenario_id.in_(all_ids),
            SimulationResult.status == SimulationStatus.COMPLETED,
        )
        .group_by(SimulationResult.scenario_id)
        .subquery()
    )
    results_row = await session.execute(
        select(SimulationResult).join(
            latest_subq,
            (SimulationResult.scenario_id == latest_subq.c.scenario_id)
            & (SimulationResult.completed_at == latest_subq.c.max_completed),
        )
    )
    results_map = {r.scenario_id: r for r in results_row.scalars().all()}

    from src.semantic.graph import KnowledgeGraphService
    from src.simulation.coverage import EvidenceCoverageService
    from src.simulation.impact import compare_simulation_results

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    coverage_service = EvidenceCoverageService(graph_service)

    # Compute coverage concurrently for all found scenarios
    async def _build_entry(cid: UUID) -> dict[str, Any]:
        cmp_scenario = cmp_scenarios_map.get(cid)
        if not cmp_scenario:
            return {
                "scenario_id": str(cid),
                "scenario_name": "Not Found",
                "deltas": None,
                "assessment": None,
                "coverage_summary": None,
            }

        sim_result = results_map.get(cid)
        sim_metrics = sim_result.metrics if sim_result else {}

        deltas = None
        assessment = None
        if baseline_metrics and sim_metrics:
            comparison = compare_simulation_results(baseline_metrics, sim_metrics)
            deltas = comparison.get("deltas")
            assessment = comparison.get("assessment")

        coverage = await coverage_service.compute_coverage(
            scenario_id=cid,
            engagement_id=cmp_scenario.engagement_id,
            modifications=list(cmp_scenario.modifications),
        )

        return {
            "scenario_id": str(cid),
            "scenario_name": cmp_scenario.name,
            "deltas": deltas,
            "assessment": assessment,
            "coverage_summary": {
                "bright": coverage.bright_count,
                "dim": coverage.dim_count,
                "dark": coverage.dark_count,
            },
        }

    comparisons = await asyncio.gather(*[_build_entry(cid) for cid in compare_ids])

    await _log_audit(
        session,
        baseline.engagement_id,
        AuditAction.SCENARIO_COMPARED,
        f"Compared {baseline.name} with {len(compare_ids)} scenario(s)",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "baseline_id": str(scenario_id),
        "baseline_name": baseline.name,
        "comparisons": comparisons,
    }


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
