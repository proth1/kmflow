"""Review pack validation API endpoints (Story #349).

Provides:
- POST /api/v1/validation/review-packs — Trigger async review pack generation
- GET  /api/v1/validation/review-packs — Retrieve generated packs by pov_version_id
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import ProcessElement, ProcessModel, User
from src.core.models.validation import ReviewPack, ReviewPackStatus
from src.core.permissions import require_engagement_access
from src.validation.pack_generator import ActivityInfo, generate_packs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReviewPackResponse(BaseModel):
    """Response schema for a single review pack."""

    id: uuid.UUID
    engagement_id: uuid.UUID
    pov_version_id: uuid.UUID
    segment_index: int
    segment_activities: list
    activity_count: int
    evidence_list: list | None = None
    confidence_scores: dict | None = None
    conflict_flags: list | None = None
    seed_terms: list | None = None
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
    # Verify POV exists
    pov_result = await session.execute(
        select(ProcessModel).where(ProcessModel.id == body.pov_version_id)
    )
    pov = pov_result.scalar_one_or_none()
    if pov is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POV version not found")

    task_id = str(uuid.uuid4())

    # Launch async generation
    asyncio.create_task(
        _generate_packs_async(
            task_id=task_id,
            pov_version_id=body.pov_version_id,
            engagement_id=body.engagement_id,
            session_factory=request.app.state.db_session_factory,
        )
    )

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
    review packs to the database.
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
