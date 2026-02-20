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
    AlternativeSuggestion,
    AuditAction,
    AuditLog,
    EpistemicAction,
    FinancialAssumption,
    FinancialAssumptionType,
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
    SuggestionDisposition,
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


# =============================================================================
# Phase 3.2: Epistemic Action Planner
# =============================================================================


class EpistemicActionResponse(BaseModel):
    target_element_id: str
    target_element_name: str
    evidence_gap_description: str
    current_confidence: float
    estimated_confidence_uplift: float
    projected_confidence: float
    information_gain_score: float
    recommended_evidence_category: str
    priority: str


class EpistemicPlanAggregates(BaseModel):
    total: int
    high_priority_count: int
    estimated_aggregate_uplift: float


class EpistemicPlanResponse(BaseModel):
    scenario_id: str
    actions: list[EpistemicActionResponse]
    aggregated_view: EpistemicPlanAggregates


@router.get("/scenarios/{scenario_id}/epistemic-plan", response_model=EpistemicPlanResponse)
async def get_epistemic_plan(
    scenario_id: UUID,
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    create_shelf_request: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get epistemic action plan ranking evidence gaps by information gain."""
    scenario = await _get_scenario_or_404(session, scenario_id)

    from src.semantic.graph import KnowledgeGraphService
    from src.simulation.epistemic import EpistemicPlannerService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    planner = EpistemicPlannerService(graph_service)

    plan = await planner.generate_epistemic_plan(
        scenario_id=scenario_id,
        engagement_id=scenario.engagement_id,
        session=session,
        process_graph=scenario.parameters or {},
    )

    # Persist epistemic actions
    for action in plan.actions[:limit]:
        ea = EpistemicAction(
            scenario_id=scenario_id,
            target_element_id=action.target_element_id,
            target_element_name=action.target_element_name,
            evidence_gap_description=action.evidence_gap_description,
            current_confidence=action.current_confidence,
            estimated_confidence_uplift=action.estimated_confidence_uplift,
            projected_confidence=action.projected_confidence,
            information_gain_score=action.information_gain_score,
            recommended_evidence_category=action.recommended_evidence_category,
            priority=action.priority,
        )
        session.add(ea)

    # Optionally create shelf request from high-priority actions
    if create_shelf_request and plan.high_priority_count > 0:
        from src.core.models import ShelfDataRequest, ShelfDataRequestItem

        shelf = ShelfDataRequest(
            engagement_id=scenario.engagement_id,
            title=f"Evidence gaps for scenario: {scenario.name}",
            description="Auto-generated from epistemic action plan",
        )
        session.add(shelf)
        await session.flush()

        for action in plan.actions[:limit]:
            if action.priority == "high":
                item = ShelfDataRequestItem(
                    request_id=shelf.id,
                    category=action.recommended_evidence_category,
                    item_name=f"Evidence for: {action.target_element_name}",
                    description=action.evidence_gap_description,
                    priority="high",
                )
                session.add(item)

    await _log_audit(
        session, scenario.engagement_id,
        AuditAction.EPISTEMIC_PLAN_GENERATED,
        f"Generated {plan.total_actions} actions for {scenario.name}",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "scenario_id": str(scenario_id),
        "actions": [
            {
                "target_element_id": a.target_element_id,
                "target_element_name": a.target_element_name,
                "evidence_gap_description": a.evidence_gap_description,
                "current_confidence": a.current_confidence,
                "estimated_confidence_uplift": a.estimated_confidence_uplift,
                "projected_confidence": a.projected_confidence,
                "information_gain_score": a.information_gain_score,
                "recommended_evidence_category": a.recommended_evidence_category,
                "priority": a.priority,
            }
            for a in plan.actions[:limit]
        ],
        "aggregated_view": {
            "total": plan.total_actions,
            "high_priority_count": plan.high_priority_count,
            "estimated_aggregate_uplift": plan.estimated_aggregate_uplift,
        },
    }


# =============================================================================
# Phase 4.1: Financial Assumptions
# =============================================================================


class FinancialAssumptionCreate(BaseModel):
    engagement_id: UUID
    assumption_type: FinancialAssumptionType
    name: str = Field(..., min_length=1, max_length=256)
    value: float
    unit: str = Field(..., min_length=1, max_length=50)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_evidence_id: UUID | None = None
    notes: str | None = None


class FinancialAssumptionResponse(BaseModel):
    id: str
    engagement_id: str
    assumption_type: str
    name: str
    value: float
    unit: str
    confidence: float
    source_evidence_id: str | None = None
    notes: str | None = None
    created_at: str


class FinancialAssumptionListResponse(BaseModel):
    items: list[FinancialAssumptionResponse]
    total: int


def _assumption_to_response(a: FinancialAssumption) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "engagement_id": str(a.engagement_id),
        "assumption_type": a.assumption_type.value
        if isinstance(a.assumption_type, FinancialAssumptionType)
        else a.assumption_type,
        "name": a.name,
        "value": a.value,
        "unit": a.unit,
        "confidence": a.confidence,
        "source_evidence_id": str(a.source_evidence_id) if a.source_evidence_id else None,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


@router.post(
    "/scenarios/{scenario_id}/financial-assumptions",
    response_model=FinancialAssumptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_financial_assumption(
    scenario_id: UUID,
    payload: FinancialAssumptionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Create a financial assumption for a scenario's engagement."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    assumption = FinancialAssumption(
        engagement_id=payload.engagement_id,
        assumption_type=payload.assumption_type,
        name=payload.name,
        value=payload.value,
        unit=payload.unit,
        confidence=payload.confidence,
        source_evidence_id=payload.source_evidence_id,
        notes=payload.notes,
    )
    session.add(assumption)
    await _log_audit(
        session, scenario.engagement_id,
        AuditAction.FINANCIAL_ASSUMPTION_CREATED,
        f"Assumption: {payload.name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(assumption)
    return _assumption_to_response(assumption)


@router.get(
    "/scenarios/{scenario_id}/financial-assumptions",
    response_model=FinancialAssumptionListResponse,
)
async def list_financial_assumptions(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List financial assumptions for a scenario's engagement."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(FinancialAssumption).where(
            FinancialAssumption.engagement_id == scenario.engagement_id
        )
    )
    items = [_assumption_to_response(a) for a in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.delete(
    "/scenarios/{scenario_id}/financial-assumptions/{assumption_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_financial_assumption(
    scenario_id: UUID,
    assumption_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> None:
    """Delete a financial assumption."""
    await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(FinancialAssumption).where(FinancialAssumption.id == assumption_id)
    )
    assumption = result.scalar_one_or_none()
    if not assumption:
        raise HTTPException(status_code=404, detail=f"Assumption {assumption_id} not found")
    await session.delete(assumption)
    await session.commit()


# =============================================================================
# Phase 4.1: Alternative Suggestions
# =============================================================================


class SuggestionCreate(BaseModel):
    context_notes: str | None = None


class SuggestionResponse(BaseModel):
    id: str
    scenario_id: str
    suggestion_text: str
    rationale: str
    governance_flags: dict[str, Any] | None = None
    evidence_gaps: dict[str, Any] | None = None
    disposition: str
    disposition_notes: str | None = None
    created_at: str


class SuggestionListResponse(BaseModel):
    items: list[SuggestionResponse]
    total: int


class SuggestionDispositionUpdate(BaseModel):
    disposition: SuggestionDisposition
    disposition_notes: str | None = None


def _suggestion_to_response(s: AlternativeSuggestion) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "scenario_id": str(s.scenario_id),
        "suggestion_text": s.suggestion_text,
        "rationale": s.rationale,
        "governance_flags": s.governance_flags,
        "evidence_gaps": s.evidence_gaps,
        "disposition": s.disposition.value
        if isinstance(s.disposition, SuggestionDisposition)
        else s.disposition,
        "disposition_notes": s.disposition_notes,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }


@router.post(
    "/scenarios/{scenario_id}/suggestions",
    response_model=SuggestionListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_suggestions(
    scenario_id: UUID,
    payload: SuggestionCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Request LLM-generated alternative suggestions for a scenario."""
    result = await session.execute(
        select(SimulationScenario)
        .where(SimulationScenario.id == scenario_id)
        .options(selectinload(SimulationScenario.modifications))
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")

    from src.simulation.suggester import AlternativeSuggesterService

    suggester = AlternativeSuggesterService()
    suggestions = await suggester.generate_suggestions(
        scenario=scenario,
        user_id=user.id,
        context_notes=payload.context_notes,
    )

    items = []
    for s_data in suggestions:
        suggestion = AlternativeSuggestion(
            scenario_id=scenario_id,
            suggestion_text=s_data["suggestion_text"],
            rationale=s_data["rationale"],
            governance_flags=s_data.get("governance_flags"),
            evidence_gaps=s_data.get("evidence_gaps"),
            llm_prompt=s_data["llm_prompt"],
            llm_response=s_data["llm_response"],
            created_by=user.id,
        )
        session.add(suggestion)
        items.append(suggestion)

    await _log_audit(
        session, scenario.engagement_id,
        AuditAction.SUGGESTION_CREATED,
        f"Generated {len(items)} suggestions for {scenario.name}",
        actor=str(user.id),
    )
    await session.commit()
    for s in items:
        await session.refresh(s)

    return {
        "items": [_suggestion_to_response(s) for s in items],
        "total": len(items),
    }


@router.get("/scenarios/{scenario_id}/suggestions", response_model=SuggestionListResponse)
async def list_suggestions(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List alternative suggestions for a scenario."""
    await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(AlternativeSuggestion).where(AlternativeSuggestion.scenario_id == scenario_id)
    )
    items = [_suggestion_to_response(s) for s in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.patch(
    "/scenarios/{scenario_id}/suggestions/{suggestion_id}",
    response_model=SuggestionResponse,
)
async def update_suggestion_disposition(
    scenario_id: UUID,
    suggestion_id: UUID,
    payload: SuggestionDispositionUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Accept, modify, or reject a suggestion."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    result = await session.execute(
        select(AlternativeSuggestion).where(
            AlternativeSuggestion.id == suggestion_id,
            AlternativeSuggestion.scenario_id == scenario_id,
        )
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

    suggestion.disposition = payload.disposition
    suggestion.disposition_notes = payload.disposition_notes

    action = (
        AuditAction.SUGGESTION_ACCEPTED
        if payload.disposition == SuggestionDisposition.ACCEPTED
        else AuditAction.SUGGESTION_REJECTED
    )
    await _log_audit(
        session, scenario.engagement_id, action,
        f"Suggestion {suggestion_id} -> {payload.disposition.value}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(suggestion)
    return _suggestion_to_response(suggestion)


# =============================================================================
# Phase 4.2: Financial Impact Estimation
# =============================================================================


class CostRange(BaseModel):
    optimistic: float
    expected: float
    pessimistic: float


class SensitivityEntry(BaseModel):
    assumption_name: str
    base_value: float
    impact_range: CostRange


class FinancialImpactResponse(BaseModel):
    scenario_id: str
    cost_range: CostRange
    sensitivity_analysis: list[SensitivityEntry]
    assumption_count: int
    delta_vs_baseline: float | None = None


@router.get("/scenarios/{scenario_id}/financial-impact", response_model=FinancialImpactResponse)
async def get_financial_impact(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Compute financial impact estimation for a scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)

    from src.simulation.financial import compute_financial_impact

    result = await session.execute(
        select(FinancialAssumption).where(
            FinancialAssumption.engagement_id == scenario.engagement_id
        )
    )
    assumptions = list(result.scalars().all())

    impact = compute_financial_impact(assumptions)

    return {
        "scenario_id": str(scenario_id),
        "cost_range": impact["cost_range"],
        "sensitivity_analysis": impact["sensitivity_analysis"],
        "assumption_count": len(assumptions),
        "delta_vs_baseline": impact.get("delta_vs_baseline"),
    }


# =============================================================================
# Phase 4.2: Scenario Ranking
# =============================================================================


class ScenarioRankEntry(BaseModel):
    scenario_id: str
    scenario_name: str
    composite_score: float
    evidence_score: float
    simulation_score: float
    financial_score: float
    governance_score: float


class ScenarioRankResponse(BaseModel):
    engagement_id: str
    rankings: list[ScenarioRankEntry]
    weights: dict[str, float]


@router.get("/scenarios/rank", response_model=ScenarioRankResponse)
async def rank_scenarios(
    engagement_id: UUID,
    request: Request,
    w_evidence: float = Query(default=0.30, ge=0.0, le=1.0),
    w_simulation: float = Query(default=0.25, ge=0.0, le=1.0),
    w_financial: float = Query(default=0.25, ge=0.0, le=1.0),
    w_governance: float = Query(default=0.20, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Rank all scenarios for an engagement by composite score."""
    from src.simulation.ranking import rank_scenarios as compute_ranking

    # Fetch all scenarios for this engagement
    result = await session.execute(
        select(SimulationScenario).where(
            SimulationScenario.engagement_id == engagement_id
        )
    )
    scenarios = list(result.scalars().all())

    weights = {
        "evidence": w_evidence,
        "simulation": w_simulation,
        "financial": w_financial,
        "governance": w_governance,
    }

    if not scenarios:
        return {
            "engagement_id": str(engagement_id),
            "rankings": [],
            "weights": weights,
        }

    # Fetch assumptions for financial scoring
    fa_result = await session.execute(
        select(FinancialAssumption).where(
            FinancialAssumption.engagement_id == engagement_id
        )
    )
    assumptions = list(fa_result.scalars().all())

    # Fetch latest simulation results per scenario
    from sqlalchemy import func as sa_func

    scenario_ids = [s.id for s in scenarios]
    latest_subq = (
        select(
            SimulationResult.scenario_id,
            sa_func.max(SimulationResult.completed_at).label("max_completed"),
        )
        .where(
            SimulationResult.scenario_id.in_(scenario_ids),
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

    rankings = compute_ranking(
        scenarios=scenarios,
        results_map=results_map,
        assumptions=assumptions,
        weights=weights,
    )

    return {
        "engagement_id": str(engagement_id),
        "rankings": rankings,
        "weights": weights,
    }
