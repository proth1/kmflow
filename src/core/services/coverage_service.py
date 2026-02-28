"""Seed list coverage and Dark Room backlog service (Story #367).

Computes engagement health metrics:
- Seed list coverage: what percentage of terms have evidence links
- Dark Room backlog: dark segments ranked by estimated confidence uplift
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
            confidence_score, evidence_grade, evidence_count, metadata_json.
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

        segments.append(DarkSegment(
            element_id=str(el.get("id", "")),
            name=str(el.get("name", "")),
            element_type=str(el.get("element_type", "")),
            confidence_score=conf,
            estimated_uplift=uplift,
            missing_knowledge_forms=missing_forms,
            recommended_actions=actions,
            related_seed_terms=el.get("related_seed_terms", []),
        ))

    # Sort by estimated uplift descending (highest value evidence first)
    segments.sort(key=lambda s: s.estimated_uplift, reverse=True)
    return segments


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
