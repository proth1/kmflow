"""Scenario comparison API route (Story #383).

Provides the side-by-side comparison endpoint for 2-5 scenarios.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.scenario_comparison import (
    MAX_SCENARIOS,
    MIN_SCENARIOS,
    ScenarioComparisonService,
)
from src.core.models import User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenario-comparison"])


@router.get("/compare")
async def compare_scenarios(
    ids: str = Query(..., description="Comma-separated scenario IDs (2-5)"),
    engagement_id: UUID = Query(..., description="Engagement ID for access control"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compare 2-5 scenarios side-by-side across key metrics.

    Returns comparison data with cycle_time_delta_pct, fte_delta,
    avg_confidence, governance_coverage_pct, and compliance_flags.
    Best/worst values per metric are flagged.

    Returns 409 if any scenario has no completed simulation results.
    """
    # Parse and validate scenario IDs
    raw_ids = [s.strip() for s in ids.split(",") if s.strip()]

    if len(raw_ids) < MIN_SCENARIOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At least {MIN_SCENARIOS} scenario IDs required",
        )
    if len(raw_ids) > MAX_SCENARIOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {MAX_SCENARIOS} scenario IDs allowed",
        )

    try:
        scenario_ids = [UUID(sid) for sid in raw_ids]
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid UUID in scenario IDs",
        ) from err

    service = ScenarioComparisonService(session)
    try:
        return await service.compare_scenarios(scenario_ids, engagement_id)
    except ValueError as exc:
        # Scenarios not found or simulation incomplete
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
