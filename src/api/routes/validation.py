"""Validation API endpoints (Stories #349, #353, #357, #365, #370).

Provides:
- POST /api/v1/validation/review-packs — Trigger async review pack generation
- GET  /api/v1/validation/review-packs — Retrieve generated packs by pov_version_id
- POST /api/v1/validation/review-packs/{id}/decisions — Submit reviewer decision
- GET  /api/v1/validation/grading-progression — Evidence grade progression data
- GET  /api/v1/validation/dark-room-shrink — Dark-Room Shrink Rate dashboard data
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    BrightnessClassification,
    DarkRoomSnapshot,
    ProcessElement,
    ProcessModel,
    ProcessModelStatus,
    User,
)
from src.core.models.grading_snapshot import GradingSnapshot
from src.core.models.role_activity_mapping import RoleActivityMapping
from src.core.models.validation import ReviewPack, ReviewPackStatus
from src.core.models.validation_decision import ReviewerAction, ValidationDecision
from src.core.permissions import require_engagement_access
from src.core.services.reviewer_actions_service import ReviewerActionsService
from src.semantic.graph import KnowledgeGraphService
from src.validation.dark_room import (
    DEFAULT_SHRINK_RATE_TARGET,
    compute_illumination_timeline,
    compute_shrink_rates,
    generate_alerts,
)
from src.validation.grading_progression import (
    DEFAULT_IMPROVEMENT_TARGET,
    compute_grade_distributions,
)
from src.validation.pack_generator import ActivityInfo, generate_packs
from src.validation.republish import (
    ElementSnapshot,
    apply_decisions_to_elements,
    compute_diff,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])

# Background task references to prevent GC from cancelling them
_background_tasks: set[asyncio.Task[None]] = set()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReviewPackResponse(BaseModel):
    """Response schema for a single review pack."""

    id: uuid.UUID
    engagement_id: uuid.UUID
    pov_version_id: uuid.UUID
    segment_index: int
    segment_activities: list[dict[str, Any]]
    activity_count: int
    evidence_list: list[str] | None = None
    confidence_scores: dict[str, float] | None = None
    conflict_flags: list[str] | None = None
    seed_terms: list[str] | None = None
    assigned_sme_id: uuid.UUID | None = None
    assigned_role: str | None = None
    status: str
    avg_confidence: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedReviewPackResponse(BaseModel):
    """Paginated response for review pack queries."""

    items: list[ReviewPackResponse]
    total: int
    limit: int
    offset: int


class DecisionRequest(BaseModel):
    """Request body for submitting a reviewer decision."""

    element_id: str = Field(..., description="ID of the graph element being reviewed")
    action: ReviewerAction = Field(..., description="Reviewer action: confirm/correct/reject/defer")
    payload: dict[str, Any] | None = Field(None, description="Action-specific payload")


class DecisionResponse(BaseModel):
    """Response from submitting a reviewer decision."""

    decision_id: str
    action: str
    element_id: str
    graph_write_back: dict[str, Any]
    decision_at: str


class GenerateRequest(BaseModel):
    """Request body for review pack generation."""

    pov_version_id: uuid.UUID
    engagement_id: uuid.UUID


class GenerateResponse(BaseModel):
    """Response from async review pack generation."""

    task_id: str
    status: str = "pending"
    message: str = "Review pack generation started"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/review-packs", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_review_packs(
    body: GenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Trigger asynchronous review pack generation for a POV version.

    Returns HTTP 202 with a task_id. Packs are retrievable via GET once complete.
    """
    # Verify POV exists and belongs to the specified engagement
    pov_result = await session.execute(
        select(ProcessModel).where(
            ProcessModel.id == body.pov_version_id,
            ProcessModel.engagement_id == body.engagement_id,
        )
    )
    pov = pov_result.scalar_one_or_none()
    if pov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POV version not found for this engagement",
        )

    task_id = str(uuid.uuid4())

    # Launch async generation with reference retention
    task = asyncio.create_task(
        _generate_packs_async(
            task_id=task_id,
            pov_version_id=body.pov_version_id,
            engagement_id=body.engagement_id,
            session_factory=request.app.state.db_session_factory,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Review pack generation started",
    }


@router.get("/review-packs", response_model=PaginatedReviewPackResponse)
async def list_review_packs(
    pov_version_id: uuid.UUID = Query(..., description="POV version to get review packs for"),
    engagement_id: uuid.UUID = Query(..., description="Engagement ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by pack status"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Retrieve generated review packs for a POV version."""
    base_where = (
        ReviewPack.pov_version_id == pov_version_id,
        ReviewPack.engagement_id == engagement_id,
    )
    query = select(ReviewPack).where(*base_where)
    count_query = select(func.count()).select_from(ReviewPack).where(*base_where)

    if status_filter is not None:
        query = query.where(ReviewPack.status == status_filter)
        count_query = count_query.where(ReviewPack.status == status_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(ReviewPack.segment_index)
    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Review Pack Detail (Story #365)
# ---------------------------------------------------------------------------


@router.get("/review-packs/{review_pack_id}", response_model=ReviewPackResponse)
async def get_review_pack(
    review_pack_id: uuid.UUID,
    engagement_id: uuid.UUID = Query(..., description="Engagement ID for access scoping"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Retrieve a single review pack by ID.

    Returns full pack details including segment activities, evidence list,
    per-element confidence scores, and conflict flags.
    """
    result = await session.execute(
        select(ReviewPack).where(
            ReviewPack.id == review_pack_id,
            ReviewPack.engagement_id == engagement_id,
        )
    )
    pack = result.scalar_one_or_none()
    if pack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review pack not found",
        )
    return pack


# ---------------------------------------------------------------------------
# Submit Reviewer Decision (Story #353)
# ---------------------------------------------------------------------------


@router.post(
    "/review-packs/{review_pack_id}/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_decision(
    review_pack_id: uuid.UUID,
    body: DecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Submit a structured reviewer decision on a review pack item.

    Persists a ValidationDecision and triggers the corresponding
    knowledge graph write-back (CONFIRM/CORRECT/REJECT/DEFER).
    """
    # Verify review pack exists and get its engagement_id
    pack_result = await session.execute(
        select(ReviewPack).where(ReviewPack.id == review_pack_id)
    )
    pack = pack_result.scalar_one_or_none()
    if pack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review pack not found",
        )

    # SEC-02: Validate element_id belongs to this review pack
    pack_element_ids = {
        a["id"] for a in (pack.segment_activities or []) if isinstance(a, dict) and "id" in a
    }
    if pack_element_ids and body.element_id not in pack_element_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Element not found in this review pack",
        )

    graph = KnowledgeGraphService(request.app.state.neo4j_driver)
    service = ReviewerActionsService(graph=graph, session=session)

    result = await service.submit_decision(
        engagement_id=pack.engagement_id,
        review_pack_id=review_pack_id,
        element_id=body.element_id,
        action=body.action,
        reviewer_id=current_user.id,
        payload=body.payload,
    )
    await session.commit()

    return result


# ---------------------------------------------------------------------------
# Filtered Decision Listing (Story #365)
# ---------------------------------------------------------------------------


class DecisionListItem(BaseModel):
    """Decision item for listing."""

    id: uuid.UUID
    engagement_id: uuid.UUID
    review_pack_id: uuid.UUID
    element_id: str
    action: str
    reviewer_id: uuid.UUID | None
    payload: dict[str, Any] | None
    graph_write_back_result: dict[str, Any] | None
    decision_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDecisionResponse(BaseModel):
    """Paginated response for decision queries."""

    items: list[DecisionListItem]
    total: int
    limit: int
    offset: int


@router.get("/decisions", response_model=PaginatedDecisionResponse)
async def list_decisions(
    engagement_id: uuid.UUID = Query(..., description="Engagement ID"),
    action: ReviewerAction | None = Query(None, description="Filter by action"),
    reviewer_id: uuid.UUID | None = Query(None, description="Filter by reviewer"),
    review_pack_id: uuid.UUID | None = Query(None, description="Filter by review pack"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List validation decisions with optional filters.

    Results are ordered by decision_at descending (most recent first).
    """
    query = select(ValidationDecision).where(
        ValidationDecision.engagement_id == engagement_id
    )
    count_query = (
        select(func.count())
        .select_from(ValidationDecision)
        .where(ValidationDecision.engagement_id == engagement_id)
    )

    if action is not None:
        query = query.where(ValidationDecision.action == action)
        count_query = count_query.where(ValidationDecision.action == action)

    if reviewer_id is not None:
        query = query.where(ValidationDecision.reviewer_id == reviewer_id)
        count_query = count_query.where(ValidationDecision.reviewer_id == reviewer_id)

    if review_pack_id is not None:
        query = query.where(ValidationDecision.review_pack_id == review_pack_id)
        count_query = count_query.where(ValidationDecision.review_pack_id == review_pack_id)

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(ValidationDecision.decision_at.desc())
    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Reviewer Routing (Story #365 — Scenario 3)
# ---------------------------------------------------------------------------


class RoutePacksRequest(BaseModel):
    """Request body for routing review packs to reviewers."""

    engagement_id: uuid.UUID


class RoutedPackResponse(BaseModel):
    """Response showing which packs were routed to which reviewer."""

    pack_id: str
    assigned_role: str | None
    assigned_sme_id: str | None
    status: str


@router.post("/review-packs/route", response_model=list[RoutedPackResponse])
async def route_review_packs(
    body: RoutePacksRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> list[dict[str, Any]]:
    """Route unassigned review packs to reviewers using role-activity mapping.

    For each pending/unassigned pack, looks up the RoleActivityMapping for
    the pack's assigned_role and sets assigned_sme_id accordingly.
    Packs with no matching role mapping remain unassigned.
    """
    # Load role-activity mappings for this engagement
    mapping_result = await session.execute(
        select(RoleActivityMapping).where(
            RoleActivityMapping.engagement_id == body.engagement_id
        )
    )
    mappings = mapping_result.scalars().all()
    role_to_reviewer: dict[str, uuid.UUID] = {
        m.role_name: m.reviewer_id for m in mappings
    }

    # Load unassigned packs for this engagement
    pack_result = await session.execute(
        select(ReviewPack).where(
            ReviewPack.engagement_id == body.engagement_id,
            ReviewPack.assigned_sme_id.is_(None),
        )
    )
    packs = pack_result.scalars().all()

    routed: list[dict[str, Any]] = []
    for pack in packs:
        reviewer_id = role_to_reviewer.get(pack.assigned_role) if pack.assigned_role else None
        if reviewer_id is not None:
            pack.assigned_sme_id = reviewer_id
        routed.append({
            "pack_id": str(pack.id),
            "assigned_role": pack.assigned_role,
            "assigned_sme_id": str(pack.assigned_sme_id) if pack.assigned_sme_id else None,
            "status": "routed" if reviewer_id else "unassigned",
        })

    await session.commit()

    return routed


# ---------------------------------------------------------------------------
# Republish Cycle (Story #361 — Scenario 1)
# ---------------------------------------------------------------------------


class RepublishRequest(BaseModel):
    """Request body to trigger POV republish."""

    pov_version_id: uuid.UUID
    engagement_id: uuid.UUID


class RepublishResponse(BaseModel):
    """Response from POV republish."""

    new_version_id: str
    new_version_number: int
    total_elements: int
    dark_shrink_rate: float | None
    changes_summary: dict[str, int]


@router.post("/republish", response_model=RepublishResponse, status_code=status.HTTP_201_CREATED)
async def republish_pov(
    body: RepublishRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Republish a POV version incorporating validation decisions.

    Creates a new version (v2, v3, etc.) by applying CONFIRM/CORRECT/REJECT/DEFER
    decisions from the prior version's review packs.
    """
    # Load source POV
    pov_result = await session.execute(
        select(ProcessModel).where(
            ProcessModel.id == body.pov_version_id,
            ProcessModel.engagement_id == body.engagement_id,
        )
    )
    source_pov = pov_result.scalar_one_or_none()
    if source_pov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POV version not found for this engagement",
        )

    # Load source elements
    elements_result = await session.execute(
        select(ProcessElement)
        .where(ProcessElement.model_id == body.pov_version_id)
        .order_by(ProcessElement.created_at)
    )
    source_elements = elements_result.scalars().all()

    # Build element snapshots
    snapshots = [
        ElementSnapshot(
            element_id=str(el.id),
            name=el.name,
            element_type=el.element_type.value if hasattr(el.element_type, "value") else str(el.element_type),
            confidence_score=el.confidence_score,
            evidence_grade=el.evidence_grade.value if hasattr(el.evidence_grade, "value") else str(el.evidence_grade),
            brightness_classification=(
                el.brightness_classification.value
                if hasattr(el.brightness_classification, "value")
                else str(el.brightness_classification)
            ),
            evidence_count=el.evidence_count,
            evidence_ids=el.evidence_ids or [],
        )
        for el in source_elements
    ]

    # Load validation decisions for this POV version's review packs
    decisions_result = await session.execute(
        select(ValidationDecision).where(
            ValidationDecision.engagement_id == body.engagement_id,
            ValidationDecision.review_pack_id.in_(
                select(ReviewPack.id).where(ReviewPack.pov_version_id == body.pov_version_id)
            ),
        )
    )
    decisions = decisions_result.scalars().all()

    decision_dicts = [
        {
            "element_id": d.element_id,
            "action": d.action,
            "payload": d.payload or {},
        }
        for d in decisions
    ]

    # Apply decisions to produce new element set
    new_snapshots = apply_decisions_to_elements(snapshots, decision_dicts)

    # Compute diff for shrink rate
    diff = compute_diff(snapshots, new_snapshots, str(body.pov_version_id), "new")

    # Create new ProcessModel version
    new_version = source_pov.version + 1
    new_pov = ProcessModel(
        engagement_id=body.engagement_id,
        version=new_version,
        scope=source_pov.scope,
        status=ProcessModelStatus.COMPLETED,
        confidence_score=source_pov.confidence_score,
        element_count=len(new_snapshots),
        evidence_count=source_pov.evidence_count,
        metadata_json={"source_version_id": str(body.pov_version_id), "source_decisions": "validation"},
        generated_by="republish_engine",
    )
    session.add(new_pov)
    await session.flush()

    # Create new ProcessElement rows for the new version
    for snap in new_snapshots:
        new_el = ProcessElement(
            model_id=new_pov.id,
            element_type=snap.element_type,
            name=snap.name,
            confidence_score=snap.confidence_score,
            evidence_grade=snap.evidence_grade,
            brightness_classification=snap.brightness_classification,
            evidence_count=snap.evidence_count,
            evidence_ids=snap.evidence_ids,
        )
        session.add(new_el)

    await session.commit()

    return {
        "new_version_id": str(new_pov.id),
        "new_version_number": new_version,
        "total_elements": len(new_snapshots),
        "dark_shrink_rate": diff.dark_shrink_rate,
        "changes_summary": {
            "added": len(diff.added),
            "removed": len(diff.removed),
            "modified": len(diff.modified),
            "unchanged": diff.unchanged_count,
        },
    }


# ---------------------------------------------------------------------------
# Version Diff (Story #361 — Scenario 2 & 3)
# ---------------------------------------------------------------------------


class ElementChangeResponse(BaseModel):
    """A single element change in the diff."""

    element_id: str
    element_name: str
    change_type: str
    changed_fields: list[str] = []
    color: str = "none"
    css_class: str = "unchanged"


class VersionDiffResponse(BaseModel):
    """Structured diff between two POV versions."""

    v1_id: str
    v2_id: str
    added: list[ElementChangeResponse]
    removed: list[ElementChangeResponse]
    modified: list[ElementChangeResponse]
    unchanged_count: int
    dark_shrink_rate: float | None
    total_changes: int


@router.get("/diff", response_model=VersionDiffResponse)
async def get_version_diff(
    v1: uuid.UUID = Query(..., description="POV version 1 ID"),
    v2: uuid.UUID = Query(..., description="POV version 2 ID"),
    engagement_id: uuid.UUID = Query(..., description="Engagement ID"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute the diff between two POV versions.

    Returns added, removed, and modified elements with BPMN color-coding hints.
    """
    # Load both versions (engagement-scoped)
    v1_result = await session.execute(
        select(ProcessModel).where(
            ProcessModel.id == v1,
            ProcessModel.engagement_id == engagement_id,
        )
    )
    v1_pov = v1_result.scalar_one_or_none()
    if v1_pov is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version 1 not found")

    v2_result = await session.execute(
        select(ProcessModel).where(
            ProcessModel.id == v2,
            ProcessModel.engagement_id == engagement_id,
        )
    )
    v2_pov = v2_result.scalar_one_or_none()
    if v2_pov is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version 2 not found")

    # Load elements for both
    v1_els_result = await session.execute(
        select(ProcessElement).where(ProcessElement.model_id == v1)
    )
    v1_elements = v1_els_result.scalars().all()

    v2_els_result = await session.execute(
        select(ProcessElement).where(ProcessElement.model_id == v2)
    )
    v2_elements = v2_els_result.scalars().all()

    def to_snapshot(el: Any) -> ElementSnapshot:
        return ElementSnapshot(
            element_id=str(el.id),
            name=el.name,
            element_type=el.element_type.value if hasattr(el.element_type, "value") else str(el.element_type),
            confidence_score=el.confidence_score,
            evidence_grade=el.evidence_grade.value if hasattr(el.evidence_grade, "value") else str(el.evidence_grade),
            brightness_classification=(
                el.brightness_classification.value
                if hasattr(el.brightness_classification, "value")
                else str(el.brightness_classification)
            ),
            evidence_count=el.evidence_count,
            evidence_ids=el.evidence_ids or [],
        )

    v1_snapshots = [to_snapshot(e) for e in v1_elements]
    v2_snapshots = [to_snapshot(e) for e in v2_elements]

    diff = compute_diff(v1_snapshots, v2_snapshots, str(v1), str(v2))

    def change_to_dict(c: Any) -> dict[str, Any]:
        return {
            "element_id": c.element_id,
            "element_name": c.element_name,
            "change_type": c.change_type.value,
            "changed_fields": c.changed_fields,
            "color": c.color,
            "css_class": c.css_class,
        }

    return {
        "v1_id": str(v1),
        "v2_id": str(v2),
        "added": [change_to_dict(c) for c in diff.added],
        "removed": [change_to_dict(c) for c in diff.removed],
        "modified": [change_to_dict(c) for c in diff.modified],
        "unchanged_count": diff.unchanged_count,
        "dark_shrink_rate": diff.dark_shrink_rate,
        "total_changes": diff.total_changes,
    }


# ---------------------------------------------------------------------------
# Async generation task
# ---------------------------------------------------------------------------


async def _generate_packs_async(
    task_id: str,
    pov_version_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session_factory: Any,
) -> None:
    """Background task to generate review packs.

    Queries process elements from the POV, segments them, and persists
    review packs to the database. On failure, writes a sentinel pack
    with status='failed' so clients can detect the error.
    """
    try:
        async with session_factory() as session:
            # Load process elements
            result = await session.execute(
                select(ProcessElement)
                .where(ProcessElement.model_id == pov_version_id)
                .order_by(ProcessElement.created_at)
            )
            elements = result.scalars().all()

            # Convert to ActivityInfo
            activities = [
                ActivityInfo(
                    id=str(el.id),
                    name=el.name,
                    confidence_score=el.confidence_score,
                    evidence_ids=el.evidence_ids or [],
                    conflict_ids=[],
                    seed_term_ids=[],
                    performing_role=None,
                )
                for el in elements
                if el.element_type == "activity"
            ]

            # Generate packs
            packs = generate_packs(activities)

            # Persist
            for pack_data in packs:
                pack = ReviewPack(
                    engagement_id=engagement_id,
                    pov_version_id=pov_version_id,
                    segment_index=pack_data.segment_index,
                    segment_activities=[
                        {"id": a.id, "name": a.name} for a in pack_data.activities
                    ],
                    activity_count=len(pack_data.activities),
                    evidence_list=pack_data.evidence_ids,
                    confidence_scores=pack_data.confidence_scores,
                    conflict_flags=pack_data.conflict_ids,
                    seed_terms=pack_data.seed_term_ids,
                    assigned_role=pack_data.assigned_role,
                    status=ReviewPackStatus.PENDING,
                    avg_confidence=pack_data.avg_confidence,
                    task_id=task_id,
                )
                session.add(pack)

            await session.commit()

            logger.info(
                "Generated %d review packs for POV %s (task %s)",
                len(packs),
                pov_version_id,
                task_id,
            )

    except Exception:
        logger.exception("Failed to generate review packs (task %s)", task_id)
        # Write a sentinel record so clients can detect the failure via GET
        try:
            async with session_factory() as session:
                sentinel = ReviewPack(
                    engagement_id=engagement_id,
                    pov_version_id=pov_version_id,
                    segment_index=-1,
                    segment_activities=[],
                    activity_count=0,
                    status="failed",
                    avg_confidence=0.0,
                    task_id=task_id,
                )
                session.add(sentinel)
                await session.commit()
        except Exception:
            logger.exception("Failed to write failure sentinel (task %s)", task_id)


# ---------------------------------------------------------------------------
# Dark-Room Shrink Rate Dashboard (Story #370)
# ---------------------------------------------------------------------------


class ShrinkRateAlertResponse(BaseModel):
    """Alert included when shrink rate is below target."""

    severity: str
    message: str
    version_number: int
    actual_rate: float
    target_rate: float
    dark_segments: list[str]


class VersionShrinkResponse(BaseModel):
    """Per-version shrink rate data."""

    version_number: int
    pov_version_id: str
    dark_count: int
    dim_count: int
    bright_count: int
    total_elements: int
    reduction_pct: float | None
    snapshot_at: str


class IlluminationEventResponse(BaseModel):
    """Timeline event for a segment that was illuminated."""

    element_name: str
    element_id: str
    from_classification: str
    to_classification: str
    illuminated_in_version: int
    pov_version_id: str
    evidence_ids: list[str]


class DarkRoomDashboardResponse(BaseModel):
    """Complete dark-room shrink rate dashboard data."""

    engagement_id: str
    shrink_rate_target: float
    versions: list[VersionShrinkResponse]
    alerts: list[ShrinkRateAlertResponse]
    illumination_timeline: list[IlluminationEventResponse]


@router.get("/dark-room-shrink", response_model=DarkRoomDashboardResponse)
async def get_dark_room_shrink(
    engagement_id: UUID = Query(..., description="Engagement UUID"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get Dark-Room Shrink Rate dashboard data.

    Returns per-version dark segment counts, reduction percentages,
    alerts when shrink rate is below target, and illumination timeline.
    """
    # Fetch snapshots ordered by version
    snapshot_query = (
        select(DarkRoomSnapshot)
        .where(DarkRoomSnapshot.engagement_id == engagement_id)
        .order_by(DarkRoomSnapshot.version_number.asc())
    )
    result = await session.execute(snapshot_query)
    snapshots = result.scalars().all()

    snapshot_dicts = [
        {
            "version_number": s.version_number,
            "pov_version_id": s.pov_version_id,
            "dark_count": s.dark_count,
            "dim_count": s.dim_count,
            "bright_count": s.bright_count,
            "total_elements": s.total_elements,
            "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else "",
        }
        for s in snapshots
    ]

    # Compute shrink rates
    versions = compute_shrink_rates(snapshot_dicts)

    # Get dark segment names for alerts (from latest version)
    dark_segment_names: list[str] = []
    if snapshots:
        latest = snapshots[-1]
        dark_elements_query = (
            select(ProcessElement.name)
            .where(
                ProcessElement.model_id == latest.pov_version_id,
                ProcessElement.brightness_classification == BrightnessClassification.DARK,
            )
        )
        dark_result = await session.execute(dark_elements_query)
        dark_segment_names = list(dark_result.scalars().all())

    # Generate alerts
    alerts = generate_alerts(versions, dark_segment_names=dark_segment_names)

    # Compute illumination timeline
    illumination_timeline: list[dict[str, Any]] = []
    if len(snapshots) >= 2:
        # Get elements across all POV versions for this engagement
        pov_ids = [s.pov_version_id for s in snapshots]
        elements_query = (
            select(
                ProcessElement.name,
                ProcessElement.id,
                ProcessElement.brightness_classification,
                ProcessElement.evidence_ids,
                ProcessModel.version,
                ProcessModel.id.label("pov_id"),
            )
            .join(ProcessModel, ProcessElement.model_id == ProcessModel.id)
            .where(ProcessElement.model_id.in_(pov_ids))
            .order_by(ProcessElement.name, ProcessModel.version)
        )
        el_result = await session.execute(elements_query)
        element_rows = el_result.all()

        version_elements = [
            {
                "element_name": row[0],
                "element_id": str(row[1]),
                "brightness_classification": row[2].value if hasattr(row[2], "value") else str(row[2]),
                "evidence_ids": row[3] or [],
                "version_number": row[4],
                "pov_version_id": str(row[5]),
            }
            for row in element_rows
        ]

        illumination_events = compute_illumination_timeline(version_elements)
        illumination_timeline = [
            {
                "element_name": e.element_name,
                "element_id": e.element_id,
                "from_classification": e.from_classification,
                "to_classification": e.to_classification,
                "illuminated_in_version": e.illuminated_in_version,
                "pov_version_id": e.pov_version_id,
                "evidence_ids": e.evidence_ids,
            }
            for e in illumination_events
        ]

    return {
        "engagement_id": str(engagement_id),
        "shrink_rate_target": DEFAULT_SHRINK_RATE_TARGET,
        "versions": [
            {
                "version_number": v.version_number,
                "pov_version_id": v.pov_version_id,
                "dark_count": v.dark_count,
                "dim_count": v.dim_count,
                "bright_count": v.bright_count,
                "total_elements": v.total_elements,
                "reduction_pct": v.reduction_pct,
                "snapshot_at": v.snapshot_at,
            }
            for v in versions
        ],
        "alerts": [
            {
                "severity": a.severity,
                "message": a.message,
                "version_number": a.version_number,
                "actual_rate": a.actual_rate,
                "target_rate": a.target_rate,
                "dark_segments": a.dark_segments,
            }
            for a in alerts
        ],
        "illumination_timeline": illumination_timeline,
    }


# ---------------------------------------------------------------------------
# Grading Progression Dashboard (Story #357)
# ---------------------------------------------------------------------------


class VersionGradeResponse(BaseModel):
    """Per-version grade distribution data."""

    version_number: int
    pov_version_id: str
    grade_counts: dict[str, int]
    total_elements: int
    improvement_pct: float | None
    snapshot_at: str


class GradingProgressionResponse(BaseModel):
    """Complete grading progression dashboard data."""

    engagement_id: str
    improvement_target: float
    versions: list[VersionGradeResponse]


@router.get("/grading-progression", response_model=GradingProgressionResponse)
async def get_grading_progression(
    engagement_id: UUID = Query(..., description="Engagement UUID"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get evidence grading progression data across POV versions.

    Returns per-version grade distributions (U/D/C/B/A counts),
    improvement percentages, and the target KPI threshold.
    """
    snapshot_query = (
        select(GradingSnapshot)
        .where(GradingSnapshot.engagement_id == engagement_id)
        .order_by(GradingSnapshot.version_number.asc())
    )
    result = await session.execute(snapshot_query)
    snapshots = result.scalars().all()

    snapshot_dicts = [
        {
            "version_number": s.version_number,
            "pov_version_id": str(s.pov_version_id),
            "grade_u": s.grade_u,
            "grade_d": s.grade_d,
            "grade_c": s.grade_c,
            "grade_b": s.grade_b,
            "grade_a": s.grade_a,
            "total_elements": s.total_elements,
            "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else "",
        }
        for s in snapshots
    ]

    distributions = compute_grade_distributions(snapshot_dicts)

    return {
        "engagement_id": str(engagement_id),
        "improvement_target": DEFAULT_IMPROVEMENT_TARGET,
        "versions": [
            {
                "version_number": d.version_number,
                "pov_version_id": d.pov_version_id,
                "grade_counts": {
                    "U": d.grade_u,
                    "D": d.grade_d,
                    "C": d.grade_c,
                    "B": d.grade_b,
                    "A": d.grade_a,
                },
                "total_elements": d.total_elements,
                "improvement_pct": d.improvement_pct,
                "snapshot_at": d.snapshot_at,
            }
            for d in distributions
        ],
    }
