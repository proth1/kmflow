"""Data classification and GDPR compliance routes (Story #317).

Provides endpoints for classification-based access control, per-engagement
retention policies, GDPR processing activities (ROPA), and compliance reporting.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.models.gdpr import LawfulBasis, RetentionAction
from src.core.permissions import require_engagement_access, require_permission
from src.core.services.gdpr_service import GdprComplianceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-classification", tags=["data-classification"])


# ── Schemas ────────────────────────────────────────────────────────────


class SetRetentionPayload(BaseModel):
    """Request body for setting retention policy."""

    retention_days: int = Field(..., ge=1, le=3650)
    action: RetentionAction = RetentionAction.ARCHIVE


class CreateProcessingActivityPayload(BaseModel):
    """Request body for creating a processing activity."""

    name: str = Field(..., max_length=256)
    description: str | None = None
    lawful_basis: LawfulBasis
    article_6_basis: str = Field(default="Art. 6(1)(f)", max_length=50)


# ── Retention Policy ──────────────────────────────────────────────────


@router.put("/retention/{engagement_id}")
async def set_retention_policy(
    engagement_id: UUID,
    payload: SetRetentionPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Set or update the retention policy for an engagement."""
    service = GdprComplianceService(session)
    policy = await service.set_retention_policy(
        engagement_id=engagement_id,
        retention_days=payload.retention_days,
        action=payload.action,
        created_by=user.id,
    )
    return {
        "id": str(policy.id),
        "engagement_id": str(policy.engagement_id),
        "retention_days": policy.retention_days,
        "action": policy.action.value,
    }


@router.get("/retention/{engagement_id}")
async def get_retention_policy(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get the retention policy for an engagement."""
    service = GdprComplianceService(session)
    policy = await service.get_retention_policy(engagement_id)
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No retention policy configured for this engagement",
        )
    return {
        "id": str(policy.id),
        "engagement_id": str(policy.engagement_id),
        "retention_days": policy.retention_days,
        "action": policy.action.value,
    }


@router.post("/retention/{engagement_id}/enforce")
async def enforce_retention(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Run retention enforcement for an engagement.

    Archives or deletes evidence items older than the configured
    retention period.
    """
    service = GdprComplianceService(session)
    return await service.enforce_retention(engagement_id)


# ── Processing Activities (ROPA) ──────────────────────────────────────


@router.post(
    "/processing-activities/{engagement_id}",
    status_code=status.HTTP_201_CREATED,
)
async def create_processing_activity(
    engagement_id: UUID,
    payload: CreateProcessingActivityPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Record a data processing activity with GDPR lawful basis."""
    service = GdprComplianceService(session)
    activity = await service.create_processing_activity(
        engagement_id=engagement_id,
        name=payload.name,
        description=payload.description,
        lawful_basis=payload.lawful_basis,
        article_6_basis=payload.article_6_basis,
        created_by=user.id,
    )
    return {
        "id": str(activity.id),
        "engagement_id": str(activity.engagement_id),
        "name": activity.name,
        "lawful_basis": activity.lawful_basis.value,
        "article_6_basis": activity.article_6_basis,
    }


@router.get("/processing-activities/{engagement_id}")
async def list_processing_activities(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List processing activities for an engagement."""
    service = GdprComplianceService(session)
    return await service.query_processing_activities(
        engagement_id=engagement_id,
        limit=limit,
        offset=offset,
    )


# ── Compliance Report ─────────────────────────────────────────────────


@router.get("/compliance/{engagement_id}")
async def get_compliance_report(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate a GDPR compliance report for an engagement.

    Reports processing activities by lawful basis and evidence items
    by classification level.
    """
    service = GdprComplianceService(session)
    return await service.get_compliance_report(engagement_id)
