"""Consent API routes for desktop endpoint capture (Story #382).

Provides endpoints for recording, withdrawing, querying, and updating
consent for desktop task mining. Enforces GDPR Art. 6(1)(a).
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
from src.core.permissions import require_engagement_access, require_permission
from src.security.consent.models import EndpointConsentType
from src.security.consent.service import ConsentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/consent", tags=["consent"])


class RecordConsentPayload(BaseModel):
    """Request body for recording consent."""

    participant_id: UUID
    engagement_id: UUID
    consent_type: EndpointConsentType
    scope: str = Field(default="application-usage-monitoring", max_length=512)
    policy_bundle_id: UUID


class UpdateOrgScopePayload(BaseModel):
    """Request body for org scope update."""

    new_scope: str = Field(..., max_length=512)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_consent(
    payload: RecordConsentPayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Record a new consent grant for a participant.

    Creates an immutable consent record linked to a policy bundle version.
    Returns 201 with the created consent record ID.
    """
    service = ConsentService(session)
    record = await service.record_consent(
        participant_id=payload.participant_id,
        engagement_id=payload.engagement_id,
        consent_type=payload.consent_type,
        scope=payload.scope,
        policy_bundle_id=payload.policy_bundle_id,
        recorded_by=user.id,
    )
    return {
        "id": str(record.id),
        "participant_id": str(record.participant_id),
        "engagement_id": str(record.engagement_id),
        "consent_type": record.consent_type.value,
        "scope": record.scope,
        "status": record.status.value,
        "recorded_at": record.recorded_at.isoformat() if record.recorded_at else None,
    }


@router.post("/{consent_id}/withdraw")
async def withdraw_consent(
    consent_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Withdraw consent for a participant.

    Marks the consent record as WITHDRAWN and queues a data deletion
    task targeting all four stores (PostgreSQL, Neo4j, pgvector, Redis).
    """
    service = ConsentService(session)
    result = await service.withdraw_consent(consent_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consent record not found or already withdrawn",
        )
    return result


@router.get("")
async def query_consent(
    participant_id: UUID | None = Query(default=None),
    engagement_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Query consent records with participant and engagement filters."""
    service = ConsentService(session)
    return await service.query_consent(
        participant_id=participant_id,
        engagement_id=engagement_id,
        limit=limit,
        offset=offset,
    )


@router.patch("/org/{engagement_id}")
async def update_org_scope(
    engagement_id: UUID,
    payload: UpdateOrgScopePayload,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Update scope on org-authorized consent for an engagement.

    Identifies affected participants and emits re-consent notification
    events. The expanded scope is not activated for processing until
    the notification workflow completes.
    """
    service = ConsentService(session)
    return await service.update_org_scope(engagement_id, payload.new_scope)
