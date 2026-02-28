"""Sensitivity analysis routes for financial estimates (Story #364).

OAT sensitivity, tornado chart data, and P10/P50/P90 percentile estimates.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.financial.sensitivity import (
    AssumptionInput,
    compute_percentile_estimates,
    compute_sensitivity,
    compute_tornado_chart,
)
from src.core.models import FinancialAssumption, User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["financial-analysis"])


async def _load_assumptions(session: AsyncSession, engagement_id: UUID) -> list[AssumptionInput]:
    """Load financial assumptions for an engagement and convert to AssumptionInput."""
    result = await session.execute(
        select(FinancialAssumption)
        .where(FinancialAssumption.engagement_id == engagement_id)
        .order_by(FinancialAssumption.name)
    )
    assumptions = list(result.scalars().all())
    if not assumptions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No financial assumptions found for this engagement",
        )
    return [
        AssumptionInput(
            name=a.name,
            value=a.value,
            confidence=a.confidence,
            confidence_range=a.confidence_range or 0.0,
        )
        for a in assumptions
    ]


@router.post("/engagements/{engagement_id}/financial-analysis/sensitivity")
async def run_sensitivity_analysis(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Run OAT sensitivity analysis over engagement financial assumptions.

    Returns assumptions ranked by impact on total cost, with impact amounts.
    """
    inputs = await _load_assumptions(session, engagement_id)
    return compute_sensitivity(inputs)


@router.get("/engagements/{engagement_id}/financial-analysis/tornado")
async def get_tornado_chart(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get tornado chart data for financial assumptions.

    Returns assumptions ordered by descending swing magnitude,
    suitable for rendering a horizontal tornado chart.
    """
    inputs = await _load_assumptions(session, engagement_id)
    entries = compute_tornado_chart(inputs)
    return {
        "items": [e.to_dict() for e in entries],
        "total": len(entries),
    }


@router.post("/engagements/{engagement_id}/financial-analysis/percentiles")
async def compute_percentiles(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute confidence-weighted P10/P50/P90 cost estimates.

    Lower-confidence assumptions contribute wider spread to the percentile range.
    """
    inputs = await _load_assumptions(session, engagement_id)
    estimate = compute_percentile_estimates(inputs)
    return estimate.to_dict()
