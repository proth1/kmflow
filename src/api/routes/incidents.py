"""Incident response API endpoints (Story #397).

Provides POST create, POST contain, POST close, and GET timeline
for security incident lifecycle management with GDPR deadline tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import IncidentClassification, IncidentStatus, User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateIncidentRequest(BaseModel):
    """Request to create a new incident."""

    engagement_id: UUID
    classification: IncidentClassification
    title: str
    description: str
    reported_by: str


class ContainIncidentRequest(BaseModel):
    """Request to execute containment actions."""

    actor: str


class CloseIncidentRequest(BaseModel):
    """Request to close an incident with resolution summary."""

    resolution_summary: str
    actor: str


class IncidentResponse(BaseModel):
    """Response schema for an incident."""

    id: UUID
    engagement_id: UUID
    classification: IncidentClassification
    status: IncidentStatus
    title: str
    description: str
    reported_by: str
    notification_deadline: datetime | None = None
    resolution_summary: str | None = None
    created_at: datetime
    contained_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContainmentResponse(BaseModel):
    """Response for containment action."""

    incident_id: str
    status: IncidentStatus
    contained_at: str
    actions_taken: list[str]
    actor: str


class CloseResponse(BaseModel):
    """Response for closing an incident."""

    incident_id: str
    classification: str
    status: IncidentStatus
    resolution_summary: str
    closed_at: str
    timeline: list[dict[str, Any]]
    retention_years: int


class TimelineEventResponse(BaseModel):
    """A single event in the incident timeline."""

    event_type: str
    actor: str
    description: str
    timestamp: str
    details: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: CreateIncidentRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:write")),
) -> Any:
    """Create a new security incident.

    For P1 incidents, automatically sets the 72-hour GDPR notification
    deadline and alerts the DPO and engagement lead.
    """
    from src.api.services.incident import IncidentService

    service = IncidentService(session)
    incident = await service.create_incident(
        engagement_id=body.engagement_id,
        classification=body.classification,
        title=body.title,
        description=body.description,
        reported_by=body.reported_by,
    )
    return incident


@router.post("/{incident_id}/contain", response_model=ContainmentResponse)
async def contain_incident(
    incident_id: UUID,
    body: ContainIncidentRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:write")),
) -> dict[str, Any]:
    """Execute containment actions for an incident.

    For P1/P2: restricts non-DPO access and freezes audit logs.
    """
    from src.api.services.incident import IncidentService

    service = IncidentService(session)
    try:
        return await service.contain_incident(
            incident_id=incident_id,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/{incident_id}/close", response_model=CloseResponse)
async def close_incident(
    incident_id: UUID,
    body: CloseIncidentRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:write")),
) -> dict[str, Any]:
    """Close an incident and generate the full timeline.

    The timeline is permanently attached and retained per audit
    log policy (7 years).
    """
    from src.api.services.incident import IncidentService

    service = IncidentService(session)
    try:
        return await service.close_incident(
            incident_id=incident_id,
            resolution_summary=body.resolution_summary,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/{incident_id}/timeline", response_model=list[TimelineEventResponse])
async def get_incident_timeline(
    incident_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:read")),
) -> Any:
    """Retrieve the incident timeline as an ordered list of events."""
    from sqlalchemy import select

    from src.core.models import Incident

    result = await session.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    if incident.timeline_json:
        return incident.timeline_json

    # If no pre-generated timeline (incident not yet closed), build live
    from src.core.models import IncidentEvent

    event_result = await session.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.created_at)
    )
    events = event_result.scalars().all()

    return [
        {
            "event_type": e.event_type.value,
            "actor": e.actor,
            "description": e.description,
            "timestamp": e.created_at.isoformat(),
            "details": e.details_json,
        }
        for e in events
    ]


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    engagement_id: UUID = Query(..., description="Filter by engagement"),
    status_filter: IncidentStatus | None = Query(None, alias="status"),
    classification: IncidentClassification | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("incident:read")),
) -> Any:
    """List incidents for an engagement with optional filters."""
    from sqlalchemy import select

    from src.core.models import Incident

    query = select(Incident).where(Incident.engagement_id == engagement_id)
    if status_filter is not None:
        query = query.where(Incident.status == status_filter)
    if classification is not None:
        query = query.where(Incident.classification == classification)
    query = query.order_by(Incident.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    return result.scalars().all()
