"""Engagement management routes.

Provides full CRUD operations, filtering, dashboard, and audit logging
for consulting engagements.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.audit import log_audit
from src.core.models import (
    AuditAction,
    AuditLog,
    Engagement,
    EngagementMember,
    EngagementStatus,
    EvidenceCategory,
    EvidenceItem,
    User,
    UserRole,
)
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements", tags=["engagements"])


# -- Request/Response Schemas ------------------------------------------------


class EngagementCreate(BaseModel):
    """Schema for creating an engagement."""

    name: str = Field(..., min_length=1, max_length=255)
    client: str = Field(..., min_length=1, max_length=255)
    business_area: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    status: EngagementStatus = EngagementStatus.DRAFT
    team: list[str] = Field(default_factory=list)


class EngagementUpdate(BaseModel):
    """Schema for updating an engagement (PATCH). All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    client: str | None = Field(None, min_length=1, max_length=255)
    business_area: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: EngagementStatus | None = None
    team: list[str] | None = None


class EngagementResponse(BaseModel):
    """Schema for engagement responses."""

    model_config = {"from_attributes": True}

    id: UUID
    name: str
    client: str
    business_area: str
    description: str | None
    status: EngagementStatus
    team: list[str] | None = None


class EngagementList(BaseModel):
    """Schema for listing engagements."""

    items: list[EngagementResponse]
    total: int


class AuditLogResponse(BaseModel):
    """Schema for audit log responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    action: AuditAction
    actor: str
    details: str | None
    created_at: Any


class AuditLogList(BaseModel):
    """Schema for listing audit log entries."""

    items: list[AuditLogResponse]
    total: int


class DashboardResponse(BaseModel):
    """Schema for engagement dashboard summary."""

    engagement: EngagementResponse
    evidence_count: int
    evidence_by_category: dict[str, int]
    coverage_percentage: float


# -- Helpers ------------------------------------------------------------------


async def _get_engagement_or_404(session: AsyncSession, engagement_id: UUID) -> Engagement:
    """Fetch an engagement by ID or raise 404."""
    result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )
    return engagement


# -- Routes -------------------------------------------------------------------


@router.post("/", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    payload: EngagementCreate,
    user: User = Depends(require_permission("engagement:create")),
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Create a new consulting engagement."""
    engagement = Engagement(
        name=payload.name,
        client=payload.client,
        business_area=payload.business_area,
        description=payload.description,
        status=payload.status,
        team=payload.team,
    )
    session.add(engagement)
    await session.flush()

    await log_audit(
        session,
        engagement.id,
        AuditAction.ENGAGEMENT_CREATED,
        details=json.dumps({"name": payload.name, "client": payload.client}),
    )
    await session.commit()
    await session.refresh(engagement)
    return engagement


@router.get("/", response_model=EngagementList)
async def list_engagements(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: EngagementStatus | None = None,
    client: str | None = None,
    business_area: str | None = None,
    user: User = Depends(require_permission("engagement:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List engagements with filtering and pagination.

    Query parameters:
    - status: Filter by engagement status
    - client: Filter by client name (exact match)
    - business_area: Filter by business area (exact match)
    - limit: Maximum results to return (default 20)
    - offset: Number of results to skip (default 0)
    """
    query = select(Engagement)
    count_query = select(func.count()).select_from(Engagement)

    # Non-admin users can only see engagements they are members of
    if user.role != UserRole.PLATFORM_ADMIN:
        member_engagement_ids = (
            select(EngagementMember.engagement_id)
            .where(EngagementMember.user_id == user.id)
            .scalar_subquery()
        )
        query = query.where(Engagement.id.in_(member_engagement_ids))
        count_query = count_query.where(Engagement.id.in_(member_engagement_ids))

    # Apply filters
    if status_filter is not None:
        query = query.where(Engagement.status == status_filter)
        count_query = count_query.where(Engagement.status == status_filter)
    if client is not None:
        query = query.where(Engagement.client == client)
        count_query = count_query.where(Engagement.client == client)
    if business_area is not None:
        query = query.where(Engagement.business_area == business_area)
        count_query = count_query.where(Engagement.business_area == business_area)

    # Paginate
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    engagements = list(result.scalars().all())

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": engagements, "total": total}


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Get a specific engagement by ID."""
    return await _get_engagement_or_404(session, engagement_id)


@router.patch("/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(
    engagement_id: UUID,
    payload: EngagementUpdate,
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Update an engagement's fields (partial update).

    Only fields included in the request body are updated.
    """
    engagement = await _get_engagement_or_404(session, engagement_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return engagement

    changed_fields: dict[str, Any] = {}
    for field_name, value in update_data.items():
        old_value = getattr(engagement, field_name)
        # Convert enum to string for comparison
        if hasattr(old_value, "value"):
            old_value = old_value.value
        value_cmp = value.value if hasattr(value, "value") else value
        if old_value != value_cmp:
            changed_fields[field_name] = {"from": str(old_value), "to": str(value_cmp)}
        setattr(engagement, field_name, value)

    if changed_fields:
        await log_audit(
            session,
            engagement.id,
            AuditAction.ENGAGEMENT_UPDATED,
            details=json.dumps(changed_fields),
        )

    await session.commit()
    await session.refresh(engagement)
    return engagement


@router.patch("/{engagement_id}/archive", response_model=EngagementResponse)
async def archive_engagement(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:delete")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Archive an engagement by setting its status to ARCHIVED."""
    engagement = await _get_engagement_or_404(session, engagement_id)

    previous_status = engagement.status
    engagement.status = EngagementStatus.ARCHIVED
    await log_audit(
        session,
        engagement.id,
        AuditAction.ENGAGEMENT_ARCHIVED,
        details=json.dumps({"previous_status": str(previous_status)}),
    )
    await session.commit()
    await session.refresh(engagement)
    return engagement


@router.get("/{engagement_id}/dashboard", response_model=DashboardResponse)
async def get_engagement_dashboard(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get an engagement dashboard with evidence summary.

    Returns the engagement details along with:
    - Total evidence count
    - Evidence count broken down by category
    - Coverage percentage (categories with at least one evidence item / total categories)
    """
    engagement = await _get_engagement_or_404(session, engagement_id)

    # Count total evidence
    count_result = await session.execute(
        select(func.count()).select_from(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    )
    evidence_count = count_result.scalar() or 0

    # Count by category
    category_query = (
        select(EvidenceItem.category, func.count().label("count"))
        .where(EvidenceItem.engagement_id == engagement_id)
        .group_by(EvidenceItem.category)
    )
    category_result = await session.execute(category_query)
    evidence_by_category: dict[str, int] = {}
    for row in category_result:
        evidence_by_category[str(row.category)] = row.count  # type: ignore[assignment]

    # Coverage: proportion of the 12 evidence categories that have at least one item
    total_categories = len(EvidenceCategory)
    covered_categories = len(evidence_by_category)
    coverage_percentage = (covered_categories / total_categories * 100.0) if total_categories > 0 else 0.0

    return {
        "engagement": engagement,
        "evidence_count": evidence_count,
        "evidence_by_category": evidence_by_category,
        "coverage_percentage": round(coverage_percentage, 2),
    }


@router.get("/{engagement_id}/audit-logs", response_model=AuditLogList)
async def get_audit_logs(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get audit log entries for an engagement."""
    # Verify engagement exists
    await _get_engagement_or_404(session, engagement_id)

    count_result = await session.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.engagement_id == engagement_id)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.engagement_id == engagement_id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return {"items": list(result.scalars().all()), "total": total}
