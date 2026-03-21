"""Data Processing Agreement (DPA) routes — GDPR Article 28 compliance.

Tracks DPAs between the consulting firm (processor) and client (controller)
for each engagement. Supports versioned DPA lifecycle: draft → active →
superseded/expired.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.dpa import (
    DpaCreate,
    DpaListResponse,
    DpaResponse,
    DpaUpdate,
)
from src.core.audit import log_audit
from src.core.models import AuditAction, User
from src.core.permissions import require_engagement_access, require_permission
from src.core.services.gdpr_service import GdprComplianceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements/{engagement_id}/dpa", tags=["dpa"])


@router.post("/", response_model=DpaResponse, status_code=status.HTTP_201_CREATED)
async def create_dpa(
    engagement_id: UUID,
    payload: DpaCreate,
    user: User = Depends(require_permission("engagement:update")),
    _access: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Create a new DPA in DRAFT status."""
    service = GdprComplianceService(session)
    dpa = await service.create_dpa(
        engagement_id=engagement_id,
        reference_number=payload.reference_number,
        version=payload.version,
        effective_date=payload.effective_date,
        controller_name=payload.controller_name,
        processor_name=payload.processor_name,
        data_categories=payload.data_categories,
        lawful_basis=payload.lawful_basis,
        created_by=user.id,
        expiry_date=payload.expiry_date,
        sub_processors=payload.sub_processors,
        retention_days_override=payload.retention_days_override,
        notes=payload.notes,
    )
    await log_audit(
        session,
        engagement_id,
        AuditAction.DPA_CREATED,
        details=json.dumps({"dpa_id": str(dpa.id), "reference_number": dpa.reference_number}),
        actor=user.email,
    )
    await session.commit()
    await session.refresh(dpa)
    return dpa


@router.get("/", response_model=DpaResponse)
async def get_active_dpa(
    engagement_id: UUID,
    user: User = Depends(require_permission("engagement:read")),
    _access: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Get the active DPA for an engagement."""
    service = GdprComplianceService(session)
    dpa = await service.get_active_dpa(engagement_id)
    if dpa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active DPA for engagement {engagement_id}",
        )
    return dpa


@router.get("/history", response_model=DpaListResponse)
async def list_dpa_history(
    engagement_id: UUID,
    limit: int = Query(default=20, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("engagement:read")),
    _access: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all DPA versions for an engagement."""
    service = GdprComplianceService(session)
    return await service.list_dpas(engagement_id, limit=limit, offset=offset)


@router.patch("/{dpa_id}", response_model=DpaResponse)
async def update_dpa(
    engagement_id: UUID,
    dpa_id: UUID,
    payload: DpaUpdate,
    user: User = Depends(require_permission("engagement:update")),
    _access: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Update a DPA (only draft or active status)."""
    service = GdprComplianceService(session)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    try:
        dpa = await service.update_dpa(engagement_id, dpa_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await log_audit(
        session,
        engagement_id,
        AuditAction.DPA_UPDATED,
        details=json.dumps({"dpa_id": str(dpa_id), "fields": list(updates.keys())}),
        actor=user.email,
    )
    await session.commit()
    await session.refresh(dpa)
    return dpa


@router.post("/{dpa_id}/activate", response_model=DpaResponse, status_code=status.HTTP_200_OK)
async def activate_dpa(
    engagement_id: UUID,
    dpa_id: UUID,
    user: User = Depends(require_permission("engagement:update")),
    _access: User = Depends(require_engagement_access),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Activate a DPA, superseding any previously active DPA."""
    service = GdprComplianceService(session)
    try:
        dpa = await service.activate_dpa(engagement_id, dpa_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await log_audit(
        session,
        engagement_id,
        AuditAction.DPA_ACTIVATED,
        details=json.dumps({"dpa_id": str(dpa_id), "reference_number": dpa.reference_number}),
        actor=user.email,
    )
    await session.commit()
    await session.refresh(dpa)
    return dpa
