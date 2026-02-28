"""Financial assumption management routes (Story #354).

Engagement-scoped CRUD for financial assumptions with version history.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import FinancialAssumption, FinancialAssumptionType, User
from src.core.permissions import require_engagement_access, require_permission
from src.simulation.assumption_service import (
    create_assumption,
    get_assumption_history,
    list_assumptions,
    update_assumption,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assumptions"])


# ── Schemas ────────────────────────────────────────────────────────────


class AssumptionCreate(BaseModel):
    """Create a financial assumption."""

    assumption_type: FinancialAssumptionType
    name: str = Field(..., min_length=1, max_length=256)
    value: float
    unit: str = Field(..., min_length=1, max_length=50)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_evidence_id: UUID | None = None
    confidence_explanation: str | None = None
    confidence_range: float | None = Field(None, ge=0.0, le=1.0)
    notes: str | None = None

    @model_validator(mode="after")
    def require_source_or_explanation(self) -> AssumptionCreate:
        if not self.source_evidence_id and not self.confidence_explanation:
            msg = "source_evidence_id or confidence_explanation is required"
            raise ValueError(msg)
        return self


class AssumptionUpdate(BaseModel):
    """Partial update for a financial assumption."""

    value: float | None = None
    unit: str | None = Field(None, max_length=50)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    confidence_range: float | None = Field(None, ge=0.0, le=1.0)
    source_evidence_id: UUID | None = None
    confidence_explanation: str | None = None
    notes: str | None = None
    name: str | None = Field(None, max_length=256)


# ── Routes ─────────────────────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/assumptions",
    status_code=status.HTTP_201_CREATED,
)
async def create_engagement_assumption(
    engagement_id: UUID,
    payload: AssumptionCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Create a financial assumption for an engagement."""
    try:
        assumption = await create_assumption(session, engagement_id, payload.model_dump())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e

    await session.commit()
    await session.refresh(assumption)
    return _assumption_to_dict(assumption)


@router.get("/engagements/{engagement_id}/assumptions")
async def list_engagement_assumptions(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    assumption_type: FinancialAssumptionType | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List financial assumptions for an engagement with optional type filter."""
    result = await list_assumptions(session, engagement_id, assumption_type, limit, offset)
    return {
        "items": [_assumption_to_dict(a) for a in result["items"]],
        "total": result["total"],
    }


@router.patch("/engagements/{engagement_id}/assumptions/{assumption_id}")
async def update_engagement_assumption(
    engagement_id: UUID,
    assumption_id: UUID,
    payload: AssumptionUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Update a financial assumption and record version history."""
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    try:
        assumption = await update_assumption(session, assumption_id, update_data, user.id, engagement_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await session.commit()
    await session.refresh(assumption)
    return _assumption_to_dict(assumption)


@router.get("/engagements/{engagement_id}/assumptions/{assumption_id}/history")
async def get_assumption_version_history(
    engagement_id: UUID,
    assumption_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get version history for a financial assumption."""
    try:
        versions = await get_assumption_history(session, assumption_id, engagement_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return {
        "assumption_id": str(assumption_id),
        "versions": [
            {
                "id": str(v.id),
                "value": v.value,
                "unit": v.unit,
                "confidence": v.confidence,
                "confidence_range": v.confidence_range,
                "source_evidence_id": str(v.source_evidence_id) if v.source_evidence_id else None,
                "confidence_explanation": v.confidence_explanation,
                "notes": v.notes,
                "changed_by": str(v.changed_by) if v.changed_by else None,
                "changed_at": v.changed_at.isoformat() if v.changed_at else "",
            }
            for v in versions
        ],
    }


def _assumption_to_dict(a: FinancialAssumption) -> dict[str, Any]:
    """Serialize a FinancialAssumption to response dict."""
    return {
        "id": str(a.id),
        "engagement_id": str(a.engagement_id),
        "assumption_type": a.assumption_type.value if hasattr(a.assumption_type, "value") else str(a.assumption_type),
        "name": a.name,
        "value": a.value,
        "unit": a.unit,
        "confidence": a.confidence,
        "confidence_range": a.confidence_range,
        "source_evidence_id": str(a.source_evidence_id) if a.source_evidence_id else None,
        "confidence_explanation": a.confidence_explanation,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
