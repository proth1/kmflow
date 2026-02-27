"""Audit log query routes for compliance investigations.

Provides paginated, filterable access to audit log entries.
Only PLATFORM_ADMIN users may query audit logs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import AuditAction, AuditLog, User
from src.core.permissions import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


# -- Schemas ------------------------------------------------------------------


class AuditLogResponse(BaseModel):
    """Single audit log entry in API responses."""

    id: UUID
    engagement_id: UUID | None = None
    action: str
    actor: str
    details: str | None = None
    user_id: UUID | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    result_status: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAuditLogResponse(BaseModel):
    """Paginated audit log response with total count."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


# -- Routes -------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedAuditLogResponse,
    summary="Query audit logs with filtering and pagination",
)
async def list_audit_logs(
    user_id: UUID | None = Query(None, description="Filter by user_id"),
    engagement_id: UUID | None = Query(None, description="Filter by engagement_id"),
    action: AuditAction | None = Query(None, description="Filter by action type"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    from_date: datetime | None = Query(None, alias="from", description="Start date (inclusive)"),
    to_date: datetime | None = Query(None, alias="to", description="End date (inclusive)"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("PLATFORM_ADMIN")),
) -> dict[str, Any]:
    """Query audit logs with optional filters.

    Requires PLATFORM_ADMIN role. Returns paginated results ordered by
    created_at descending (newest first).
    """
    base_query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    # Apply filters
    if user_id is not None:
        base_query = base_query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if engagement_id is not None:
        base_query = base_query.where(AuditLog.engagement_id == engagement_id)
        count_query = count_query.where(AuditLog.engagement_id == engagement_id)
    if action is not None:
        base_query = base_query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type is not None:
        base_query = base_query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)
    if from_date is not None:
        base_query = base_query.where(AuditLog.created_at >= from_date)
        count_query = count_query.where(AuditLog.created_at >= from_date)
    if to_date is not None:
        base_query = base_query.where(AuditLog.created_at <= to_date)
        count_query = count_query.where(AuditLog.created_at <= to_date)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate and order
    items_query = base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(items_query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
