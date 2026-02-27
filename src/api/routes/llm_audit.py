"""LLM Audit Trail API endpoints (Story #386).

Provides engagement-level LLM audit querying, hallucination flagging,
and suggestion disposition stats.
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
from src.core.models import User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["llm-audit"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FlagHallucinationRequest(BaseModel):
    """Request to flag an LLM suggestion as a hallucination."""

    reason: str = Field(..., min_length=1, max_length=2000)


class AuditEntryResponse(BaseModel):
    """LLM audit log entry response."""

    id: str
    scenario_id: str
    user_id: str | None = None
    prompt_tokens: int
    completion_tokens: int
    model_name: str
    evidence_ids: list | None = None
    error_message: str | None = None
    hallucination_flagged: bool
    hallucination_reason: str | None = None
    flagged_at: str | None = None
    flagged_by_user_id: str | None = None
    created_at: str


class PaginatedAuditResponse(BaseModel):
    """Paginated list of audit entries."""

    items: list[AuditEntryResponse]
    total: int
    limit: int
    offset: int


class AuditStatsResponse(BaseModel):
    """LLM audit statistics response."""

    total_entries: int
    total_suggestions: int
    accepted_count: int
    modified_count: int
    rejected_count: int
    hallucination_flagged_count: int
    acceptance_rate: float
    modification_rate: float
    rejection_rate: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/engagements/{engagement_id}/llm-audit",
    response_model=PaginatedAuditResponse,
)
async def list_llm_audit(
    engagement_id: UUID,
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> Any:
    """List LLM audit entries for an engagement with date range filter."""
    from src.api.services.llm_audit import LLMAuditService

    service = LLMAuditService(session)
    return await service.list_by_engagement(
        engagement_id=engagement_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/suggestions/{audit_log_id}/flag-hallucination",
    response_model=AuditEntryResponse,
)
async def flag_hallucination(
    audit_log_id: UUID,
    body: FlagHallucinationRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> Any:
    """Flag an LLM audit entry as containing a hallucination."""
    from src.api.services.llm_audit import LLMAuditService

    service = LLMAuditService(session)
    try:
        return await service.flag_hallucination(
            audit_log_id=audit_log_id,
            reason=body.reason,
            flagged_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/engagements/{engagement_id}/llm-audit/stats",
    response_model=AuditStatsResponse,
)
async def get_llm_audit_stats(
    engagement_id: UUID,
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
) -> Any:
    """Get acceptance/modification/rejection rates for LLM suggestions."""
    from src.api.services.llm_audit import LLMAuditService

    service = LLMAuditService(session)
    return await service.get_stats(
        engagement_id=engagement_id,
        from_date=from_date,
        to_date=to_date,
    )
