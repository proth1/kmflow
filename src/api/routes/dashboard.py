"""Dashboard API routes.

Provides aggregated metrics and analytics for engagement dashboards,
including evidence coverage, confidence distribution, and recent activity.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    AuditLog,
    Engagement,
    EvidenceGap,
    EvidenceItem,
    ProcessElement,
    ProcessModel,
    ProcessModelStatus,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemStatus,
    User,
)
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# -- Response Schemas ----------------------------------------------------------


class GapCountBySeverity(BaseModel):
    """Gap counts grouped by severity."""

    high: int = 0
    medium: int = 0
    low: int = 0


class RecentActivityEntry(BaseModel):
    """A recent audit log entry."""

    id: str
    action: str
    actor: str
    details: str | None = None
    created_at: Any | None = None


class DashboardResponse(BaseModel):
    """Aggregated engagement dashboard data."""

    engagement_id: str
    engagement_name: str
    evidence_coverage_pct: float = Field(..., description="Overall evidence coverage percentage (0-100)")
    overall_confidence: float = Field(..., description="Overall confidence score from latest POV (0.0-1.0)")
    gap_counts: GapCountBySeverity
    evidence_item_count: int
    process_model_count: int
    recent_activity: list[RecentActivityEntry]


class CategoryCoverage(BaseModel):
    """Evidence coverage for a single category."""

    category: str
    requested_count: int
    received_count: int
    coverage_pct: float = Field(..., description="Coverage percentage for this category (0-100)")
    below_threshold: bool = Field(default=False, description="True if coverage is below 50%")


class EvidenceCoverageResponse(BaseModel):
    """Detailed evidence coverage breakdown."""

    engagement_id: str
    overall_coverage_pct: float
    categories: list[CategoryCoverage]


class ConfidenceBucket(BaseModel):
    """Element count for a confidence level."""

    level: str
    min_score: float
    max_score: float
    count: int


class WeakElement(BaseModel):
    """A process element with low confidence."""

    id: str
    name: str
    element_type: str
    confidence_score: float


class ConfidenceDistributionResponse(BaseModel):
    """Confidence distribution across process elements."""

    engagement_id: str
    model_id: str | None = None
    overall_confidence: float
    distribution: list[ConfidenceBucket]
    weakest_elements: list[WeakElement]


# -- Helpers ------------------------------------------------------------------

CONFIDENCE_LEVELS = [
    ("VERY_HIGH", 0.90, 1.00),
    ("HIGH", 0.75, 0.89),
    ("MEDIUM", 0.50, 0.74),
    ("LOW", 0.25, 0.49),
    ("VERY_LOW", 0.00, 0.24),
]


def _classify_confidence(score: float) -> str:
    """Classify a confidence score into a named level."""
    if score >= 0.90:
        return "VERY_HIGH"
    elif score >= 0.75:
        return "HIGH"
    elif score >= 0.50:
        return "MEDIUM"
    elif score >= 0.25:
        return "LOW"
    return "VERY_LOW"


# -- Routes -------------------------------------------------------------------


@router.get("/{engagement_id}", response_model=DashboardResponse)
async def get_dashboard(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get aggregated dashboard data for an engagement.

    Returns evidence coverage, confidence scores, gap counts,
    and recent activity.
    """
    eng_uuid = engagement_id

    # Verify engagement exists
    eng_result = await session.execute(select(Engagement).where(Engagement.id == eng_uuid))
    engagement = eng_result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Evidence item count
    ev_count_result = await session.execute(
        select(func.count()).select_from(EvidenceItem).where(EvidenceItem.engagement_id == eng_uuid)
    )
    evidence_item_count = ev_count_result.scalar() or 0

    # Process model count
    pm_count_result = await session.execute(
        select(func.count()).select_from(ProcessModel).where(ProcessModel.engagement_id == eng_uuid)
    )
    process_model_count = pm_count_result.scalar() or 0

    # Overall confidence from latest completed POV
    latest_model_result = await session.execute(
        select(ProcessModel)
        .where(
            ProcessModel.engagement_id == eng_uuid,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.created_at.desc())
        .limit(1)
    )
    latest_model = latest_model_result.scalar_one_or_none()
    overall_confidence = latest_model.confidence_score if latest_model else 0.0

    # Evidence coverage: count requested items vs received per category
    shelf_items_result = await session.execute(
        select(
            ShelfDataRequestItem.category,
            func.count().label("total"),
            func.count().filter(ShelfDataRequestItem.status == ShelfRequestItemStatus.RECEIVED).label("received"),
        )
        .join(ShelfDataRequest)
        .where(ShelfDataRequest.engagement_id == eng_uuid)
        .group_by(ShelfDataRequestItem.category)
    )
    shelf_rows = shelf_items_result.all()

    total_requested = sum(row.total for row in shelf_rows)
    total_received = sum(row.received for row in shelf_rows)
    evidence_coverage_pct = round(total_received / total_requested * 100, 1) if total_requested > 0 else 0.0

    # Gap counts by severity (from latest model)
    gap_counts = GapCountBySeverity()
    if latest_model:
        gap_result = await session.execute(
            select(EvidenceGap.severity, func.count().label("cnt"))
            .where(EvidenceGap.model_id == latest_model.id)
            .group_by(EvidenceGap.severity)
        )
        for row in gap_result.all():
            severity_str = str(row.severity).lower()
            if severity_str == "high":
                gap_counts.high = row.cnt
            elif severity_str == "medium":
                gap_counts.medium = row.cnt
            elif severity_str == "low":
                gap_counts.low = row.cnt

    # Recent activity (last 10 audit entries)
    audit_result = await session.execute(
        select(AuditLog).where(AuditLog.engagement_id == eng_uuid).order_by(AuditLog.created_at.desc()).limit(10)
    )
    audit_logs = list(audit_result.scalars().all())

    recent_activity = [
        RecentActivityEntry(
            id=str(log.id),
            action=str(log.action),
            actor=log.actor,
            details=log.details,
            created_at=log.created_at,
        )
        for log in audit_logs
    ]

    return {
        "engagement_id": str(eng_uuid),
        "engagement_name": engagement.name,
        "evidence_coverage_pct": evidence_coverage_pct,
        "overall_confidence": overall_confidence,
        "gap_counts": gap_counts,
        "evidence_item_count": evidence_item_count,
        "process_model_count": process_model_count,
        "recent_activity": recent_activity,
    }


@router.get(
    "/{engagement_id}/evidence-coverage",
    response_model=EvidenceCoverageResponse,
)
async def get_evidence_coverage(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get detailed evidence coverage by category.

    Compares shelf data request items (requested) vs received items
    per evidence category.
    """
    eng_uuid = engagement_id

    # Verify engagement exists
    eng_result = await session.execute(select(Engagement.id).where(Engagement.id == eng_uuid))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Per-category breakdown from shelf data request items
    shelf_items_result = await session.execute(
        select(
            ShelfDataRequestItem.category,
            func.count().label("total"),
            func.count().filter(ShelfDataRequestItem.status == ShelfRequestItemStatus.RECEIVED).label("received"),
        )
        .join(ShelfDataRequest)
        .where(ShelfDataRequest.engagement_id == eng_uuid)
        .group_by(ShelfDataRequestItem.category)
    )
    shelf_rows = shelf_items_result.all()

    categories = []
    total_requested = 0
    total_received = 0

    for row in shelf_rows:
        coverage = round(row.received / row.total * 100, 1) if row.total > 0 else 0.0
        categories.append(
            CategoryCoverage(
                category=str(row.category),
                requested_count=row.total,
                received_count=row.received,
                coverage_pct=coverage,
                below_threshold=coverage < 50.0,
            )
        )
        total_requested += row.total
        total_received += row.received

    overall = round(total_received / total_requested * 100, 1) if total_requested > 0 else 0.0

    return {
        "engagement_id": str(eng_uuid),
        "overall_coverage_pct": overall,
        "categories": categories,
    }


@router.get(
    "/{engagement_id}/confidence-distribution",
    response_model=ConfidenceDistributionResponse,
)
async def get_confidence_distribution(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get confidence distribution across process elements.

    Uses the latest completed process model for the engagement
    and buckets elements by confidence level.
    """
    eng_uuid = engagement_id

    # Verify engagement exists
    eng_result = await session.execute(select(Engagement.id).where(Engagement.id == eng_uuid))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Get latest completed model
    latest_model_result = await session.execute(
        select(ProcessModel)
        .where(
            ProcessModel.engagement_id == eng_uuid,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.created_at.desc())
        .limit(1)
    )
    latest_model = latest_model_result.scalar_one_or_none()

    if not latest_model:
        # No completed model yet -- return empty distribution
        return {
            "engagement_id": str(eng_uuid),
            "model_id": None,
            "overall_confidence": 0.0,
            "distribution": [
                ConfidenceBucket(level=name, min_score=lo, max_score=hi, count=0) for name, lo, hi in CONFIDENCE_LEVELS
            ],
            "weakest_elements": [],
        }

    # Get all elements for this model
    elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == latest_model.id))
    elements = list(elements_result.scalars().all())

    # Bucket by confidence level
    buckets: dict[str, int] = {name: 0 for name, _, _ in CONFIDENCE_LEVELS}
    for elem in elements:
        level = _classify_confidence(elem.confidence_score)
        buckets[level] += 1

    distribution = [
        ConfidenceBucket(level=name, min_score=lo, max_score=hi, count=buckets[name])
        for name, lo, hi in CONFIDENCE_LEVELS
    ]

    # Weakest elements (bottom 5 by confidence)
    sorted_elements = sorted(elements, key=lambda e: e.confidence_score)
    weakest = [
        WeakElement(
            id=str(e.id),
            name=e.name,
            element_type=str(e.element_type),
            confidence_score=e.confidence_score,
        )
        for e in sorted_elements[:5]
    ]

    return {
        "engagement_id": str(eng_uuid),
        "model_id": str(latest_model.id),
        "overall_confidence": latest_model.confidence_score,
        "distribution": distribution,
        "weakest_elements": weakest,
    }
