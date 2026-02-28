"""Seed list pipeline routes (Story #321).

Provides endpoints for the 4-stage seed list pipeline:
1. Consultant vocabulary upload
2. NLP refinement trigger
3. Probe generation
4. Extraction targeting
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import ProcessElement, ProcessModel, ProcessModelStatus, User
from src.core.models.seed_term import SeedTerm, TermCategory, TermSource, TermStatus
from src.core.permissions import require_engagement_access, require_permission
from src.core.services.coverage_service import build_dark_room_backlog, compute_coverage
from src.core.services.seed_list_service import SeedListService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["seed-lists"])


# ── Schemas ────────────────────────────────────────────────────────────


class SeedTermInput(BaseModel):
    """Single seed term input."""

    term: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(default="general", max_length=200)
    category: TermCategory = TermCategory.ACTIVITY


class CreateSeedListPayload(BaseModel):
    """Request body for bulk seed term creation."""

    terms: list[SeedTermInput] = Field(..., min_length=1, max_length=100)


class DiscoveredTermInput(BaseModel):
    """Single NLP-discovered term."""

    term: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(default="general", max_length=200)
    category: TermCategory = TermCategory.ACTIVITY


class AddDiscoveredTermsPayload(BaseModel):
    """Request body for adding NLP-discovered terms."""

    terms: list[DiscoveredTermInput] = Field(..., min_length=1, max_length=200)


# ── Stage 1: Vocabulary Upload ─────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/seed-lists",
    status_code=status.HTTP_201_CREATED,
)
async def create_seed_list(
    engagement_id: UUID,
    payload: CreateSeedListPayload,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Bulk create consultant-provided seed terms."""
    service = SeedListService(session)
    return await service.create_seed_terms(
        engagement_id=engagement_id,
        terms=[t.model_dump() for t in payload.terms],
        source=TermSource.CONSULTANT_PROVIDED,
    )


@router.get("/engagements/{engagement_id}/seed-lists")
async def get_seed_list(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    status_filter: TermStatus | None = Query(None, alias="status"),
    source: TermSource | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Get the seed list for an engagement with optional filters."""
    service = SeedListService(session)
    return await service.get_seed_list(
        engagement_id,
        status=status_filter,
        source=source,
        limit=limit,
        offset=offset,
    )


# ── Stage 2: NLP Refinement ───────────────────────────────────────────


@router.post("/engagements/{engagement_id}/seed-lists/refine")
async def refine_seed_list(
    engagement_id: UUID,
    payload: AddDiscoveredTermsPayload,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Add NLP-discovered terms to the seed list."""
    service = SeedListService(session)
    return await service.add_discovered_terms(
        engagement_id=engagement_id,
        discovered=[t.model_dump() for t in payload.terms],
    )


# ── Stage 3: Probe Generation ─────────────────────────────────────────


@router.post("/engagements/{engagement_id}/seed-lists/generate-probes")
async def generate_probes(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    seed_term_id: UUID | None = Query(None),
) -> dict[str, Any]:
    """Generate probes from active seed terms."""
    service = SeedListService(session)
    return await service.generate_probes(engagement_id, seed_term_id)


# ── Stage 4: Extraction Targeting ──────────────────────────────────────


@router.get("/engagements/{engagement_id}/seed-lists/extraction-targets")
async def get_extraction_targets(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get active seed terms for extraction pipeline targeting."""
    service = SeedListService(session)
    return await service.get_extraction_targets(engagement_id)


# ── Term Management ───────────────────────────────────────────────────


@router.delete(
    "/engagements/{engagement_id}/seed-terms/{term_id}",
    status_code=status.HTTP_200_OK,
)
async def deprecate_seed_term(
    engagement_id: UUID,
    term_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Deprecate a seed term (soft delete)."""
    service = SeedListService(session)
    result = await service.deprecate_term(term_id)
    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Seed term not found"
        )
    return result


# ── Seed List Coverage Report (Story #367) ────────────────────────────


@router.get("/engagements/{engagement_id}/seed-list/coverage")
async def get_seed_list_coverage(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Seed list coverage report showing covered/uncovered terms.

    Returns total_terms, covered_count, uncovered_count, coverage_percentage,
    and the list of uncovered terms with their metadata.
    """
    # Load active seed terms for the engagement
    terms_result = await session.execute(
        select(SeedTerm).where(
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        )
    )
    terms = list(terms_result.scalars().all())

    # Build term dicts
    term_dicts = [
        {
            "id": str(t.id),
            "term": t.term,
            "domain": t.domain,
            "category": t.category.value if t.category else "",
            "status": t.status.value if t.status else "active",
        }
        for t in terms
    ]

    # Determine which terms have evidence links
    # A term is "covered" if any ProcessElement name contains the term
    # (evidence linking via seed term → element name matching)
    latest_pov_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == engagement_id, ProcessModel.status == ProcessModelStatus.COMPLETED)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    latest_pov = latest_pov_result.scalar_one_or_none()

    evidence_links: set[str] = set()
    if latest_pov:
        elements_result = await session.execute(
            select(ProcessElement).where(ProcessElement.model_id == latest_pov.id)
        )
        elements = list(elements_result.scalars().all())
        element_names_lower = {e.name.lower() for e in elements}

        for t in terms:
            if t.term.lower() in element_names_lower or any(t.term.lower() in name for name in element_names_lower):
                evidence_links.add(str(t.id))

    report = compute_coverage(term_dicts, evidence_links)
    return {
        "total_terms": report.total_terms,
        "covered_count": report.covered_count,
        "uncovered_count": report.uncovered_count,
        "coverage_percentage": report.coverage_percentage,
        "uncovered_terms": report.uncovered_terms,
    }


# ── Dark Room Backlog (Story #367) ────────────────────────────────────


@router.get("/engagements/{engagement_id}/dark-room/backlog")
async def get_dark_room_backlog(
    engagement_id: UUID,
    threshold: float = Query(default=0.40, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Dark Room backlog: dark segments ranked by estimated confidence uplift.

    Returns segments below the confidence threshold, sorted by highest
    estimated uplift first (most valuable evidence acquisition targets).

    Args:
        engagement_id: The engagement to analyze.
        threshold: Confidence threshold for "dark" classification (default 0.40).
        limit: Maximum segments to return.
    """
    # Load latest completed POV
    pov_result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == engagement_id, ProcessModel.status == ProcessModelStatus.COMPLETED)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    pov = pov_result.scalar_one_or_none()
    if not pov:
        return {"engagement_id": str(engagement_id), "segments": [], "total_dark": 0}

    # Load elements
    elements_result = await session.execute(
        select(ProcessElement).where(ProcessElement.model_id == pov.id)
    )
    elements = list(elements_result.scalars().all())

    element_dicts = [
        {
            "id": str(el.id),
            "name": el.name,
            "element_type": el.element_type.value if el.element_type else "",
            "confidence_score": el.confidence_score,
            "evidence_count": el.evidence_count,
            "evidence_grade": el.evidence_grade.value if el.evidence_grade else "U",
            "related_seed_terms": [],
        }
        for el in elements
    ]

    backlog = build_dark_room_backlog(element_dicts, dark_threshold=threshold)

    return {
        "engagement_id": str(engagement_id),
        "pov_version": pov.version,
        "total_dark": len(backlog),
        "segments": [
            {
                "element_id": seg.element_id,
                "name": seg.name,
                "element_type": seg.element_type,
                "confidence_score": seg.confidence_score,
                "estimated_uplift": seg.estimated_uplift,
                "missing_knowledge_forms": seg.missing_knowledge_forms,
                "recommended_actions": seg.recommended_actions,
                "related_seed_terms": seg.related_seed_terms,
            }
            for seg in backlog[:limit]
        ],
    }
