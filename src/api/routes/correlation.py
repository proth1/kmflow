"""Correlation Engine API routes.

Provides endpoints to trigger correlation runs, list case link edges,
retrieve daily diagnostic reports, and surface unlinked events.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.correlation import (
    CaseLinkListResponse,
    CaseLinkResponse,
    CorrelationLinkRequest,
    CorrelationLinkResponse,
    DiagnosticsResponse,
    UnlinkedEventListResponse,
    UnlinkedEventResponse,
)
from src.core.models import Engagement, User
from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.core.permissions import require_engagement_access, require_permission
from src.taskmining.correlation.assisted import AssistedLinker
from src.taskmining.correlation.deterministic import DeterministicLinker
from src.taskmining.correlation.diagnostics import CorrelationDiagnostics
from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX, RoleAssociator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/correlation", tags=["correlation"])


# ---------------------------------------------------------------------------
# POST /correlation/link
# ---------------------------------------------------------------------------


@router.post("/link", response_model=CorrelationLinkResponse, status_code=status.HTTP_200_OK)
async def run_correlation(
    body: CorrelationLinkRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:write")),
) -> dict[str, Any]:
    """Trigger a full correlation run for an engagement.

    Runs deterministic pass first, then assisted pass on remaining unlinked
    events, and finally role-aggregates anything still unlinked.
    """
    engagement_id = body.engagement_id

    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    # Fetch all events for the engagement
    events_result = await session.execute(
        select(CanonicalActivityEvent).where(
            CanonicalActivityEvent.engagement_id == engagement_id
        )
    )
    all_events = list(events_result.scalars().all())

    if not all_events:
        return {
            "engagement_id": engagement_id,
            "links_created": 0,
            "deterministic_count": 0,
            "assisted_count": 0,
            "role_aggregate_count": 0,
            "unlinked_count": 0,
        }

    # -- Deterministic pass --
    det_linker = DeterministicLinker()
    det_edges = await det_linker.link_events_to_cases(session, engagement_id, all_events)
    deterministic_count = len(det_edges)

    linked_event_ids = {e.event_id for e in det_edges}
    unlinked_after_det = [ev for ev in all_events if ev.id not in linked_event_ids]

    # -- Assisted pass --
    assisted_linker = AssistedLinker()
    asst_edges = await assisted_linker.link_probabilistic(session, engagement_id, unlinked_after_det)
    assisted_count = len(asst_edges)

    linked_event_ids |= {e.event_id for e in asst_edges}

    # -- Flush deterministic + assisted before role-aggregate query --
    await session.flush()

    # -- Role-aggregate pass --
    role_assoc = RoleAssociator()
    role_aggregate_count = await role_assoc.associate_unlinked(session, engagement_id)

    await session.commit()

    total_linked = deterministic_count + assisted_count + role_aggregate_count
    unlinked_count = len(all_events) - total_linked

    logger.info(
        "Correlation run complete for engagement %s: det=%d, asst=%d, role=%d, unlinked=%d",
        engagement_id,
        deterministic_count,
        assisted_count,
        role_aggregate_count,
        max(0, unlinked_count),
    )

    return {
        "engagement_id": engagement_id,
        "links_created": total_linked,
        "deterministic_count": deterministic_count,
        "assisted_count": assisted_count,
        "role_aggregate_count": role_aggregate_count,
        "unlinked_count": max(0, unlinked_count),
    }


# ---------------------------------------------------------------------------
# GET /correlation/links
# ---------------------------------------------------------------------------


@router.get("/links", response_model=CaseLinkListResponse)
async def list_links(
    engagement_id: UUID = Query(...),
    case_id: str | None = Query(None, description="Filter by case ID"),
    method: str | None = Query(None, description="Filter by link method: deterministic, assisted, role_aggregate"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List CaseLinkEdge records with optional filters."""
    filters = [
        CaseLinkEdge.engagement_id == engagement_id,
        CaseLinkEdge.confidence >= min_confidence,
    ]
    if case_id:
        filters.append(CaseLinkEdge.case_id == case_id)
    if method:
        filters.append(CaseLinkEdge.method == method)

    count_result = await session.execute(
        select(func.count()).select_from(CaseLinkEdge).where(*filters)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(CaseLinkEdge).where(*filters).limit(limit).offset(offset)
    )
    links = list(result.scalars().all())

    return {
        "items": [
            {
                "id": lk.id,
                "engagement_id": lk.engagement_id,
                "event_id": lk.event_id,
                "case_id": lk.case_id,
                "method": lk.method,
                "confidence": lk.confidence,
                "explainability": lk.explainability,
                "created_at": lk.created_at,
            }
            for lk in links
        ],
        "total": total,
    }


# ---------------------------------------------------------------------------
# GET /correlation/diagnostics
# ---------------------------------------------------------------------------


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_diagnostics(
    engagement_id: UUID = Query(...),
    report_date: date = Query(..., description="Date to compute diagnostics for (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Return the daily correlation quality report for an engagement."""
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    diagnostics = CorrelationDiagnostics()
    report = await diagnostics.generate_daily_report(session, engagement_id, report_date)
    return report


# ---------------------------------------------------------------------------
# GET /correlation/unlinked
# ---------------------------------------------------------------------------


@router.get("/unlinked", response_model=UnlinkedEventListResponse)
async def list_unlinked_events(
    engagement_id: UUID = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List canonical events that have no real case link (excluding role aggregates)."""
    # Subquery: event IDs with a real (non-role-aggregate) link
    linked_subq = (
        select(CaseLinkEdge.event_id)
        .where(
            CaseLinkEdge.engagement_id == engagement_id,
            ~CaseLinkEdge.case_id.startswith(ROLE_AGGREGATE_PREFIX),
        )
    )

    count_result = await session.execute(
        select(func.count())
        .select_from(CanonicalActivityEvent)
        .where(
            CanonicalActivityEvent.engagement_id == engagement_id,
            CanonicalActivityEvent.id.not_in(linked_subq),
        )
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(CanonicalActivityEvent)
        .where(
            CanonicalActivityEvent.engagement_id == engagement_id,
            CanonicalActivityEvent.id.not_in(linked_subq),
        )
        .order_by(CanonicalActivityEvent.timestamp_utc.asc())
        .limit(limit)
        .offset(offset)
    )
    events = list(result.scalars().all())

    return {
        "items": [
            {
                "id": ev.id,
                "engagement_id": ev.engagement_id,
                "case_id": ev.case_id,
                "activity_name": ev.activity_name,
                "timestamp_utc": ev.timestamp_utc,
                "source_system": ev.source_system,
                "performer_role_ref": ev.performer_role_ref,
                "confidence_score": ev.confidence_score,
            }
            for ev in events
        ],
        "total": total,
    }
