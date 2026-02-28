"""Evidence Confidence Overlay routes (Story #385).

Per-scenario evidence coverage analysis that surfaces which modifications
affect Bright, Dim, or Dark process areas. Dark-area modifications generate
warnings about insufficient evidence backing.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.evidence_coverage import EvidenceCoverageService
from src.core.models import User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scenarios", tags=["evidence-coverage"])

MAX_COMPARE_SCENARIOS = 10


# NOTE: /compare/evidence-coverage must be registered BEFORE /{scenario_id}/...
# so that "compare" is not captured as a UUID path parameter.
@router.get("/compare/evidence-coverage")
async def compare_evidence_coverage(
    scenario_ids: str = Query(
        ...,
        description="Comma-separated scenario UUIDs to compare (max 10)",
    ),
    engagement_id: UUID = Query(..., description="Engagement owning the scenarios"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compare multiple scenarios by evidence coverage risk score.

    Returns scenarios sorted by risk_score descending (lower risk first).
    """
    try:
        parsed_ids = [UUID(sid.strip()) for sid in scenario_ids.split(",")]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scenario UUID format: {exc}",
        ) from exc

    if len(parsed_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least 2 scenario IDs are required for comparison",
        )

    if len(parsed_ids) > MAX_COMPARE_SCENARIOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {MAX_COMPARE_SCENARIOS} scenarios can be compared at once",
        )

    service = EvidenceCoverageService(session)
    try:
        results = await service.compare_scenarios(parsed_ids, engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"scenarios": results}


@router.get("/{scenario_id}/evidence-coverage")
async def get_evidence_coverage(
    scenario_id: UUID,
    engagement_id: UUID = Query(..., description="Engagement owning this scenario"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get per-element evidence confidence overlay for a scenario.

    Returns brightness classification for each modified element, warning flags
    for Dark-area modifications, and a coverage summary with risk score.
    """
    service = EvidenceCoverageService(session)
    try:
        return await service.get_scenario_coverage(scenario_id, engagement_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
