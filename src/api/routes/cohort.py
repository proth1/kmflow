"""Cohort suppression API endpoints (Story #391).

Provides cohort size checking, export validation, and engagement-level
configuration for minimum cohort size thresholds.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User, UserRole
from src.core.permissions import require_permission, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cohort", tags=["cohort"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CohortCheckRequest(BaseModel):
    """Request to check cohort suppression status."""

    engagement_id: UUID
    cohort_size: int = Field(..., ge=0)
    context: str | None = None


class CohortCheckResponse(BaseModel):
    """Response from cohort suppression check."""

    suppressed: bool
    reason: str | None = None
    cohort_size_observed: int
    cohort_minimum: int
    data: Any | None = None


class ExportCheckRequest(BaseModel):
    """Request to check whether an export is allowed."""

    engagement_id: UUID
    cohort_size: int = Field(..., ge=0)


class ExportCheckResponse(BaseModel):
    """Response for export permission check."""

    allowed: bool
    cohort_size: int
    cohort_minimum: int


class ConfigureRequest(BaseModel):
    """Request to configure engagement cohort settings."""

    minimum_cohort_size: int = Field(..., ge=2, le=100)


class CohortConfigResponse(BaseModel):
    """Response with cohort configuration."""

    engagement_id: str
    cohort_minimum_size: int
    is_default: bool = False
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/check", response_model=CohortCheckResponse)
async def check_cohort(
    body: CohortCheckRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> Any:
    """Check whether a cohort meets the minimum size threshold.

    Returns suppressed=true if the group is below the minimum,
    with HTTP 200 (suppression is a valid analytical outcome).
    """
    from src.security.cohort.suppression import CohortSuppressionService

    service = CohortSuppressionService(session)
    return await service.check_cohort(
        engagement_id=body.engagement_id,
        cohort_size=body.cohort_size,
        context=body.context,
    )


@router.post("/export-check", response_model=ExportCheckResponse)
async def check_export(
    body: ExportCheckRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> Any:
    """Check whether an export is allowed based on cohort size.

    Returns 422 if the cohort is below the minimum threshold.
    """
    from src.security.cohort.suppression import CohortExportBlockedError, CohortSuppressionService

    service = CohortSuppressionService(session)
    try:
        return await service.check_export(
            engagement_id=body.engagement_id,
            cohort_size=body.cohort_size,
            requester=user.email,
        )
    except CohortExportBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.patch(
    "/engagements/{engagement_id}/settings",
    response_model=CohortConfigResponse,
)
async def configure_engagement(
    engagement_id: UUID,
    body: ConfigureRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role(UserRole.ENGAGEMENT_LEAD)),
) -> Any:
    """Configure the minimum cohort size for an engagement.

    Only ENGAGEMENT_LEAD or higher can modify cohort settings.
    """
    from src.security.cohort.suppression import CohortSuppressionService

    service = CohortSuppressionService(session)
    try:
        return await service.configure_engagement(
            engagement_id=engagement_id,
            minimum_cohort_size=body.minimum_cohort_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/engagements/{engagement_id}/settings",
    response_model=CohortConfigResponse,
)
async def get_engagement_config(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> Any:
    """Get the cohort suppression configuration for an engagement."""
    from src.security.cohort.suppression import CohortSuppressionService

    service = CohortSuppressionService(session)
    return await service.get_engagement_config(
        engagement_id=engagement_id,
    )
