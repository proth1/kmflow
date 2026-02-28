"""Seed list coverage and Dark Room backlog service (Story #367).

Computes engagement health metrics:
- Seed list coverage: what percentage of terms have evidence links
- Dark Room backlog: dark segments ranked by estimated confidence uplift
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import ProcessElement, ProcessModel, ProcessModelStatus
from src.core.models.seed_term import SeedTerm, TermStatus


@dataclass
class CoverageReport:
    """Seed list coverage report for an engagement."""

    total_terms: int
    covered_count: int
    uncovered_count: int
    coverage_percentage: float
    uncovered_terms: list[dict[str, str]]


@dataclass
class DarkSegment:
    """A dark-classified process segment with uplift estimate."""

    element_id: str
    name: str
    element_type: str
    confidence_score: float
    estimated_uplift: float
    missing_knowledge_forms: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    related_seed_terms: list[str] = field(default_factory=list)


def compute_coverage(
    seed_terms: list[dict[str, Any]],
    evidence_links: set[str],
) -> CoverageReport:
    """Compute seed list coverage from term list and evidence links.

    Args:
        seed_terms: List of seed term dicts with keys: id, term, domain, category, status.
        evidence_links: Set of seed term IDs that have at least one evidence link.

    Returns:
        CoverageReport with counts and uncovered term list.
    """
    active_terms = [t for t in seed_terms if t.get("status", "active") == "active"]
    total = len(active_terms)
    covered = sum(1 for t in active_terms if str(t.get("id", "")) in evidence_links)
    uncovered = total - covered

    uncovered_terms = [
        {
            "id": str(t.get("id", "")),
            "term": str(t.get("term", "")),
            "domain": str(t.get("domain", "")),
            "category": str(t.get("category", "")),
        }
        for t in active_terms
        if str(t.get("id", "")) not in evidence_links
    ]

    return CoverageReport(
        total_terms=total,
        covered_count=covered,
        uncovered_count=uncovered,
        coverage_percentage=round((covered / total) * 100, 1) if total > 0 else 0.0,
        uncovered_terms=uncovered_terms,
    )


def estimate_uplift(confidence_score: float) -> float:
    """Estimate confidence uplift if target evidence were obtained.

    Heuristic v1: max possible improvement scaled by current gap.
    Elements with lower confidence have higher potential uplift.

    Args:
        confidence_score: Current confidence (0.0-1.0).

    Returns:
        Estimated uplift (0.0-1.0).
    """
    max_confidence = 1.0
    gap = max_confidence - confidence_score
    # Assume we can close ~50% of the gap with targeted evidence acquisition
    return round(gap * 0.5, 4)


def build_dark_room_backlog(
    elements: list[dict[str, Any]],
    dark_threshold: float = 0.40,
) -> list[DarkSegment]:
    """Build the dark room backlog from process elements.

    Filters elements with confidence below threshold, computes uplift,
    and sorts by estimated uplift descending.

    Args:
        elements: List of element dicts with keys: id, name, element_type,
            confidence_score, evidence_grade, evidence_count, related_seed_terms.
        dark_threshold: Confidence threshold for "dark" classification.

    Returns:
        List of DarkSegment sorted by estimated_uplift descending.
    """
    segments: list[DarkSegment] = []

    for el in elements:
        conf = float(el.get("confidence_score", 0.0))
        if conf >= dark_threshold:
            continue

        uplift = estimate_uplift(conf)
        evidence_count = int(el.get("evidence_count", 0))
        evidence_grade = str(el.get("evidence_grade", "U"))

        # Generate missing knowledge forms based on evidence gaps
        missing_forms = _infer_missing_knowledge(evidence_count, evidence_grade)

        # Generate recommended actions
        actions = _infer_recommended_actions(evidence_count, evidence_grade, conf)

        segments.append(
            DarkSegment(
                element_id=str(el.get("id", "")),
                name=str(el.get("name", "")),
                element_type=str(el.get("element_type", "")),
                confidence_score=conf,
                estimated_uplift=uplift,
                missing_knowledge_forms=missing_forms,
                recommended_actions=actions,
                related_seed_terms=el.get("related_seed_terms", []),
            )
        )

    # Sort by estimated uplift descending (highest value evidence first)
    segments.sort(key=lambda s: s.estimated_uplift, reverse=True)
    return segments


async def fetch_coverage_report(
    session: AsyncSession,
    engagement_id: UUID,
) -> dict[str, Any]:
    """Fetch and compute seed list coverage for an engagement.

    Loads active seed terms, finds the latest completed POV, matches terms
    to element names, and returns coverage statistics.

    Args:
        session: Database session.
        engagement_id: The engagement to analyze.

    Returns:
        Dict with coverage report fields.
    """
    # Load active seed terms
    terms_result = await session.execute(
        select(SeedTerm).where(
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        )
    )
    terms = list(terms_result.scalars().all())

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

    # Find evidence links via element name matching against latest POV
    latest_pov = await _get_latest_pov(session, engagement_id)

    evidence_links: set[str] = set()
    if latest_pov:
        elements_result = await session.execute(select(ProcessElement).where(ProcessElement.model_id == latest_pov.id))
        elements = list(elements_result.scalars().all())
        element_names_lower = {e.name.lower() for e in elements}

        for t in terms:
            if t.term.lower() in element_names_lower:
                evidence_links.add(str(t.id))

    report = compute_coverage(term_dicts, evidence_links)
    return {
        "total_terms": report.total_terms,
        "covered_count": report.covered_count,
        "uncovered_count": report.uncovered_count,
        "coverage_percentage": report.coverage_percentage,
        "uncovered_terms": report.uncovered_terms,
    }


async def fetch_dark_room_backlog(
    session: AsyncSession,
    engagement_id: UUID,
    threshold: float = 0.40,
    limit: int = 50,
) -> dict[str, Any]:
    """Fetch dark room backlog for an engagement.

    Loads the latest completed POV, filters elements below confidence threshold
    in SQL, populates related seed terms, and returns ranked dark segments.

    Args:
        session: Database session.
        engagement_id: The engagement to analyze.
        threshold: Confidence threshold for "dark" classification.
        limit: Maximum segments to return.

    Returns:
        Dict with dark room backlog fields.
    """
    latest_pov = await _get_latest_pov(session, engagement_id)
    if not latest_pov:
        return {"engagement_id": str(engagement_id), "segments": [], "total_dark": 0}

    # Push threshold filter to SQL (P-1 fix)
    elements_result = await session.execute(
        select(ProcessElement).where(
            ProcessElement.model_id == latest_pov.id,
            ProcessElement.confidence_score < threshold,
        )
    )
    dark_elements = list(elements_result.scalars().all())

    # Load active seed terms for cross-referencing (A-1 fix)
    terms_result = await session.execute(
        select(SeedTerm).where(
            SeedTerm.engagement_id == engagement_id,
            SeedTerm.status == TermStatus.ACTIVE,
        )
    )
    seed_terms = list(terms_result.scalars().all())

    element_dicts = []
    for el in dark_elements:
        # Find related seed terms by name matching
        related = [t.term for t in seed_terms if t.term.lower() in el.name.lower()]
        element_dicts.append(
            {
                "id": str(el.id),
                "name": el.name,
                "element_type": el.element_type.value if el.element_type else "",
                "confidence_score": el.confidence_score,
                "evidence_count": el.evidence_count,
                "evidence_grade": el.evidence_grade.value if el.evidence_grade else "U",
                "related_seed_terms": related,
            }
        )

    backlog = build_dark_room_backlog(element_dicts, dark_threshold=threshold)

    return {
        "engagement_id": str(engagement_id),
        "pov_version": latest_pov.version,
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


async def _get_latest_pov(
    session: AsyncSession,
    engagement_id: UUID,
) -> ProcessModel | None:
    """Get the latest completed POV for an engagement."""
    result = await session.execute(
        select(ProcessModel)
        .where(ProcessModel.engagement_id == engagement_id, ProcessModel.status == ProcessModelStatus.COMPLETED)
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _infer_missing_knowledge(evidence_count: int, evidence_grade: str) -> list[str]:
    """Infer what knowledge forms are missing based on evidence state."""
    forms: list[str] = []

    if evidence_count == 0:
        forms.append("Process documentation")
        forms.append("Subject matter expert interview")
        forms.append("System walkthrough recording")
    elif evidence_grade in ("U", "D"):
        forms.append("Corroborating evidence from second source")
        if evidence_count < 3:
            forms.append("Process walkthrough recording")
    elif evidence_grade == "C":
        forms.append("SME validation of existing evidence")

    return forms


def _infer_recommended_actions(
    evidence_count: int,
    evidence_grade: str,
    confidence: float,
) -> list[str]:
    """Generate recommended evidence acquisition actions."""
    actions: list[str] = []

    if evidence_count == 0:
        actions.append("Request process walkthrough recording from client")
        actions.append("Obtain policy document from client")
        actions.append("Schedule SME interview")
    elif confidence < 0.20:
        actions.append("Request additional documentation from client")
        actions.append("Schedule process observation session")
    elif evidence_grade in ("U", "D"):
        actions.append("Request corroborating evidence from alternative source")
        actions.append("Schedule validation interview with process owner")
    elif evidence_grade == "C":
        actions.append("Schedule SME review session for evidence validation")

    return actions
