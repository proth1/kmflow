"""Simulation routes for process what-if analysis.

Provides API for creating, running, and analyzing process simulations,
including scenario modifications, evidence coverage, and comparison.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_session
from src.api.schemas.simulations import (
    EpistemicPlanResponse,
    FinancialAssumptionCreate,
    FinancialAssumptionListResponse,
    FinancialAssumptionResponse,
    FinancialImpactResponse,
    ModificationCreate,
    ModificationList,
    ModificationResponse,
    ScenarioComparisonResponse,
    ScenarioCoverageResponse,
    ScenarioCreate,
    ScenarioList,
    ScenarioRankResponse,
    ScenarioResponse,
    SimulationResultList,
    SimulationResultResponse,
    SuggestionCreate,
    SuggestionDispositionUpdate,
    SuggestionListResponse,
    SuggestionResponse,
)
from src.core.audit import log_audit
from src.core.models import (
    AlternativeSuggestion,
    AuditAction,
    EpistemicAction,
    FinancialAssumption,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
    SuggestionDisposition,
    User,
)
from src.core.permissions import require_engagement_access, require_permission
from src.simulation.service import (
    assumption_to_response,
    get_scenario_or_404,
    modification_to_response,
    result_to_response,
    scenario_to_response,
    suggestion_to_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])

VALID_TEMPLATE_KEYS = frozenset(
    {"consolidate_adjacent", "automate_gateway", "shift_decision_boundary", "remove_control"}
)

# In-memory rate limiter for LLM endpoints (per-user, 5 requests/minute).
# NOTE: This is per-process only. In multi-worker deployments (uvicorn --workers N),
# the effective limit becomes N * _LLM_RATE_LIMIT. For production multi-worker
# deployments, replace with Redis-based rate limiting.
_LLM_RATE_LIMIT = 5
_LLM_RATE_WINDOW = 60  # seconds
_LLM_MAX_TRACKED_USERS = 10_000
_llm_request_log: dict[str, list[float]] = {}


def _check_llm_rate_limit(user_id: str) -> None:
    """Raise 429 if the user exceeds LLM request rate limit.

    This is an in-memory, single-process rate limiter. It does not share
    state across multiple uvicorn workers. For multi-worker deployments,
    use Redis-based rate limiting instead.
    """
    now = time.monotonic()
    window_start = now - _LLM_RATE_WINDOW
    # Evict stale users to prevent unbounded memory growth
    if len(_llm_request_log) > _LLM_MAX_TRACKED_USERS:
        stale = [uid for uid, ts in _llm_request_log.items() if not ts or ts[-1] < window_start]
        for uid in stale:
            del _llm_request_log[uid]
    # Prune old entries for this user
    user_log = _llm_request_log.get(user_id, [])
    user_log = [t for t in user_log if t > window_start]
    if len(user_log) >= _LLM_RATE_LIMIT:
        _llm_request_log[user_id] = user_log
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_LLM_RATE_LIMIT} LLM requests per {_LLM_RATE_WINDOW}s",
        )
    user_log.append(now)
    _llm_request_log[user_id] = user_log


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
    await log_audit(
        session, payload.engagement_id, AuditAction.SIMULATION_CREATED, f"Scenario: {payload.name}", actor=str(user.id)
    )
    await session.commit()
    await session.refresh(scenario)
    return scenario_to_response(scenario)


@router.get("/scenarios", response_model=ScenarioList)
async def list_scenarios(
    engagement_id: UUID | None = None,
    simulation_type: SimulationType | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List simulation scenarios."""
    query = select(SimulationScenario)
    count_query = select(func.count(SimulationScenario.id))
    if engagement_id:
        query = query.where(SimulationScenario.engagement_id == engagement_id)
        count_query = count_query.where(SimulationScenario.engagement_id == engagement_id)
    if simulation_type:
        query = query.where(SimulationScenario.simulation_type == simulation_type)
        count_query = count_query.where(SimulationScenario.simulation_type == simulation_type)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [scenario_to_response(s) for s in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Get a scenario by ID."""
    scenario = await get_scenario_or_404(session, scenario_id)
    return scenario_to_response(scenario)


# -- Run Simulation -----------------------------------------------------------


@router.post("/scenarios/{scenario_id}/run", response_model=SimulationResultResponse)
async def run_scenario(
    scenario_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:run")),
) -> dict[str, Any]:
    """Run a simulation scenario."""
    scenario = await get_scenario_or_404(session, scenario_id)

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
        engine_result = await asyncio.to_thread(
            run_simulation,
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

    except (ValueError, RuntimeError, KeyError) as e:
        sim_result.status = SimulationStatus.FAILED
        sim_result.error_message = str(e)
        sim_result.completed_at = datetime.now(UTC)

    await log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SIMULATION_EXECUTED,
        f"Scenario: {scenario.name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(sim_result)
    return result_to_response(sim_result)


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
    scenario = await get_scenario_or_404(session, scenario_id)

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
    await log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SCENARIO_MODIFIED,
        f"Added {payload.modification_type} on {payload.element_name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(mod)
    return modification_to_response(mod)


@router.get("/scenarios/{scenario_id}/modifications", response_model=ModificationList)
async def list_modifications(
    scenario_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List modifications for a scenario."""
    await get_scenario_or_404(session, scenario_id)
    query = select(ScenarioModification).where(ScenarioModification.scenario_id == scenario_id)
    count_query = select(func.count(ScenarioModification.id)).where(ScenarioModification.scenario_id == scenario_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [modification_to_response(m) for m in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


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
    scenario = await get_scenario_or_404(session, scenario_id)
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
    await log_audit(
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
    baseline = await get_scenario_or_404(session, scenario_id)

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

    await log_audit(
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
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List simulation results."""
    query = select(SimulationResult)
    count_query = select(func.count(SimulationResult.id))
    if scenario_id:
        query = query.where(SimulationResult.scenario_id == scenario_id)
        count_query = count_query.where(SimulationResult.scenario_id == scenario_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [result_to_response(r) for r in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


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
    return result_to_response(sim_result)


# -- Epistemic Plan -----------------------------------------------------------


@router.post("/scenarios/{scenario_id}/epistemic-plan", response_model=EpistemicPlanResponse)
async def generate_epistemic_plan(
    scenario_id: UUID,
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    create_shelf_request: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
) -> dict[str, Any]:
    """Generate epistemic action plan ranking evidence gaps by information gain."""
    scenario = await get_scenario_or_404(session, scenario_id)

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

    # Delete previous actions for this scenario before persisting new ones
    from sqlalchemy import delete as sql_delete

    await session.execute(sql_delete(EpistemicAction).where(EpistemicAction.scenario_id == scenario_id))

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

    await log_audit(
        session,
        scenario.engagement_id,
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


# -- Financial Assumptions ----------------------------------------------------


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
    scenario = await get_scenario_or_404(session, scenario_id)

    # Prevent cross-engagement assignment
    if payload.engagement_id != scenario.engagement_id:
        raise HTTPException(
            status_code=422,
            detail="engagement_id must match the scenario's engagement",
        )

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
    await log_audit(
        session,
        scenario.engagement_id,
        AuditAction.FINANCIAL_ASSUMPTION_CREATED,
        f"Assumption: {payload.name}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(assumption)
    return assumption_to_response(assumption)


@router.get(
    "/scenarios/{scenario_id}/financial-assumptions",
    response_model=FinancialAssumptionListResponse,
)
async def list_financial_assumptions(
    scenario_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List financial assumptions for a scenario's engagement."""
    scenario = await get_scenario_or_404(session, scenario_id)
    query = select(FinancialAssumption).where(FinancialAssumption.engagement_id == scenario.engagement_id)
    count_query = select(func.count(FinancialAssumption.id)).where(
        FinancialAssumption.engagement_id == scenario.engagement_id
    )
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [assumption_to_response(a) for a in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


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
    await get_scenario_or_404(session, scenario_id)
    result = await session.execute(select(FinancialAssumption).where(FinancialAssumption.id == assumption_id))
    assumption = result.scalar_one_or_none()
    if not assumption:
        raise HTTPException(status_code=404, detail=f"Assumption {assumption_id} not found")
    await session.delete(assumption)
    await session.commit()


# -- Alternative Suggestions --------------------------------------------------


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
    _check_llm_rate_limit(str(user.id))

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
            engagement_id=scenario.engagement_id,
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

    await log_audit(
        session,
        scenario.engagement_id,
        AuditAction.SUGGESTION_CREATED,
        f"Generated {len(items)} suggestions for {scenario.name}",
        actor=str(user.id),
    )
    await session.commit()
    for s in items:
        await session.refresh(s)

    return {
        "items": [suggestion_to_response(s) for s in items],
        "total": len(items),
    }


@router.get("/scenarios/{scenario_id}/suggestions", response_model=SuggestionListResponse)
async def list_suggestions(
    scenario_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """List alternative suggestions for a scenario."""
    await get_scenario_or_404(session, scenario_id)
    query = select(AlternativeSuggestion).where(AlternativeSuggestion.scenario_id == scenario_id)
    count_query = select(func.count(AlternativeSuggestion.id)).where(AlternativeSuggestion.scenario_id == scenario_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [suggestion_to_response(s) for s in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


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
    scenario = await get_scenario_or_404(session, scenario_id)
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

    if payload.disposition == SuggestionDisposition.ACCEPTED:
        action = AuditAction.SUGGESTION_ACCEPTED
    elif payload.disposition == SuggestionDisposition.REJECTED:
        action = AuditAction.SUGGESTION_REJECTED
    else:
        # MODIFIED is a form of acceptance with changes
        action = AuditAction.SUGGESTION_ACCEPTED
    await log_audit(
        session,
        scenario.engagement_id,
        action,
        f"Suggestion {suggestion_id} -> {payload.disposition.value}",
        actor=str(user.id),
    )
    await session.commit()
    await session.refresh(suggestion)
    return suggestion_to_response(suggestion)


# -- Financial Impact ---------------------------------------------------------


@router.get("/scenarios/{scenario_id}/financial-impact", response_model=FinancialImpactResponse)
async def get_financial_impact(
    scenario_id: UUID,
    baseline_scenario_id: UUID | None = Query(default=None, description="Baseline scenario for delta comparison"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> dict[str, Any]:
    """Compute financial impact estimation for a scenario."""
    scenario = await get_scenario_or_404(session, scenario_id)

    from src.simulation.financial import compute_financial_impact

    result = await session.execute(
        select(FinancialAssumption).where(FinancialAssumption.engagement_id == scenario.engagement_id)
    )
    assumptions = list(result.scalars().all())

    # Compute baseline expected cost if a baseline scenario is provided
    baseline_expected: float | None = None
    if baseline_scenario_id:
        baseline = await get_scenario_or_404(session, baseline_scenario_id)
        bl_result = await session.execute(
            select(FinancialAssumption).where(FinancialAssumption.engagement_id == baseline.engagement_id)
        )
        bl_assumptions = list(bl_result.scalars().all())
        baseline_expected = sum(a.value for a in bl_assumptions) if bl_assumptions else 0.0

    impact = compute_financial_impact(assumptions, baseline_expected=baseline_expected)

    return {
        "scenario_id": str(scenario_id),
        "cost_range": impact["cost_range"],
        "sensitivity_analysis": impact["sensitivity_analysis"],
        "assumption_count": len(assumptions),
        "delta_vs_baseline": impact.get("delta_vs_baseline"),
    }


# -- Scenario Ranking ---------------------------------------------------------


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
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Rank all scenarios for an engagement by composite score."""
    from src.simulation.ranking import rank_scenarios as compute_ranking

    # Validate weights sum to ~1.0
    weight_sum = w_evidence + w_simulation + w_financial + w_governance
    if abs(weight_sum - 1.0) > 0.01:
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to 1.0 (got {weight_sum:.4f})",
        )

    # Fetch all scenarios for this engagement
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.engagement_id == engagement_id))
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
        select(FinancialAssumption).where(FinancialAssumption.engagement_id == engagement_id)
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
