"""Simulation service layer — serializers and shared helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AlternativeSuggestion,
    FinancialAssumption,
    FinancialAssumptionType,
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
    SuggestionDisposition,
)


async def get_scenario_or_404(
    session: AsyncSession,
    scenario_id: UUID,
) -> SimulationScenario:
    """Fetch a simulation scenario by ID or raise 404."""
    result = await session.execute(select(SimulationScenario).where(SimulationScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found")
    return scenario


def scenario_to_response(s: SimulationScenario) -> dict[str, Any]:
    """Serialize a SimulationScenario ORM object to a response dict."""
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


def result_to_response(r: SimulationResult) -> dict[str, Any]:
    """Serialize a SimulationResult ORM object to a response dict."""
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


def modification_to_response(m: ScenarioModification) -> dict[str, Any]:
    """Serialize a ScenarioModification ORM object to a response dict."""
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


def assumption_to_response(a: FinancialAssumption) -> dict[str, Any]:
    """Serialize a FinancialAssumption ORM object to a response dict."""
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


def suggestion_to_response(s: AlternativeSuggestion) -> dict[str, Any]:
    """Serialize an AlternativeSuggestion ORM object to a response dict."""
    return {
        "id": str(s.id),
        "scenario_id": str(s.scenario_id),
        "suggestion_text": s.suggestion_text,
        "rationale": s.rationale,
        "governance_flags": s.governance_flags,
        "evidence_gaps": s.evidence_gaps,
        "disposition": s.disposition.value if isinstance(s.disposition, SuggestionDisposition) else s.disposition,
        "disposition_notes": s.disposition_notes,
        "modified_content": s.modified_content,
        "disposed_at": s.disposed_at.isoformat() if s.disposed_at else None,
        "disposed_by_user_id": str(s.disposed_by_user_id) if s.disposed_by_user_id else None,
        "created_at": s.created_at.isoformat() if s.created_at else "",
    }
