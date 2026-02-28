"""Governance gap detection service.

Detects process activities that lack required governance controls by
cross-referencing regulation obligations against ENFORCED_BY edges
in the knowledge graph.

Gap severity:
  CRITICAL — regulatory obligation with financial penalty exposure
  HIGH — regulatory obligation without direct financial penalty
  MEDIUM — policy requirement gap
  LOW — best practice gap
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.models import (
    GovernanceGapSeverity,
    GovernanceGapStatus,
    GovernanceGapType,
)

logger = logging.getLogger(__name__)


def derive_severity(regulation_obligations: dict[str, Any] | None) -> GovernanceGapSeverity:
    """Derive gap severity from the regulation's obligation metadata.

    Args:
        regulation_obligations: JSON obligations from the Regulation record.

    Returns:
        Severity tier based on regulatory impact.
    """
    if not regulation_obligations:
        return GovernanceGapSeverity.MEDIUM

    has_penalty = regulation_obligations.get("financial_penalty", False)
    is_regulatory = regulation_obligations.get("regulatory", True)

    if is_regulatory and has_penalty:
        return GovernanceGapSeverity.CRITICAL
    elif is_regulatory:
        return GovernanceGapSeverity.HIGH
    else:
        return GovernanceGapSeverity.MEDIUM


class GovernanceGapDetectionService:
    """Detects governance gaps in an engagement's process activities.

    Queries the knowledge graph for activities that are categorised as requiring
    controls (via regulation obligations) but lack ENFORCED_BY edges.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def get_regulated_activities(
        self, engagement_id: str, required_categories: list[str]
    ) -> list[dict[str, Any]]:
        """Find activities in regulated categories for an engagement.

        Returns list of dicts with activity_id, activity_name, activity_category.
        """
        try:
            query = (
                "MATCH (a:Activity) "
                "WHERE a.engagement_id = $engagement_id "
                "AND a.activity_category IN $categories "
                "RETURN a.id AS activity_id, a.name AS activity_name, "
                "a.activity_category AS activity_category"
            )
            records = await self._graph.run_query(
                query, {"engagement_id": engagement_id, "categories": required_categories}
            )
            return [
                {
                    "activity_id": r["activity_id"],
                    "activity_name": r.get("activity_name", ""),
                    "activity_category": r.get("activity_category", ""),
                }
                for r in records
                if r.get("activity_id")
            ]
        except Exception:
            logger.warning(
                "Failed to query regulated activities for engagement %s",
                engagement_id,
                exc_info=True,
            )
            return []

    async def get_ungoverned_activity_ids(
        self, engagement_id: str, activity_ids: list[str], regulation_id: str | None = None
    ) -> list[str]:
        """Find which activities lack ENFORCED_BY edges (no controls linked).

        Args:
            engagement_id: Engagement to check.
            activity_ids: Activity IDs to inspect.
            regulation_id: If provided, only considers controls linked to this
                regulation via ENFORCES->Policy->GOVERNED_BY->Regulation chain.

        Returns:
            List of activity IDs with no (matching) controls.
        """
        if not activity_ids:
            return []

        try:
            if regulation_id:
                # Regulation-aware: only count controls linked through the governance
                # chain to this specific regulation.
                query = (
                    "MATCH (a:Activity) "
                    "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
                    "AND NOT (a)-[:ENFORCED_BY]->(:Control)-[:ENFORCES]->(:Policy)"
                    "-[:GOVERNED_BY]->(:Regulation {id: $regulation_id}) "
                    "RETURN a.id AS activity_id"
                )
                records = await self._graph.run_query(
                    query,
                    {
                        "activity_ids": activity_ids,
                        "engagement_id": engagement_id,
                        "regulation_id": regulation_id,
                    },
                )
            else:
                query = (
                    "MATCH (a:Activity) "
                    "WHERE a.id IN $activity_ids AND a.engagement_id = $engagement_id "
                    "AND NOT (a)-[:ENFORCED_BY]->(:Control) "
                    "RETURN a.id AS activity_id"
                )
                records = await self._graph.run_query(
                    query, {"activity_ids": activity_ids, "engagement_id": engagement_id}
                )
            return [r["activity_id"] for r in records if r.get("activity_id")]
        except Exception:
            logger.warning(
                "Failed to check ENFORCED_BY edges for engagement %s",
                engagement_id,
                exc_info=True,
            )
            return []

    async def detect_gaps(
        self,
        engagement_id: str,
        regulations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run gap detection for an engagement.

        Args:
            engagement_id: The engagement to scan.
            regulations: List of regulation dicts with id, name, obligations.
                Each obligation should specify required_categories.

        Returns:
            List of gap finding dicts ready for persistence.
        """
        all_gaps: list[dict[str, Any]] = []

        for reg in regulations:
            obligations = reg.get("obligations") or {}
            required_categories = obligations.get("required_categories", [])
            if not required_categories:
                continue

            # Find activities in regulated categories
            regulated_activities = await self.get_regulated_activities(engagement_id, required_categories)
            if not regulated_activities:
                continue

            # Check which lack controls
            activity_ids = [a["activity_id"] for a in regulated_activities]
            ungoverned_ids = await self.get_ungoverned_activity_ids(engagement_id, activity_ids)
            ungoverned_set = set(ungoverned_ids)

            severity = derive_severity(obligations)

            for act in regulated_activities:
                if act["activity_id"] in ungoverned_set:
                    all_gaps.append(
                        {
                            "engagement_id": engagement_id,
                            "activity_id": act["activity_id"],
                            "activity_name": act["activity_name"],
                            "regulation_id": reg["id"],
                            "regulation_name": reg.get("name", ""),
                            "gap_type": GovernanceGapType.CONTROL_GAP,
                            "severity": severity,
                            "status": GovernanceGapStatus.OPEN,
                            "description": (
                                f"Activity '{act['activity_name']}' (category: {act['activity_category']}) "
                                f"requires controls per regulation '{reg.get('name', '')}' "
                                f"but has no ENFORCED_BY edges."
                            ),
                        }
                    )

        return all_gaps

    async def resolve_covered_gaps(
        self,
        engagement_id: str,
        existing_open_gaps: list[dict[str, Any]],
    ) -> list[str]:
        """Check which open gaps are now covered and should be resolved.

        Checks per-regulation: a gap is only resolved when the activity has
        controls linked to the *same* regulation that created the gap.

        Args:
            engagement_id: The engagement being scanned.
            existing_open_gaps: List of open gap dicts with activity_id and regulation_id.

        Returns:
            List of gap IDs that should be marked resolved.
        """
        if not existing_open_gaps:
            return []

        # Group gaps by regulation to perform regulation-aware checks
        by_regulation: dict[str, list[dict[str, Any]]] = {}
        for gap in existing_open_gaps:
            reg_id = str(gap.get("regulation_id", ""))
            by_regulation.setdefault(reg_id, []).append(gap)

        resolved_gap_ids: list[str] = []
        for reg_id, gaps in by_regulation.items():
            activity_ids = list({str(g["activity_id"]) for g in gaps})
            ungoverned_ids = await self.get_ungoverned_activity_ids(
                engagement_id, activity_ids, regulation_id=reg_id if reg_id else None
            )
            ungoverned_set = set(ungoverned_ids)

            for gap in gaps:
                if str(gap["activity_id"]) not in ungoverned_set:
                    resolved_gap_ids.append(gap["id"])

        return resolved_gap_ids
