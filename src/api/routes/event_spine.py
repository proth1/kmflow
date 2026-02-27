"""Event spine API routes.

Provides endpoints for building and retrieving case event spines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import Engagement, User
from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.permissions import require_engagement_access, require_permission

router = APIRouter(prefix="/api/v1", tags=["event-spine"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CanonicalEventResponse(BaseModel):
    """Response schema for a single canonical event."""

    model_config = {"from_attributes": True}

    id: UUID
    case_id: str
    activity_name: str
    timestamp_utc: datetime
    source_system: str
    performer_role_ref: str | None
    confidence_score: float
    brightness: str | None
    mapping_status: str
    process_element_id: UUID | None


class EventSpineResponse(BaseModel):
    """Response schema for a case's event spine."""

    engagement_id: UUID
    case_id: str
    total_events: int
    events: list[CanonicalEventResponse]


class CaseListResponse(BaseModel):
    """Response listing distinct case IDs in an engagement."""

    engagement_id: UUID
    cases: list[str]
    total: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/engagements/{engagement_id}/cases",
    response_model=CaseListResponse,
)
async def list_cases(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List distinct case IDs that have events in this engagement."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    result = await session.execute(
        select(CanonicalActivityEvent.case_id)
        .where(CanonicalActivityEvent.engagement_id == engagement_id)
        .distinct()
        .order_by(CanonicalActivityEvent.case_id)
    )
    cases = [row[0] for row in result.all()]
    return {"engagement_id": engagement_id, "cases": cases, "total": len(cases)}


@router.get(
    "/cases/{case_id}/event-spine",
    response_model=EventSpineResponse,
)
async def get_event_spine(
    case_id: str,
    engagement_id: UUID = Query(..., description="Engagement ID for authorization"),
    limit: int = Query(200, ge=1, le=2000, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Retrieve the chronological event spine for a case.

    Events are ordered by timestamp_utc ascending to form a complete
    case timeline.
    """
    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Total count for pagination
    count_result = await session.execute(
        select(func.count())
        .select_from(CanonicalActivityEvent)
        .where(
            CanonicalActivityEvent.case_id == case_id,
            CanonicalActivityEvent.engagement_id == engagement_id,
        )
    )
    total = count_result.scalar() or 0

    # Paginated events
    result = await session.execute(
        select(CanonicalActivityEvent)
        .where(
            CanonicalActivityEvent.case_id == case_id,
            CanonicalActivityEvent.engagement_id == engagement_id,
        )
        .order_by(CanonicalActivityEvent.timestamp_utc.asc())
        .limit(limit)
        .offset(offset)
    )
    events = list(result.scalars().all())

    return {
        "engagement_id": engagement_id,
        "case_id": case_id,
        "total_events": total,
        "events": events,
    }
