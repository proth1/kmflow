"""SLA compliance checker for data catalog entries.

Compares evidence item quality scores against the quality_sla thresholds
stored on a DataCatalogEntry. Returns a structured SLAResult describing
which thresholds passed or failed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import DataCatalogEntry, EvidenceItem

logger = logging.getLogger(__name__)


@dataclass
class SLAViolation:
    """A single quality SLA threshold that was not met.

    Attributes:
        metric: The metric name (e.g., 'completeness', 'min_score').
        threshold: The configured minimum/maximum value.
        actual: The actual observed value.
        message: Human-readable description.
    """

    metric: str
    threshold: float
    actual: float
    message: str


@dataclass
class SLAResult:
    """Result of a quality SLA check for a catalog entry.

    Attributes:
        passing: True if all SLA thresholds are met.
        violations: List of individual threshold failures.
        checked_at: Timestamp of the check.
        entry_id: The catalog entry that was checked.
        evidence_count: Number of evidence items evaluated.
    """

    passing: bool
    violations: list[SLAViolation] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    entry_id: Any = None
    evidence_count: int = 0


async def check_quality_sla(
    session: AsyncSession,
    catalog_entry: DataCatalogEntry,
) -> SLAResult:
    """Check quality SLA compliance for a data catalog entry.

    Retrieves all EvidenceItem records associated with the catalog entry's
    engagement (or platform-wide if no engagement is scoped) and compares
    their quality_score values against the thresholds in ``quality_sla``.

    The ``quality_sla`` dict on the catalog entry may contain:
    - ``min_score``: minimum acceptable average quality score (0.0-1.0)
    - ``min_completeness``: minimum fraction of items with non-null score
    - ``max_failing_fraction``: maximum fraction of items below min_score

    Args:
        session: Async database session.
        catalog_entry: The DataCatalogEntry to check.

    Returns:
        SLAResult with passing status and any violations.
    """
    sla = catalog_entry.quality_sla or {}
    violations: list[SLAViolation] = []

    if not sla:
        # No SLA defined — trivially passing
        return SLAResult(
            passing=True,
            entry_id=catalog_entry.id,
            evidence_count=0,
        )

    # Fetch evidence items in scope
    query = select(EvidenceItem)
    if catalog_entry.engagement_id is not None:
        query = query.where(EvidenceItem.engagement_id == catalog_entry.engagement_id)

    result = await session.execute(query)
    items: list[EvidenceItem] = list(result.scalars().all())
    evidence_count = len(items)

    if evidence_count == 0:
        # Nothing to evaluate — trivially passing
        return SLAResult(
            passing=True,
            entry_id=catalog_entry.id,
            evidence_count=0,
        )

    # Collect quality scores (only items that have a score)
    scored_items = [item for item in items if hasattr(item, "quality_score") and item.quality_score is not None]
    scored_count = len(scored_items)
    scores = [float(item.quality_score) for item in scored_items]

    # --- min_completeness check ---
    min_completeness: float | None = sla.get("min_completeness")
    if min_completeness is not None:
        actual_completeness = scored_count / evidence_count if evidence_count > 0 else 0.0
        if actual_completeness < min_completeness:
            violations.append(
                SLAViolation(
                    metric="min_completeness",
                    threshold=min_completeness,
                    actual=actual_completeness,
                    message=(
                        f"Only {actual_completeness:.1%} of evidence items have "
                        f"quality scores; minimum required is {min_completeness:.1%}."
                    ),
                )
            )

    # --- min_score check (average) ---
    min_score: float | None = sla.get("min_score")
    if min_score is not None and scores:
        avg_score = sum(scores) / len(scores)
        if avg_score < min_score:
            violations.append(
                SLAViolation(
                    metric="min_score",
                    threshold=min_score,
                    actual=avg_score,
                    message=(f"Average quality score {avg_score:.3f} is below the minimum required {min_score:.3f}."),
                )
            )

    # --- max_failing_fraction check ---
    max_failing: float | None = sla.get("max_failing_fraction")
    if max_failing is not None and min_score is not None and scores:
        failing = [s for s in scores if s < min_score]
        failing_fraction = len(failing) / len(scores)
        if failing_fraction > max_failing:
            violations.append(
                SLAViolation(
                    metric="max_failing_fraction",
                    threshold=max_failing,
                    actual=failing_fraction,
                    message=(
                        f"{failing_fraction:.1%} of evidence items score below "
                        f"min_score={min_score}; maximum allowed failing fraction "
                        f"is {max_failing:.1%}."
                    ),
                )
            )

    passing = len(violations) == 0
    logger.info(
        "SLA check for catalog entry %s: %s (%d items, %d violations)",
        catalog_entry.id,
        "PASSING" if passing else "FAILING",
        evidence_count,
        len(violations),
    )

    return SLAResult(
        passing=passing,
        violations=violations,
        entry_id=catalog_entry.id,
        evidence_count=evidence_count,
    )
