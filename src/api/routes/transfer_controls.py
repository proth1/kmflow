"""Cross-border data transfer control API endpoints (Story #395).

Provides endpoints for evaluating transfers, managing TIAs,
recording SCCs, and querying transfer logs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import TransferDecision, User
from src.core.models.transfer import DataResidencyRestriction
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transfer-controls", tags=["transfer-controls"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EvaluateTransferRequest(BaseModel):
    """Request to evaluate a cross-border data transfer."""

    engagement_id: UUID
    connector_id: str = Field(..., min_length=1, max_length=255)
    data_residency: DataResidencyRestriction


class EvaluateTransferResponse(BaseModel):
    """Result of a transfer evaluation."""

    decision: TransferDecision
    reason: str
    destination: str | None = None
    connector_id: str
    tia_id: str | None = None
    scc_reference_id: str | None = None
    guidance: str | None = None


class CreateTIARequest(BaseModel):
    """Request to create a Transfer Impact Assessment."""

    engagement_id: UUID
    connector_id: str = Field(..., min_length=1, max_length=255)
    assessor: str = Field(..., min_length=1, max_length=255)


class TIAResponse(BaseModel):
    """Response schema for a TIA record."""

    id: UUID
    engagement_id: UUID
    connector_id: str
    destination_jurisdiction: str
    assessor: str
    status: str
    approved_at: datetime | None = None
    approved_by: str | None = None

    model_config = {"from_attributes": True}


class ApproveTIARequest(BaseModel):
    """Request to approve a Transfer Impact Assessment."""

    approved_by: str = Field(..., min_length=1, max_length=255)


class RecordSCCRequest(BaseModel):
    """Request to record Standard Contractual Clauses."""

    engagement_id: UUID
    connector_id: str = Field(..., min_length=1, max_length=255)
    scc_version: str = Field(..., min_length=1, max_length=50)
    reference_id: str = Field(..., min_length=1, max_length=255)
    executed_at: datetime


class SCCResponse(BaseModel):
    """Response schema for an SCC record."""

    id: UUID
    engagement_id: UUID
    connector_id: str
    scc_version: str
    reference_id: str
    executed_at: datetime

    model_config = {"from_attributes": True}


class TransferLogResponse(BaseModel):
    """Response schema for a transfer log entry."""

    id: UUID
    engagement_id: UUID
    connector_id: str
    destination_jurisdiction: str
    decision: str
    scc_reference_id: str | None = None
    tia_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/evaluate", response_model=EvaluateTransferResponse)
async def evaluate_transfer(
    body: EvaluateTransferRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("transfer:read")),
) -> Any:
    """Evaluate whether a cross-border data transfer is permitted.

    Checks residency restrictions, TIA status, and SCC records
    to determine if the transfer can proceed.
    """
    from src.api.services.transfer_control import TransferControlService

    service = TransferControlService(session)
    result = await service.evaluate_transfer(
        engagement_id=body.engagement_id,
        connector_id=body.connector_id,
        data_residency=body.data_residency,
    )
    return result


@router.post("/tia", response_model=TIAResponse, status_code=status.HTTP_201_CREATED)
async def create_tia(
    body: CreateTIARequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("transfer:write")),
) -> Any:
    """Create a Transfer Impact Assessment for a connector."""
    from src.api.services.transfer_control import TransferControlService

    service = TransferControlService(session)
    tia = await service.create_tia(
        engagement_id=body.engagement_id,
        connector_id=body.connector_id,
        assessor=body.assessor,
    )
    return tia


@router.post("/tia/{tia_id}/approve", response_model=TIAResponse)
async def approve_tia(
    tia_id: UUID,
    body: ApproveTIARequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("transfer:write")),
) -> Any:
    """Approve a pending Transfer Impact Assessment."""
    from src.api.services.transfer_control import TransferControlService

    service = TransferControlService(session)
    try:
        tia = await service.approve_tia(tia_id=tia_id, approved_by=body.approved_by)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return tia


@router.post("/scc", response_model=SCCResponse, status_code=status.HTTP_201_CREATED)
async def record_scc(
    body: RecordSCCRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("transfer:write")),
) -> Any:
    """Record Standard Contractual Clauses for a connector."""
    from src.api.services.transfer_control import TransferControlService

    service = TransferControlService(session)
    scc = await service.record_scc(
        engagement_id=body.engagement_id,
        connector_id=body.connector_id,
        scc_version=body.scc_version,
        reference_id=body.reference_id,
        executed_at=body.executed_at,
    )
    return scc


@router.get("/log", response_model=list[TransferLogResponse])
async def list_transfer_logs(
    engagement_id: UUID = Query(..., description="Filter by engagement"),
    connector_id: str | None = Query(None, description="Filter by connector"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("transfer:read")),
) -> Any:
    """List transfer log entries for an engagement."""
    from sqlalchemy import select

    from src.core.models import DataTransferLog

    query = select(DataTransferLog).where(DataTransferLog.engagement_id == engagement_id)
    if connector_id is not None:
        query = query.where(DataTransferLog.connector_id == connector_id)
    query = query.order_by(DataTransferLog.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    return result.scalars().all()
