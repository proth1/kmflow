"""Policy Decision Point (PDP) API endpoints (Story #377).

Provides policy evaluation, rule management, and health check endpoints
for the lightweight PDP service.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import PDPDecisionType, User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pdp", tags=["pdp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EvaluateRequest(BaseModel):
    """Request to evaluate a policy decision."""

    engagement_id: UUID
    resource_id: str = Field(..., min_length=1, max_length=255)
    classification: str = Field(..., pattern=r"^(public|internal|confidential|restricted)$")
    operation: str = Field(..., pattern=r"^(read|write|export|delete)$")
    request_id: str | None = None


class ObligationResponse(BaseModel):
    """An obligation attached to a PERMIT decision."""

    type: str
    params: dict[str, Any] | None = None


class EvaluateResponse(BaseModel):
    """Response from a policy evaluation."""

    decision: PDPDecisionType
    reason: str | None = None
    obligations: list[dict[str, Any]]
    audit_id: str
    latency_ms: float
    required_role: str | None = None


class CreateRuleRequest(BaseModel):
    """Request to create a new policy rule."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    conditions_json: dict
    decision: PDPDecisionType
    obligations_json: list[dict[str, Any]] | None = None
    reason: str | None = None
    priority: int = Field(default=100, ge=1, le=1000)


class PolicyRuleResponse(BaseModel):
    """Response schema for a policy rule."""

    id: UUID
    name: str
    description: str | None = None
    conditions_json: dict
    decision: str
    obligations_json: list | None = None
    reason: str | None = None
    priority: int
    is_active: bool

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """PDP health check response."""

    status: str
    decisions_tracked: int
    p99_latency_ms: float
    avg_latency_ms: float | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    body: EvaluateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pdp:evaluate")),
) -> Any:
    """Evaluate a policy decision for an access request.

    Returns PERMIT or DENY with optional obligations and audit trail entry.
    """
    from src.api.services.pdp import PDPService

    service = PDPService(session)
    result = await service.evaluate(
        engagement_id=body.engagement_id,
        actor=user.email,
        actor_role=user.role.value if hasattr(user.role, "value") else str(user.role),
        resource_id=body.resource_id,
        classification=body.classification,
        operation=body.operation,
        request_id=body.request_id,
    )
    return result


@router.post("/rules", response_model=PolicyRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: CreateRuleRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pdp:admin")),
) -> Any:
    """Create a new policy rule (hot-reloaded on next evaluation)."""
    from src.api.services.pdp import PDPService

    service = PDPService(session)
    try:
        policy = await service.create_rule(
            name=body.name,
            description=body.description,
            conditions_json=body.conditions_json,
            decision=body.decision,
            obligations_json=body.obligations_json,
            reason=body.reason,
            priority=body.priority,
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Policy rule '{body.name}' already exists",
            ) from exc
        raise
    return policy


@router.get("/rules", response_model=list[PolicyRuleResponse])
async def list_rules(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("pdp:admin")),
) -> Any:
    """List all active policy rules ordered by priority."""
    from src.api.services.pdp import PDPService

    service = PDPService(session)
    return await service.list_rules()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> dict[str, Any]:
    """PDP health check with p99 latency metric."""
    from src.api.services.pdp import PDPService

    return PDPService.get_health_metrics()
