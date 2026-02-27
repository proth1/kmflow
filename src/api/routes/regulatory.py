"""Regulatory, Policy, and Control management routes.

Provides CRUD operations for policies, controls, and regulations
within an engagement context.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.audit import log_audit
from src.core.models import (
    AuditAction,
    Control,
    ControlEffectiveness,
    Engagement,
    Policy,
    PolicyType,
    Regulation,
    User,
)
from src.core.permissions import require_engagement_access, require_permission

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


# -- Policy Routes ------------------------------------------------------------


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Policy:
    """Create a new policy."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found")
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
    await log_audit(session, payload.engagement_id, AuditAction.POLICY_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(policy)
    return policy


@router.get("/policies", response_model=PolicyList)
async def list_policies(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    policy_type: PolicyType | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List policies for an engagement."""
    query = select(Policy).where(Policy.engagement_id == engagement_id, Policy.deleted_at.is_(None))
    count_query = select(func.count()).select_from(Policy).where(Policy.engagement_id == engagement_id, Policy.deleted_at.is_(None))

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
    result = await session.execute(select(Policy).where(Policy.id == policy_id, Policy.deleted_at.is_(None)))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")
    return policy


@router.patch("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    payload: PolicyUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Policy:
    """Update a policy's fields (partial update)."""
    result = await session.execute(select(Policy).where(Policy.id == policy_id, Policy.deleted_at.is_(None)))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(policy, field_name, value)

    await session.commit()
    await session.refresh(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> None:
    """Soft-delete a policy (sets deleted_at, does not hard delete)."""
    from datetime import UTC, datetime

    result = await session.execute(select(Policy).where(Policy.id == policy_id, Policy.deleted_at.is_(None)))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Policy {policy_id} not found")

    policy.deleted_at = datetime.now(UTC)
    await log_audit(session, policy.engagement_id, AuditAction.POLICY_DELETED, json.dumps({"id": str(policy_id), "name": policy.name}))
    await session.commit()


# -- Control Routes -----------------------------------------------------------


@router.post("/controls", response_model=ControlResponse, status_code=status.HTTP_201_CREATED)
async def create_control(
    payload: ControlCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Control:
    """Create a new control."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found")
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
    await log_audit(session, payload.engagement_id, AuditAction.CONTROL_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(control)
    return control


@router.get("/controls", response_model=ControlList)
async def list_controls(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List controls for an engagement."""
    query = select(Control).where(Control.engagement_id == engagement_id, Control.deleted_at.is_(None))
    count_query = select(func.count()).select_from(Control).where(Control.engagement_id == engagement_id, Control.deleted_at.is_(None))
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
    result = await session.execute(select(Control).where(Control.id == control_id, Control.deleted_at.is_(None)))
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Control {control_id} not found")
    return control


@router.patch("/controls/{control_id}", response_model=ControlResponse)
async def update_control(
    control_id: UUID,
    payload: ControlUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Control:
    """Update a control's fields (partial update)."""
    result = await session.execute(select(Control).where(Control.id == control_id, Control.deleted_at.is_(None)))
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Control {control_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(control, field_name, value)

    await session.commit()
    await session.refresh(control)
    return control


@router.delete("/controls/{control_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_control(
    control_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> None:
    """Soft-delete a control and remove its ENFORCED_BY edges from Neo4j."""
    from datetime import UTC, datetime

    result = await session.execute(select(Control).where(Control.id == control_id, Control.deleted_at.is_(None)))
    control = result.scalar_one_or_none()
    if not control:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Control {control_id} not found")

    # Remove ENFORCED_BY edges from Neo4j
    try:
        from src.semantic.graph import KnowledgeGraphService

        driver = request.app.state.neo4j_driver
        graph_service = KnowledgeGraphService(driver)
        await graph_service.run_query(
            "MATCH (:Activity)-[r:ENFORCED_BY]->(c:Control {id: $control_id}) DELETE r",
            {"control_id": str(control_id)},
        )
    except Exception:
        logger.warning("Failed to remove ENFORCED_BY edges for control %s from Neo4j", control_id)

    control.deleted_at = datetime.now(UTC)
    await log_audit(
        session,
        control.engagement_id,
        AuditAction.CONTROL_DELETED,
        json.dumps({"id": str(control_id), "name": control.name}),
    )
    await session.commit()


# -- Regulation Routes --------------------------------------------------------


@router.post("/regulations", response_model=RegulationResponse, status_code=status.HTTP_201_CREATED)
async def create_regulation(
    payload: RegulationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Regulation:
    """Create a new regulation."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == payload.engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Engagement {payload.engagement_id} not found")
    regulation = Regulation(
        engagement_id=payload.engagement_id,
        name=payload.name,
        framework=payload.framework,
        jurisdiction=payload.jurisdiction,
        obligations=payload.obligations,
    )
    session.add(regulation)
    await session.flush()
    await log_audit(session, payload.engagement_id, AuditAction.REGULATION_CREATED, json.dumps({"name": payload.name}))
    await session.commit()
    await session.refresh(regulation)
    return regulation


@router.get("/regulations", response_model=RegulationList)
async def list_regulations(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    framework: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List regulations for an engagement, optionally filtered by framework."""
    query = select(Regulation).where(Regulation.engagement_id == engagement_id, Regulation.deleted_at.is_(None))
    count_query = select(func.count()).select_from(Regulation).where(Regulation.engagement_id == engagement_id, Regulation.deleted_at.is_(None))

    if framework is not None:
        query = query.where(Regulation.framework == framework)
        count_query = count_query.where(Regulation.framework == framework)
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
    user: User = Depends(require_permission("engagement:update")),
) -> Regulation:
    """Update a regulation's fields (partial update)."""
    result = await session.execute(select(Regulation).where(Regulation.id == regulation_id, Regulation.deleted_at.is_(None)))
    regulation = result.scalar_one_or_none()
    if not regulation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation {regulation_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(regulation, field_name, value)

    await session.commit()
    await session.refresh(regulation)
    return regulation


@router.delete("/regulations/{regulation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_regulation(
    regulation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> None:
    """Soft-delete a regulation (sets deleted_at, does not hard delete)."""
    from datetime import UTC, datetime

    result = await session.execute(select(Regulation).where(Regulation.id == regulation_id, Regulation.deleted_at.is_(None)))
    regulation = result.scalar_one_or_none()
    if not regulation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation {regulation_id} not found")

    regulation.deleted_at = datetime.now(UTC)
    await log_audit(session, regulation.engagement_id, AuditAction.REGULATION_DELETED, json.dumps({"id": str(regulation_id), "name": regulation.name}))
    await session.commit()


# -- Governance Chain Traversal -----------------------------------------------


class GovernanceChainLink(BaseModel):
    """A single link in the governance chain."""

    entity_id: str
    entity_type: str
    name: str
    relationship_type: str | None = None


class GovernanceChainResponse(BaseModel):
    """Response for governance chain traversal."""

    activity_id: str
    chain: list[GovernanceChainLink]


@router.get("/activities/{activity_id}/governance-chain", response_model=GovernanceChainResponse)
async def get_governance_chain(
    activity_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Traverse the full governance chain for a process activity.

    Returns: Activity -> Control -> Policy -> Regulation chain from Neo4j.
    """
    from src.semantic.graph import KnowledgeGraphService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)

    query = (
        "MATCH (a:Activity {id: $activity_id})-[:ENFORCED_BY]->(c:Control)"
        "-[:ENFORCES]->(p:Policy)-[:GOVERNED_BY]->(r:Regulation) "
        "RETURN a.id AS activity_id, a.name AS activity_name, "
        "c.id AS control_id, c.name AS control_name, "
        "p.id AS policy_id, p.name AS policy_name, "
        "r.id AS regulation_id, r.name AS regulation_name"
    )
    records = await graph_service.run_query(query, {"activity_id": str(activity_id)})

    chain: list[dict[str, Any]] = []
    if records:
        rec = records[0]
        chain = [
            {"entity_id": rec.get("activity_id", ""), "entity_type": "Activity", "name": rec.get("activity_name", ""), "relationship_type": None},
            {"entity_id": rec.get("control_id", ""), "entity_type": "Control", "name": rec.get("control_name", ""), "relationship_type": "ENFORCED_BY"},
            {"entity_id": rec.get("policy_id", ""), "entity_type": "Policy", "name": rec.get("policy_name", ""), "relationship_type": "ENFORCES"},
            {"entity_id": rec.get("regulation_id", ""), "entity_type": "Regulation", "name": rec.get("regulation_name", ""), "relationship_type": "GOVERNED_BY"},
        ]

    return {"activity_id": str(activity_id), "chain": chain}


# -- Overlay Engine Routes (Story #29) ----------------------------------------


@router.post("/overlay/{engagement_id}/build")
async def build_governance_overlay(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
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
    _engagement_user: User = Depends(require_engagement_access),
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
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Find processes without governance links."""
    from src.core.regulatory import RegulatoryOverlayEngine
    from src.semantic.graph import KnowledgeGraphService

    driver = request.app.state.neo4j_driver
    graph_service = KnowledgeGraphService(driver)
    engine = RegulatoryOverlayEngine(graph_service)

    ungoverned = await engine.find_ungoverned_processes(str(engagement_id))
    return {"engagement_id": str(engagement_id), "ungoverned": ungoverned, "count": len(ungoverned)}
