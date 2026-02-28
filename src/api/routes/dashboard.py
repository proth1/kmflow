"""Dashboard API routes.

Provides aggregated metrics and analytics for engagement dashboards,
including evidence coverage, confidence distribution, and recent activity.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    AuditLog,
    ConflictObject,
    DarkRoomSnapshot,
    Engagement,
    EngagementMember,
    EvidenceGap,
    EvidenceItem,
    GapAnalysisResult,
    ProcessElement,
    ProcessModel,
    ProcessModelStatus,
    ResolutionStatus,
    SeedTerm,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemStatus,
    TOMDimension,
    User,
    UserRole,
    ValidationDecision,
)
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Simple in-memory TTL cache for dashboard queries.
# Dashboard data is aggregated and relatively expensive to recompute;
# 30-second staleness is acceptable for monitoring use cases.
_DASHBOARD_CACHE_TTL = 30  # seconds
_dashboard_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    """Return cached value if present and not expired, else None."""
    entry = _dashboard_cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _DASHBOARD_CACHE_TTL:
        del _dashboard_cache[key]
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _dashboard_cache[key] = (time.monotonic(), value)


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

    cache_key = f"dashboard:{eng_uuid}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

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

    result = {
        "engagement_id": str(eng_uuid),
        "engagement_name": engagement.name,
        "evidence_coverage_pct": evidence_coverage_pct,
        "overall_confidence": overall_confidence,
        "gap_counts": gap_counts,
        "evidence_item_count": evidence_item_count,
        "process_model_count": process_model_count,
        "recent_activity": recent_activity,
    }
    _cache_set(cache_key, result)
    return result


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

    cache_key = f"evidence_coverage:{eng_uuid}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

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

    result = {
        "engagement_id": str(eng_uuid),
        "overall_coverage_pct": overall,
        "categories": categories,
    }
    _cache_set(cache_key, result)
    return result


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

    cache_key = f"confidence_distribution:{eng_uuid}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

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
        empty_result = {
            "engagement_id": str(eng_uuid),
            "model_id": None,
            "overall_confidence": 0.0,
            "distribution": [
                ConfidenceBucket(level=name, min_score=lo, max_score=hi, count=0) for name, lo, hi in CONFIDENCE_LEVELS
            ],
            "weakest_elements": [],
        }
        _cache_set(cache_key, empty_result)
        return empty_result

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

    result = {
        "engagement_id": str(eng_uuid),
        "model_id": str(latest_model.id),
        "overall_confidence": latest_model.confidence_score,
        "distribution": distribution,
        "weakest_elements": weakest,
    }
    _cache_set(cache_key, result)
    return result


# -- Persona Dashboard Schemas ------------------------------------------------

ENGAGEMENT_LEAD_ROLES = {"engagement_lead", "platform_admin"}
ANALYST_ROLES = {"analyst", "process_analyst", "platform_admin"}
SME_ROLES = {"sme", "subject_matter_expert", "platform_admin"}
CLIENT_ROLES = {"client", "client_stakeholder", "platform_admin"}


class BrightnessDistribution(BaseModel):
    """Brightness distribution across process elements."""

    bright_pct: float = Field(0.0, description="Percentage of BRIGHT elements")
    dim_pct: float = Field(0.0, description="Percentage of DIM elements")
    dark_pct: float = Field(0.0, description="Percentage of DARK elements")
    total_elements: int = 0


class TOMAlignmentEntry(BaseModel):
    """TOM alignment score for a single dimension."""

    dimension: str
    alignment_pct: float = Field(..., description="Alignment percentage (0-100)")


class EngagementLeadDashboard(BaseModel):
    """Full KPI dashboard for Engagement Lead persona."""

    engagement_id: str
    evidence_coverage_pct: float
    overall_confidence: float
    brightness_distribution: BrightnessDistribution
    tom_alignment: list[TOMAlignmentEntry]
    gap_counts: GapCountBySeverity
    seed_list_coverage_pct: float
    dark_room_shrink_rate: float


class ProcessingStatusCounts(BaseModel):
    """Evidence processing status counts."""

    pending: int = 0
    validated: int = 0
    active: int = 0
    expired: int = 0
    archived: int = 0


class ConflictQueueItem(BaseModel):
    """A conflict object in the resolution queue."""

    id: str
    mismatch_type: str
    severity: float
    resolution_status: str
    created_at: Any | None = None


class ProcessAnalystDashboard(BaseModel):
    """Dashboard for Process Analyst persona."""

    engagement_id: str
    processing_status: ProcessingStatusCounts
    relationship_mapping_pct: float
    conflict_queue: list[ConflictQueueItem]
    total_conflicts: int
    unresolved_conflicts: int


class DecisionHistoryItem(BaseModel):
    """A validation decision in SME history."""

    id: str
    decision: str
    created_at: Any | None = None


class SmeDashboard(BaseModel):
    """Dashboard for SME persona."""

    engagement_id: str
    pending_review_count: int
    total_annotation_count: int
    confidence_impact: float
    decision_history: list[DecisionHistoryItem]


class GapFindingSummary(BaseModel):
    """Gap finding for client view (no internal scores)."""

    id: str
    gap_type: str
    dimension: str
    recommendation: str | None = None


class ClientStakeholderDashboard(BaseModel):
    """Read-only dashboard for Client Stakeholder persona."""

    engagement_id: str
    overall_confidence: float
    brightness_distribution: BrightnessDistribution
    gap_findings: list[GapFindingSummary]
    total_recommendations: int


# -- Persona Helpers ----------------------------------------------------------


async def _get_user_engagement_role(
    engagement_id: UUID,
    user: User,
    session: AsyncSession,
) -> str:
    """Get user's role on an engagement. Raises 403 if not a member."""
    if user.role == UserRole.PLATFORM_ADMIN:
        return "platform_admin"

    result = await session.execute(
        select(EngagementMember.role_in_engagement).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.id,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this engagement",
        )
    return role


async def _get_brightness_distribution(
    engagement_id: UUID,
    session: AsyncSession,
) -> BrightnessDistribution:
    """Compute brightness distribution for the latest completed model."""
    model_result = await session.execute(
        select(ProcessModel.id)
        .where(
            ProcessModel.engagement_id == engagement_id,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.created_at.desc())
        .limit(1)
    )
    model_id = model_result.scalar_one_or_none()
    if model_id is None:
        return BrightnessDistribution()

    elements_result = await session.execute(
        select(
            ProcessElement.brightness_classification,
            func.count().label("cnt"),
        )
        .where(ProcessElement.model_id == model_id)
        .group_by(ProcessElement.brightness_classification)
    )
    rows = elements_result.all()
    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        key = str(row.brightness_classification).lower() if row.brightness_classification else "unknown"
        counts[key] = row.cnt
        total += row.cnt

    if total == 0:
        return BrightnessDistribution()

    return BrightnessDistribution(
        bright_pct=round(counts.get("bright", 0) / total * 100, 1),
        dim_pct=round(counts.get("dim", 0) / total * 100, 1),
        dark_pct=round(counts.get("dark", 0) / total * 100, 1),
        total_elements=total,
    )


# -- Persona Dashboard Routes -------------------------------------------------


@router.get(
    "/{engagement_id}/engagement-lead",
    response_model=EngagementLeadDashboard,
)
async def get_engagement_lead_dashboard(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Engagement Lead dashboard with full KPI suite."""
    role = await _get_user_engagement_role(engagement_id, user, session)
    if role not in ENGAGEMENT_LEAD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Engagement Lead role required",
        )

    eng_uuid = engagement_id

    # Evidence coverage
    shelf_result = await session.execute(
        select(
            func.count().label("total"),
            func.count()
            .filter(ShelfDataRequestItem.status == ShelfRequestItemStatus.RECEIVED)
            .label("received"),
        )
        .join(ShelfDataRequest)
        .where(ShelfDataRequest.engagement_id == eng_uuid)
    )
    shelf_row = shelf_result.one()
    evidence_coverage_pct = (
        round(shelf_row.received / shelf_row.total * 100, 1) if shelf_row.total > 0 else 0.0
    )

    # Overall confidence from latest completed model
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

    # Brightness distribution
    brightness = await _get_brightness_distribution(eng_uuid, session)

    # TOM alignment per dimension (1.0 - avg_severity)
    gaps_result = await session.execute(
        select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == eng_uuid)
    )
    gaps = list(gaps_result.scalars().all())

    dim_severities: dict[str, list[float]] = {dim.value: [] for dim in TOMDimension}
    for gap in gaps:
        dim_key = str(gap.dimension)
        if dim_key in dim_severities:
            dim_severities[dim_key].append(gap.severity)

    tom_alignment = []
    for dim in TOMDimension:
        sev_values = dim_severities[dim.value]
        avg_sev = sum(sev_values) / len(sev_values) if sev_values else 0.0
        tom_alignment.append(
            TOMAlignmentEntry(
                dimension=dim.value,
                alignment_pct=round((1.0 - avg_sev) * 100, 1),
            )
        )

    # Gap counts by severity
    gap_counts = GapCountBySeverity()
    if latest_model:
        gap_sev_result = await session.execute(
            select(EvidenceGap.severity, func.count().label("cnt"))
            .where(EvidenceGap.model_id == latest_model.id)
            .group_by(EvidenceGap.severity)
        )
        for row in gap_sev_result.all():
            sev = str(row.severity).lower()
            if sev == "high":
                gap_counts.high = row.cnt
            elif sev == "medium":
                gap_counts.medium = row.cnt
            elif sev == "low":
                gap_counts.low = row.cnt

    # Seed list coverage (active terms / total terms)
    seed_result = await session.execute(
        select(
            func.count().label("total"),
            func.count().filter(SeedTerm.status == "active").label("active"),
        ).where(SeedTerm.engagement_id == eng_uuid)
    )
    seed_row = seed_result.one()
    seed_list_coverage_pct = (
        round(seed_row.active / seed_row.total * 100, 1) if seed_row.total > 0 else 0.0
    )

    # Dark room shrink rate (compare last two snapshots)
    snapshots_result = await session.execute(
        select(DarkRoomSnapshot)
        .where(DarkRoomSnapshot.engagement_id == eng_uuid)
        .order_by(DarkRoomSnapshot.version_number.desc())
        .limit(2)
    )
    snapshots = list(snapshots_result.scalars().all())
    dark_room_shrink_rate = 0.0
    if len(snapshots) == 2:
        prev_dark = snapshots[1].dark_count
        curr_dark = snapshots[0].dark_count
        if prev_dark > 0:
            dark_room_shrink_rate = round((prev_dark - curr_dark) / prev_dark * 100, 1)

    return {
        "engagement_id": str(eng_uuid),
        "evidence_coverage_pct": evidence_coverage_pct,
        "overall_confidence": overall_confidence,
        "brightness_distribution": brightness,
        "tom_alignment": tom_alignment,
        "gap_counts": gap_counts,
        "seed_list_coverage_pct": seed_list_coverage_pct,
        "dark_room_shrink_rate": dark_room_shrink_rate,
    }


@router.get(
    "/{engagement_id}/analyst",
    response_model=ProcessAnalystDashboard,
)
async def get_analyst_dashboard(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Process Analyst dashboard with processing status and conflict queue."""
    role = await _get_user_engagement_role(engagement_id, user, session)
    if role not in ANALYST_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Process Analyst role required",
        )

    eng_uuid = engagement_id

    # Evidence processing status by validation_status
    status_result = await session.execute(
        select(
            EvidenceItem.validation_status,
            func.count().label("cnt"),
        )
        .where(EvidenceItem.engagement_id == eng_uuid)
        .group_by(EvidenceItem.validation_status)
    )
    processing = ProcessingStatusCounts()
    for row in status_result.all():
        vs = str(row.validation_status).lower()
        if vs == "pending":
            processing.pending = row.cnt
        elif vs == "validated":
            processing.validated = row.cnt
        elif vs == "active":
            processing.active = row.cnt
        elif vs == "expired":
            processing.expired = row.cnt
        elif vs == "archived":
            processing.archived = row.cnt

    # Relationship mapping progress (% elements with at least one evidence link)
    latest_model_result = await session.execute(
        select(ProcessModel.id)
        .where(
            ProcessModel.engagement_id == eng_uuid,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.created_at.desc())
        .limit(1)
    )
    model_id = latest_model_result.scalar_one_or_none()
    relationship_mapping_pct = 0.0
    if model_id:
        total_elem_result = await session.execute(
            select(func.count()).select_from(ProcessElement).where(ProcessElement.model_id == model_id)
        )
        total_elements = total_elem_result.scalar() or 0
        if total_elements > 0:
            mapped_result = await session.execute(
                select(func.count())
                .select_from(ProcessElement)
                .where(
                    ProcessElement.model_id == model_id,
                    ProcessElement.evidence_count > 0,
                )
            )
            mapped_elements = mapped_result.scalar() or 0
            relationship_mapping_pct = round(mapped_elements / total_elements * 100, 1)

    # Conflict resolution queue (unresolved, sorted by severity desc)
    conflict_result = await session.execute(
        select(ConflictObject)
        .where(
            ConflictObject.engagement_id == eng_uuid,
            ConflictObject.resolution_status == ResolutionStatus.UNRESOLVED,
        )
        .order_by(ConflictObject.severity.desc())
        .limit(50)
    )
    unresolved_conflicts_list = list(conflict_result.scalars().all())

    conflict_queue = [
        ConflictQueueItem(
            id=str(c.id),
            mismatch_type=str(c.mismatch_type),
            severity=c.severity,
            resolution_status=str(c.resolution_status),
            created_at=c.created_at,
        )
        for c in unresolved_conflicts_list
    ]

    # Total conflicts count
    total_count_result = await session.execute(
        select(func.count()).select_from(ConflictObject).where(ConflictObject.engagement_id == eng_uuid)
    )
    total_conflicts = total_count_result.scalar() or 0
    unresolved_conflicts = len(unresolved_conflicts_list)

    return {
        "engagement_id": str(eng_uuid),
        "processing_status": processing,
        "relationship_mapping_pct": relationship_mapping_pct,
        "conflict_queue": conflict_queue,
        "total_conflicts": total_conflicts,
        "unresolved_conflicts": unresolved_conflicts,
    }


@router.get(
    "/{engagement_id}/sme",
    response_model=SmeDashboard,
)
async def get_sme_dashboard(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """SME dashboard with review queue and annotation stats."""
    role = await _get_user_engagement_role(engagement_id, user, session)
    if role not in SME_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SME role required",
        )

    eng_uuid = engagement_id
    user_id = user.id

    # Total annotations (all decisions by this user for this engagement)
    total_result = await session.execute(
        select(func.count())
        .select_from(ValidationDecision)
        .where(
            ValidationDecision.engagement_id == eng_uuid,
            ValidationDecision.reviewer_id == user_id,
        )
    )
    total_annotation_count = total_result.scalar() or 0

    # Pending review count: DEFER actions are treated as pending re-review
    defer_result = await session.execute(
        select(func.count())
        .select_from(ValidationDecision)
        .where(
            ValidationDecision.engagement_id == eng_uuid,
            ValidationDecision.reviewer_id == user_id,
            ValidationDecision.action == "DEFER",
        )
    )
    pending_review_count = defer_result.scalar() or 0

    # Confidence impact: ratio of CONFIRM decisions to total
    confirm_result = await session.execute(
        select(func.count())
        .select_from(ValidationDecision)
        .where(
            ValidationDecision.engagement_id == eng_uuid,
            ValidationDecision.reviewer_id == user_id,
            ValidationDecision.action == "CONFIRM",
        )
    )
    confirm_count = confirm_result.scalar() or 0
    confidence_impact = (
        round(confirm_count / total_annotation_count, 2)
        if total_annotation_count > 0
        else 0.0
    )

    # Recent decision history (last 20)
    history_result = await session.execute(
        select(ValidationDecision)
        .where(
            ValidationDecision.engagement_id == eng_uuid,
            ValidationDecision.reviewer_id == user_id,
        )
        .order_by(ValidationDecision.decision_at.desc())
        .limit(20)
    )
    decisions = list(history_result.scalars().all())

    decision_history = [
        DecisionHistoryItem(
            id=str(d.id),
            decision=str(d.action),
            created_at=d.decision_at,
        )
        for d in decisions
    ]

    return {
        "engagement_id": str(eng_uuid),
        "pending_review_count": pending_review_count,
        "total_annotation_count": total_annotation_count,
        "confidence_impact": confidence_impact,
        "decision_history": decision_history,
    }


@router.get(
    "/{engagement_id}/client",
    response_model=ClientStakeholderDashboard,
)
async def get_client_dashboard(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Client Stakeholder read-only findings dashboard."""
    role = await _get_user_engagement_role(engagement_id, user, session)
    if role not in CLIENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client Stakeholder role required",
        )

    eng_uuid = engagement_id

    # Overall confidence
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

    # Brightness distribution
    brightness = await _get_brightness_distribution(eng_uuid, session)

    # Gap findings (without internal severity scores — client-friendly view)
    gaps_result = await session.execute(
        select(GapAnalysisResult)
        .where(GapAnalysisResult.engagement_id == eng_uuid)
        .order_by(GapAnalysisResult.created_at.desc())
        .limit(50)
    )
    gaps = list(gaps_result.scalars().all())

    gap_findings = [
        GapFindingSummary(
            id=str(g.id),
            gap_type=str(g.gap_type),
            dimension=str(g.dimension),
            recommendation=g.recommendation,
        )
        for g in gaps
    ]

    total_recommendations = sum(1 for g in gaps if g.recommendation)

    return {
        "engagement_id": str(eng_uuid),
        "overall_confidence": overall_confidence,
        "brightness_distribution": brightness,
        "gap_findings": gap_findings,
        "total_recommendations": total_recommendations,
    }
