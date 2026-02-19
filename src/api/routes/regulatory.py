"""Regulatory, Policy, and Control management routes.

Provides CRUD operations for policies, controls, and regulations
within an engagement context.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditAction,
    AuditLog,
    Control,
    ControlEffectiveness,
    Engagement,
    Policy,
    PolicyType,
    Regulation,
    User,
)
from src.api.deps import get_session
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory"])


# -- Request/Response Schemas ------------------------------------------------


class PolicyCreate(BaseModel):
    """Schema for creating a policy."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    policy_type: PolicyType
    source_evidence_id: UUID | None = None
    clauses: dict[str, Any] | None = None
    description: str | None = None


class PolicyUpdate(BaseModel):
    """Schema for updating a policy (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    policy_type: PolicyType | None = None
    source_evidence_id: UUID | None = None
    clauses: dict[str, Any] | None = None
    description: str | None = None


class PolicyResponse(BaseModel):
    """Schema for policy responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    policy_type: PolicyType
    source_evidence_id: UUID | None
    clauses: dict[str, Any] | None
    description: str | None
    created_at: Any
    updated_at: Any


class PolicyList(BaseModel):
    """Schema for listing policies."""

    items: list[PolicyResponse]
    total: int


class ControlCreate(BaseModel):
    """Schema for creating a control."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    effectiveness: ControlEffectiveness = ControlEffectiveness.EFFECTIVE
    effectiveness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    linked_policy_ids: list[str] | None = None


class ControlUpdate(BaseModel):
    """Schema for updating a control (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    effectiveness: ControlEffectiveness | None = None
    effectiveness_score: float | None = Field(None, ge=0.0, le=1.0)
    linked_policy_ids: list[str] | None = None


class ControlResponse(BaseModel):
    """Schema for control responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    description: str | None
    effectiveness: ControlEffectiveness
    effectiveness_score: float
    linked_policy_ids: list[str] | None
    created_at: Any
    updated_at: Any


class ControlList(BaseModel):
    """Schema for listing controls."""

    items: list[ControlResponse]
    total: int


class RegulationCreate(BaseModel):
    """Schema for creating a regulation."""

    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=512)
    framework: str | None = None
    jurisdiction: str | None = None
    obligations: dict[str, Any] | None = None


class RegulationUpdate(BaseModel):
    """Schema for updating a regulation (PATCH)."""

    name: str | None = Field(None, min_length=1, max_length=512)
    framework: str | None = None
    jurisdiction: str | None = None
    obligations: dict[str, Any] | None = None


class RegulationResponse(BaseModel):
    """Schema for regulation responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    framework: str | None
    jurisdiction: str | None
    obligations: dict[str, Any] | None
    created_at: Any
    updated_at: Any


class RegulationList(BaseModel):
    """Schema for listing regulations."""

    items: list[RegulationResponse]
    total: int


# -- Helpers ------------------------------------------------------------------


async def _log_audit(
    session: AsyncSession,
    engagement_id: UUID,
    action: AuditAction,
    details: str | None = None,
) -> None:
    audit = AuditLog(engagement_id=engagement_id, action=action, actor="system", details=details)
    session.add(audit)


async def _verify_engagement(session: AsyncSession, engagement_id: UUID) -> None:
    result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {engagement_id} not found")


# -- Policy Routes ------------------------------------------------------------


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Policy:
    """Create a new policy."""
    await _verify_engagement(session, payload.engagement_id)
    policy = Policy(
        engagement_id=payload.engagement_id,
        name=payload.name,
        policy_type=payload.policy_type,
        source_evidence_id=payload.source_evidence_id,
        clauses=payload.clauses,
        description=payload.description,
    )
    session.add(policy)
    await session.flush()
    await _log_audit(session, payload.engagement_id, AuditAction.POLICY_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(policy)
    return policy


@router.get("/policies", response_model=PolicyList)
async def list_policies(
    engagement_id: UUID,
    limit: int = 20,
    offset: int = 0,
    policy_type: PolicyType | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List policies for an engagement."""
    query = select(Policy).where(Policy.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(Policy).where(Policy.engagement_id == engagement_id)

    if policy_type is not None:
        query = query.where(Policy.policy_type == policy_type)
        count_query = count_query.where(Policy.policy_type == policy_type)

    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    policies = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": policies, "total": total}


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Policy:
    """Get a specific policy by ID."""
    result = await session.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")
    return policy


# -- Control Routes -----------------------------------------------------------


@router.post("/controls", response_model=ControlResponse, status_code=status.HTTP_201_CREATED)
async def create_control(
    payload: ControlCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Control:
    """Create a new control."""
    await _verify_engagement(session, payload.engagement_id)
    control = Control(
        engagement_id=payload.engagement_id,
        name=payload.name,
        description=payload.description,
        effectiveness=payload.effectiveness,
        effectiveness_score=payload.effectiveness_score,
        linked_policy_ids=payload.linked_policy_ids,
    )
    session.add(control)
    await session.flush()
    await _log_audit(session, payload.engagement_id, AuditAction.CONTROL_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(control)
    return control


@router.get("/controls", response_model=ControlList)
async def list_controls(
    engagement_id: UUID,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List controls for an engagement."""
    query = select(Control).where(Control.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(Control).where(Control.engagement_id == engagement_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    controls = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": controls, "total": total}


@router.get("/controls/{control_id}", response_model=ControlResponse)
async def get_control(
    control_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Control:
    """Get a specific control by ID."""
    result = await session.execute(select(Control).where(Control.id == control_id))
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Control {control_id} not found")
    return control


# -- Regulation Routes --------------------------------------------------------


@router.post("/regulations", response_model=RegulationResponse, status_code=status.HTTP_201_CREATED)
async def create_regulation(
    payload: RegulationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Regulation:
    """Create a new regulation."""
    await _verify_engagement(session, payload.engagement_id)
    regulation = Regulation(
        engagement_id=payload.engagement_id,
        name=payload.name,
        framework=payload.framework,
        jurisdiction=payload.jurisdiction,
        obligations=payload.obligations,
    )
    session.add(regulation)
    await session.flush()
    await _log_audit(session, payload.engagement_id, AuditAction.REGULATION_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(regulation)
    return regulation


@router.get("/regulations", response_model=RegulationList)
async def list_regulations(
    engagement_id: UUID,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List regulations for an engagement."""
    query = select(Regulation).where(Regulation.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(Regulation).where(Regulation.engagement_id == engagement_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    regulations = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": regulations, "total": total}


@router.patch("/regulations/{regulation_id}", response_model=RegulationResponse)
async def update_regulation(
    regulation_id: UUID,
    payload: RegulationUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Regulation:
    """Update a regulation's fields (partial update)."""
    result = await session.execute(select(Regulation).where(Regulation.id == regulation_id))
    regulation = result.scalar_one_or_none()
    if not regulation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation {regulation_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(regulation, field_name, value)

    await session.commit()
    await session.refresh(regulation)
    return regulation


# -- Overlay Engine Routes (Story #29) ----------------------------------------


@router.post("/overlay/{engagement_id}/build")
async def build_governance_overlay(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Build governance chains in the knowledge graph for an engagement."""
    from src.core.regulatory import RegulatoryOverlayEngine
    from src.semantic.graph import KnowledgeGraphService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = RegulatoryOverlayEngine(graph_service)

    chains = await engine.build_governance_chains(session, str(engagement_id))
    return {
        "engagement_id": str(engagement_id),
        "chains_built": len(chains),
        "chains": [
            {"process_id": c.process_id, "process_name": c.process_name, "policy_count": len(c.policies)}
            for c in chains
        ],
    }


@router.get("/overlay/{engagement_id}/compliance")
async def get_compliance_state(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Assess compliance state for an engagement."""
    from src.core.regulatory import RegulatoryOverlayEngine
    from src.semantic.graph import KnowledgeGraphService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = RegulatoryOverlayEngine(graph_service)

    state = await engine.assess_compliance(session, str(engagement_id))
    return {
        "engagement_id": state.engagement_id,
        "level": str(state.level),
        "governed_count": state.governed_count,
        "ungoverned_count": state.ungoverned_count,
        "total_processes": state.total_processes,
        "policy_coverage": state.policy_coverage,
    }


@router.get("/overlay/{engagement_id}/ungoverned")
async def get_ungoverned_processes(
    engagement_id: UUID,
    request: Request,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Find processes without governance links."""
    from src.core.regulatory import RegulatoryOverlayEngine
    from src.semantic.graph import KnowledgeGraphService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = RegulatoryOverlayEngine(graph_service)

    ungoverned = await engine.find_ungoverned_processes(str(engagement_id))
    return {"engagement_id": str(engagement_id), "ungoverned": ungoverned, "count": len(ungoverned)}
