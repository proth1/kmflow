"""Client portal routes (read-only, client_viewer role).

Provides a restricted view of engagement data for client stakeholders
with read-only access to process models, findings, and evidence status.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    Engagement,
    EvidenceGap,
    EvidenceItem,
    GapAnalysisResult,
    MonitoringAlert,
    ProcessModel,
    AlertStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])


# -- Schemas ------------------------------------------------------------------


class PortalOverview(BaseModel):
    engagement_id: str
    engagement_name: str
    client: str
    status: str
    evidence_count: int
    process_model_count: int
    open_alerts: int
    overall_confidence: float


class PortalFinding(BaseModel):
    id: str
    dimension: str
    gap_type: str
    severity: float
    recommendation: str | None = None


class PortalFindingsList(BaseModel):
    items: list[PortalFinding]
    total: int


class PortalEvidenceStatus(BaseModel):
    category: str
    count: int
    avg_quality: float


class PortalEvidenceSummary(BaseModel):
    total_items: int
    categories: list[PortalEvidenceStatus]


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


# -- Routes -------------------------------------------------------------------


@router.get("/{engagement_id}/overview", response_model=PortalOverview)
async def portal_overview(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get high-level overview for client portal."""
    result = await session.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")

    evidence_count = (await session.execute(
        select(func.count(EvidenceItem.id)).where(EvidenceItem.engagement_id == engagement_id)
    )).scalar() or 0

    model_count = (await session.execute(
        select(func.count(ProcessModel.id)).where(ProcessModel.engagement_id == engagement_id)
    )).scalar() or 0

    alert_count = (await session.execute(
        select(func.count(MonitoringAlert.id)).where(
            MonitoringAlert.engagement_id == engagement_id,
            MonitoringAlert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
        )
    )).scalar() or 0

    # Calculate overall confidence from process models
    confidence_result = await session.execute(
        select(func.avg(ProcessModel.confidence_score)).where(
            ProcessModel.engagement_id == engagement_id
        )
    )
    overall_confidence = confidence_result.scalar() or 0.0

    return {
        "engagement_id": str(engagement_id),
        "engagement_name": engagement.name,
        "client": engagement.client,
        "status": engagement.status.value if hasattr(engagement.status, 'value') else str(engagement.status),
        "evidence_count": evidence_count,
        "process_model_count": model_count,
        "open_alerts": alert_count,
        "overall_confidence": round(float(overall_confidence), 3),
    }


@router.get("/{engagement_id}/findings", response_model=PortalFindingsList)
async def portal_findings(
    engagement_id: UUID,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get gap analysis findings for client review."""
    result = await session.execute(
        select(GapAnalysisResult)
        .where(GapAnalysisResult.engagement_id == engagement_id)
        .order_by(GapAnalysisResult.severity.desc())
        .offset(offset)
        .limit(limit)
    )
    gaps = result.scalars().all()

    items = [
        {
            "id": str(g.id),
            "dimension": g.dimension.value if hasattr(g.dimension, 'value') else str(g.dimension),
            "gap_type": g.gap_type.value if hasattr(g.gap_type, 'value') else str(g.gap_type),
            "severity": g.severity,
            "recommendation": g.recommendation,
        }
        for g in gaps
    ]

    return {"items": items, "total": len(items)}


@router.get("/{engagement_id}/evidence-status", response_model=PortalEvidenceSummary)
async def portal_evidence_status(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get evidence status summary for client portal."""
    result = await session.execute(
        select(
            EvidenceItem.category,
            func.count(EvidenceItem.id).label("count"),
            func.avg(
                (EvidenceItem.completeness_score + EvidenceItem.reliability_score +
                 EvidenceItem.freshness_score + EvidenceItem.consistency_score) / 4.0
            ).label("avg_quality"),
        )
        .where(EvidenceItem.engagement_id == engagement_id)
        .group_by(EvidenceItem.category)
    )
    rows = result.all()

    categories = [
        {
            "category": row.category.value if hasattr(row.category, 'value') else str(row.category),
            "count": row.count,
            "avg_quality": round(float(row.avg_quality or 0), 3),
        }
        for row in rows
    ]

    total_items = sum(c["count"] for c in categories)

    return {"total_items": total_items, "categories": categories}


@router.get("/{engagement_id}/process", response_model=dict)
async def portal_process(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get process model data for the interactive explorer."""
    result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == engagement_id)
        .order_by(ProcessModel.created_at.desc())
        .limit(1)
    )
    model = result.scalar_one_or_none()
    if not model:
        return {"engagement_id": str(engagement_id), "model": None}

    return {
        "engagement_id": str(engagement_id),
        "model": {
            "id": str(model.id),
            "scope": model.scope,
            "confidence_score": model.confidence_score,
            "element_count": model.element_count,
            "bpmn_xml": model.bpmn_xml,
        },
    }
