"""Shelf data request management routes.

Provides creation, tracking, and fulfillment of shelf data requests
used to gather evidence from clients during engagements.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_session
from src.core.models import (
    AuditAction,
    AuditLog,
    EvidenceCategory,
    EvidenceItem,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemPriority,
    ShelfRequestItemSource,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
    User,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/shelf-requests", tags=["shelf-requests"])


# -- Request/Response Schemas ------------------------------------------------


class ShelfRequestItemCreate(BaseModel):
    """Schema for creating a shelf data request item."""

    category: EvidenceCategory
    item_name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    priority: ShelfRequestItemPriority = ShelfRequestItemPriority.MEDIUM


class ShelfRequestCreate(BaseModel):
    """Schema for creating a shelf data request."""

    engagement_id: UUID
    title: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    due_date: str | None = None  # ISO date string
    items: list[ShelfRequestItemCreate] = Field(default_factory=list)


class ShelfRequestUpdate(BaseModel):
    """Schema for updating a shelf data request."""

    title: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    status: ShelfRequestStatus | None = None
    due_date: str | None = None


class ShelfRequestItemResponse(BaseModel):
    """Schema for shelf data request item responses."""

    model_config = {"from_attributes": True}

    id: UUID
    request_id: UUID
    category: EvidenceCategory
    item_name: str
    description: str | None = None
    priority: ShelfRequestItemPriority
    status: ShelfRequestItemStatus
    matched_evidence_id: UUID | None = None
    epistemic_action_id: UUID | None = None
    source: ShelfRequestItemSource = ShelfRequestItemSource.MANUAL


class ShelfRequestResponse(BaseModel):
    """Schema for shelf data request responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    title: str
    description: str | None = None
    status: ShelfRequestStatus
    due_date: Any | None = None
    items: list[ShelfRequestItemResponse] = Field(default_factory=list)
    fulfillment_percentage: float = 0.0


class ShelfRequestList(BaseModel):
    """Schema for listing shelf data requests."""

    items: list[ShelfRequestResponse]
    total: int


class ShelfRequestStatusResponse(BaseModel):
    """Schema for shelf request fulfillment status."""

    id: UUID
    title: str
    status: ShelfRequestStatus
    total_items: int
    received_items: int
    pending_items: int
    overdue_items: int
    fulfillment_percentage: float


class IntakeRequest(BaseModel):
    """Schema for client evidence submission / intake."""

    evidence_id: UUID
    item_id: UUID | None = None  # If None, auto-match by category


class IntakeResponse(BaseModel):
    """Schema for intake response."""

    matched_item_id: UUID | None = None
    matched_item_name: str | None = None
    evidence_id: UUID
    auto_matched: bool = False


# -- Helpers ------------------------------------------------------------------


async def _get_request_or_404(
    session: AsyncSession,
    request_id: UUID,
) -> ShelfDataRequest:
    """Fetch a shelf data request by ID with items eagerly loaded, or raise 404."""
    result = await session.execute(
        select(ShelfDataRequest).options(selectinload(ShelfDataRequest.items)).where(ShelfDataRequest.id == request_id)
    )
    shelf_request = result.scalar_one_or_none()
    if not shelf_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shelf data request {request_id} not found",
        )
    return shelf_request


# -- Routes -------------------------------------------------------------------


@router.post("/", response_model=ShelfRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_shelf_request(
    payload: ShelfRequestCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> ShelfDataRequest:
    """Create a new shelf data request with items.

    Creates the request in DRAFT status with the specified items.
    """
    from datetime import date

    shelf_request = ShelfDataRequest(
        engagement_id=payload.engagement_id,
        title=payload.title,
        description=payload.description,
        due_date=date.fromisoformat(payload.due_date) if payload.due_date else None,
    )
    session.add(shelf_request)
    await session.flush()

    # Create items
    for item_data in payload.items:
        item = ShelfDataRequestItem(
            request_id=shelf_request.id,
            category=item_data.category,
            item_name=item_data.item_name,
            description=item_data.description,
            priority=item_data.priority,
        )
        session.add(item)

    # Audit log
    audit = AuditLog(
        engagement_id=payload.engagement_id,
        action=AuditAction.SHELF_REQUEST_CREATED,
        details=json.dumps(
            {
                "request_title": payload.title,
                "item_count": len(payload.items),
            }
        ),
    )
    session.add(audit)

    await session.commit()

    # Re-fetch with items loaded
    return await _get_request_or_404(session, shelf_request.id)


@router.get("/", response_model=ShelfRequestList)
async def list_shelf_requests(
    engagement_id: UUID | None = None,
    status_filter: ShelfRequestStatus | None = None,
    source: ShelfRequestItemSource | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List shelf data requests with optional filtering.

    Query parameters:
    - engagement_id: Filter by engagement
    - status_filter: Filter by request status
    - source: Filter by item source (planner/manual) — returns requests containing matching items
    - limit: Maximum results (default 20)
    - offset: Number of results to skip (default 0)
    """
    from sqlalchemy import func

    query = select(ShelfDataRequest).options(selectinload(ShelfDataRequest.items))
    count_query = select(func.count()).select_from(ShelfDataRequest)

    if engagement_id is not None:
        query = query.where(ShelfDataRequest.engagement_id == engagement_id)
        count_query = count_query.where(ShelfDataRequest.engagement_id == engagement_id)
    if status_filter is not None:
        query = query.where(ShelfDataRequest.status == status_filter)
        count_query = count_query.where(ShelfDataRequest.status == status_filter)
    if source is not None:
        query = query.where(
            ShelfDataRequest.id.in_(
                select(ShelfDataRequestItem.request_id).where(ShelfDataRequestItem.source == source)
            )
        )
        count_query = count_query.where(
            ShelfDataRequest.id.in_(
                select(ShelfDataRequestItem.request_id).where(ShelfDataRequestItem.source == source)
            )
        )

    query = query.offset(offset).limit(limit).order_by(ShelfDataRequest.created_at.desc())

    result = await session.execute(query)
    items = list(result.scalars().unique().all())

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


class FollowThroughRateResponse(BaseModel):
    """Schema for follow-through rate response."""

    engagement_id: UUID
    total_epistemic_actions: int
    linked_shelf_items: int
    follow_through_rate: float
    target_rate: float
    meets_target: bool


@router.get("/follow-through-rate", response_model=FollowThroughRateResponse)
async def get_follow_through_rate(
    engagement_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get follow-through rate for planner-driven shelf requests.

    Follow-through rate = shelf items linked to epistemic actions /
    total epistemic actions. Target: >50%.
    """
    from src.api.services.shelf_integration import ShelfIntegrationService

    service = ShelfIntegrationService(session)
    return await service.get_follow_through_rate(engagement_id)


@router.get("/{request_id}", response_model=ShelfRequestResponse)
async def get_shelf_request(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> ShelfDataRequest:
    """Get a shelf data request by ID with items."""
    return await _get_request_or_404(session, request_id)


@router.get("/{request_id}/status", response_model=ShelfRequestStatusResponse)
async def get_shelf_request_status(
    request_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get fulfillment status for a shelf data request.

    Returns counts of received, pending, and overdue items
    along with fulfillment percentage.
    """
    shelf_request = await _get_request_or_404(session, request_id)

    total_items = len(shelf_request.items)
    received_items = sum(1 for i in shelf_request.items if i.status == ShelfRequestItemStatus.RECEIVED)
    pending_items = sum(1 for i in shelf_request.items if i.status == ShelfRequestItemStatus.PENDING)
    overdue_items = sum(1 for i in shelf_request.items if i.status == ShelfRequestItemStatus.OVERDUE)

    return {
        "id": shelf_request.id,
        "title": shelf_request.title,
        "status": shelf_request.status,
        "total_items": total_items,
        "received_items": received_items,
        "pending_items": pending_items,
        "overdue_items": overdue_items,
        "fulfillment_percentage": shelf_request.fulfillment_percentage,
    }


@router.patch("/{request_id}", response_model=ShelfRequestResponse)
async def update_shelf_request(
    request_id: UUID,
    payload: ShelfRequestUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> ShelfDataRequest:
    """Update a shelf data request.

    Can update title, description, status, and due_date.
    Use status change to SENT to finalize the request.
    """
    from datetime import date

    shelf_request = await _get_request_or_404(session, request_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return shelf_request

    changed: dict[str, Any] = {}
    for field_name, value in update_data.items():
        if field_name == "due_date" and value is not None:
            value = date.fromisoformat(value)
        old_value = getattr(shelf_request, field_name)
        if hasattr(old_value, "value"):
            old_value = old_value.value
        value_cmp = value.value if hasattr(value, "value") else value
        if old_value != value_cmp:
            changed[field_name] = {"from": str(old_value), "to": str(value_cmp)}
        setattr(shelf_request, field_name, value)

    if changed:
        audit = AuditLog(
            engagement_id=shelf_request.engagement_id,
            action=AuditAction.SHELF_REQUEST_UPDATED,
            details=json.dumps(changed),
        )
        session.add(audit)

    await session.commit()
    return await _get_request_or_404(session, request_id)


@router.post("/{request_id}/intake", response_model=IntakeResponse)
async def submit_evidence_intake(
    request_id: UUID,
    payload: IntakeRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Submit evidence for a shelf data request.

    Matches uploaded evidence to a request item. If item_id is not provided,
    auto-matches by category and name similarity.
    """
    shelf_request = await _get_request_or_404(session, request_id)

    # Verify evidence exists
    ev_result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == payload.evidence_id))
    evidence = ev_result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {payload.evidence_id} not found",
        )

    matched_item: ShelfDataRequestItem | None = None

    if payload.item_id:
        # Direct match to specified item
        for item in shelf_request.items:
            if item.id == payload.item_id:
                matched_item = item
                break
        if not matched_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request item {payload.item_id} not found in this request",
            )
    else:
        # Auto-match by category
        for item in shelf_request.items:
            if item.category == evidence.category and item.status == ShelfRequestItemStatus.PENDING:
                matched_item = item
                break

        # If no category match, try name similarity
        if not matched_item:
            evidence_name_lower = evidence.name.lower()
            for item in shelf_request.items:
                if item.status == ShelfRequestItemStatus.PENDING and item.item_name.lower() in evidence_name_lower:
                    matched_item = item
                    break

    if matched_item:
        matched_item.matched_evidence_id = evidence.id
        matched_item.status = ShelfRequestItemStatus.RECEIVED
        await session.commit()

        return {
            "matched_item_id": matched_item.id,
            "matched_item_name": matched_item.item_name,
            "evidence_id": evidence.id,
            "auto_matched": payload.item_id is None,
        }

    # No match found - still associate the evidence but don't match an item
    return {
        "matched_item_id": None,
        "matched_item_name": None,
        "evidence_id": evidence.id,
        "auto_matched": False,
    }
