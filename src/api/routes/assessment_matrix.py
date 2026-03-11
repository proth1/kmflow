"""Assessment Overlay Matrix API routes.

Provides endpoints for computing, retrieving, and exporting the
Assessment Overlay Matrix — a 2D scatter chart (Value x Ability-to-Execute)
with quadrant analysis for process area prioritization.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.services.assessment_matrix import AssessmentMatrixService
from src.core.audit import log_audit
from src.core.models import AuditAction, User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assessment-matrix"])


@router.get("/engagements/{engagement_id}/assessment-matrix")
async def get_assessment_matrix(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("simulation:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get the assessment overlay matrix for an engagement.

    Returns all process area entries with their Value and Ability-to-Execute
    scores, quadrant classification, and component breakdowns.
    """
    service = AssessmentMatrixService(session)
    entries = await service.get_matrix(engagement_id)

    # Compute quadrant summaries
    quadrant_counts: dict[str, int] = {}
    for entry in entries:
        q = entry["quadrant"]
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1

    return {
        "engagement_id": str(engagement_id),
        "entries": entries,
        "total": len(entries),
        "quadrant_summary": quadrant_counts,
    }


@router.post("/engagements/{engagement_id}/assessment-matrix/compute")
async def compute_assessment_matrix(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:create")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute (or recompute) the assessment overlay matrix.

    Analyzes process elements, maturity scores, compliance data, and
    simulation results to score each process area on Value and
    Ability-to-Execute axes.
    """
    service = AssessmentMatrixService(session)
    entries = await service.compute_matrix(engagement_id)

    await log_audit(
        session,
        engagement_id,
        AuditAction.SIMULATION_CREATED,
        f"Assessment matrix computed with {len(entries)} process areas",
        actor=str(user.id),
    )
    await session.commit()

    quadrant_counts: dict[str, int] = {}
    for entry in entries:
        q = entry["quadrant"]
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1

    return {
        "engagement_id": str(engagement_id),
        "entries": entries,
        "total": len(entries),
        "quadrant_summary": quadrant_counts,
    }


@router.post("/engagements/{engagement_id}/assessment-matrix/export")
async def export_assessment_matrix(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("simulation:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Export the assessment matrix as a structured report.

    Returns a JSON export with entries, quadrant analysis, and
    recommendations suitable for PDF generation or downstream reporting.
    """
    service = AssessmentMatrixService(session)
    entries = await service.get_matrix(engagement_id)

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment matrix data found. Run /compute first.",
        )

    # Build quadrant analysis
    quadrants: dict[str, list[dict[str, Any]]] = {
        "transform": [],
        "invest": [],
        "maintain": [],
        "deprioritize": [],
    }
    for entry in entries:
        quadrants[entry["quadrant"]].append(
            {
                "process_area": entry["process_area_name"],
                "value_score": entry["value_score"],
                "ability_to_execute": entry["ability_to_execute"],
            }
        )

    # Build recommendations
    recommendations = []
    if quadrants["transform"]:
        recommendations.append(
            {
                "priority": "high",
                "action": "Prioritize transformation",
                "areas": [e["process_area"] for e in quadrants["transform"]],
                "rationale": "High value with strong execution capability — maximize ROI.",
            }
        )
    if quadrants["invest"]:
        recommendations.append(
            {
                "priority": "medium",
                "action": "Invest in capability building",
                "areas": [e["process_area"] for e in quadrants["invest"]],
                "rationale": "High value but execution gaps — invest in maturity and evidence.",
            }
        )
    if quadrants["maintain"]:
        recommendations.append(
            {
                "priority": "low",
                "action": "Maintain current operations",
                "areas": [e["process_area"] for e in quadrants["maintain"]],
                "rationale": "Lower value but already capable — maintain without heavy investment.",
            }
        )
    if quadrants["deprioritize"]:
        recommendations.append(
            {
                "priority": "info",
                "action": "Deprioritize or defer",
                "areas": [e["process_area"] for e in quadrants["deprioritize"]],
                "rationale": "Low value and execution gaps — revisit in future assessment cycles.",
            }
        )

    await log_audit(
        session,
        engagement_id,
        AuditAction.REPORT_GENERATED,
        "Assessment matrix exported",
        actor=str(user.id),
    )
    await session.commit()

    return {
        "engagement_id": str(engagement_id),
        "entries": entries,
        "quadrant_analysis": quadrants,
        "recommendations": recommendations,
        "total": len(entries),
    }
