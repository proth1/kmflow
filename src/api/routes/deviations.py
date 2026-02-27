"""Deviation query API endpoint for process deviation detection (Story #350).

Provides GET /api/v1/deviations with filtering by type, severity,
time range, and engagement. Supports pagination with limit/offset.
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
from src.core.models import (
    DeviationCategory,
    DeviationSeverity,
    ProcessDeviation,
    User,
)
from src.core.permissions import require_engagement_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/deviations", tags=["deviations"])


class DeviationResponse(BaseModel):
    """Response schema for a single deviation."""

    id: UUID
    engagement_id: UUID
    category: str
    severity: str | None = None
    severity_score: float = 0.0
    description: str
    affected_element: str | None = None
    process_element_id: str | None = None
    telemetry_ref: str | None = None
    magnitude: float = 0.0
    details_json: dict | None = None
    detected_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDeviationResponse(BaseModel):
    """Paginated response for deviation queries."""

    items: list[DeviationResponse]
    total: int
    limit: int
    offset: int


@router.get("", response_model=PaginatedDeviationResponse)
async def list_deviations(
    engagement_id: UUID = Query(..., description="Engagement to query deviations for"),
    type: DeviationCategory | None = Query(None, description="Filter by deviation category"),
    severity: DeviationSeverity | None = Query(None, description="Filter by severity"),
    from_date: datetime | None = Query(None, alias="from", description="Filter from date"),
    to_date: datetime | None = Query(None, alias="to", description="Filter to date"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Query deviations with filters for type, severity, and time range.

    Returns paginated results ordered by detected_at descending.
    Each deviation includes: id, type, severity, process_element_id,
    detected_at, and telemetry_ref.
    """
    query = select(ProcessDeviation).where(
        ProcessDeviation.engagement_id == engagement_id,
    )
    count_query = (
        select(func.count())
        .select_from(ProcessDeviation)
        .where(
            ProcessDeviation.engagement_id == engagement_id,
        )
    )

    if type is not None:
        query = query.where(ProcessDeviation.category == type)
        count_query = count_query.where(ProcessDeviation.category == type)
    if severity is not None:
        query = query.where(ProcessDeviation.severity == severity)
        count_query = count_query.where(ProcessDeviation.severity == severity)
    if from_date is not None:
        query = query.where(ProcessDeviation.detected_at >= from_date)
        count_query = count_query.where(ProcessDeviation.detected_at >= from_date)
    if to_date is not None:
        query = query.where(ProcessDeviation.detected_at <= to_date)
        count_query = count_query.where(ProcessDeviation.detected_at <= to_date)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(ProcessDeviation.detected_at.desc())
    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
