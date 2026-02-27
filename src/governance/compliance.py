"""Compliance state tracking service for process elements.

Assesses compliance state based on control coverage percentage,
computed by checking ENFORCED_BY edges in the knowledge graph against
evidence of control execution.

Coverage thresholds:
  100% → FULLY_COMPLIANT
  > 0% → PARTIALLY_COMPLIANT
  0%   → NON_COMPLIANT
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from src.core.models import ComplianceLevel

logger = logging.getLogger(__name__)


def compute_compliance_state(
    total_required: int,
    controls_with_evidence: int,
) -> tuple[ComplianceLevel, Decimal]:
    """Compute compliance state from control coverage.

    Args:
        total_required: Total number of required controls (ENFORCED_BY edges).
        controls_with_evidence: Number of controls that have execution evidence.

    Returns:
        (state, coverage_percentage) tuple.
    """
    if total_required == 0:
        return ComplianceLevel.NOT_ASSESSED, Decimal("0.00")

    coverage = Decimal(controls_with_evidence) / Decimal(total_required) * Decimal("100")
    coverage = coverage.quantize(Decimal("0.01"))

    if coverage >= Decimal("100.00"):
        return ComplianceLevel.FULLY_COMPLIANT, Decimal("100.00")
    elif coverage > Decimal("0.00"):
        return ComplianceLevel.PARTIALLY_COMPLIANT, coverage
    else:
        return ComplianceLevel.NON_COMPLIANT, Decimal("0.00")


class ComplianceAssessmentService:
    """Assesses compliance state for process activities.

    Uses ENFORCED_BY edges in the knowledge graph to determine required
    controls, then checks for evidence of control execution.
    """

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def get_required_controls(
        self, activity_id: str, engagement_id: str
    ) -> list[dict[str, Any]]:
        """Query ENFORCED_BY edges to find required controls for an activity.

        Returns list of dicts with 'control_id' and 'control_name' keys.
        """
        try:
            query = (
                "MATCH (a)-[:ENFORCED_BY]->(c) "
                "WHERE a.id = $activity_id AND a.engagement_id = $engagement_id "
                "RETURN c.id AS control_id, c.name AS control_name"
            )
            records = await self._graph.run_query(
                query, {"activity_id": activity_id, "engagement_id": engagement_id}
            )
            return [
                {"control_id": r["control_id"], "control_name": r.get("control_name", "")}
                for r in records
                if r.get("control_id")
            ]
        except Exception:
            logger.warning(
                "Failed to query ENFORCED_BY edges for activity %s", activity_id
            )
            return []

    async def get_controls_with_evidence(
        self, control_ids: list[str], engagement_id: str
    ) -> list[str]:
        """Check which controls have execution evidence.

        Returns list of control IDs that have supporting evidence.
        """
        if not control_ids:
            return []

        try:
            query = (
                "MATCH (c)-[:EVIDENCED_BY]->(e) "
                "WHERE c.id IN $control_ids AND c.engagement_id = $engagement_id "
                "RETURN DISTINCT c.id AS control_id"
            )
            records = await self._graph.run_query(
                query, {"control_ids": control_ids, "engagement_id": engagement_id}
            )
            return [r["control_id"] for r in records if r.get("control_id")]
        except Exception:
            logger.warning("Failed to query control evidence for engagement %s", engagement_id)
            return []

    async def assess_activity(
        self,
        activity_id: str,
        engagement_id: str,
    ) -> dict[str, Any]:
        """Assess compliance state for a single activity.

        Returns dict with: state, control_coverage_percentage, total_required_controls,
        controls_with_evidence, gaps (list of missing control IDs).
        """
        required_controls = await self.get_required_controls(activity_id, engagement_id)
        total_required = len(required_controls)

        if total_required == 0:
            return {
                "state": ComplianceLevel.NOT_ASSESSED,
                "control_coverage_percentage": Decimal("0.00"),
                "total_required_controls": 0,
                "controls_with_evidence": 0,
                "gaps": {"missing_controls": []},
            }

        control_ids = [c["control_id"] for c in required_controls]
        evidenced_ids = await self.get_controls_with_evidence(control_ids, engagement_id)
        evidenced_set = set(evidenced_ids)

        controls_with_evidence = len(evidenced_set)
        missing_controls = [
            {"control_id": c["control_id"], "control_name": c["control_name"]}
            for c in required_controls
            if c["control_id"] not in evidenced_set
        ]

        state, coverage = compute_compliance_state(total_required, controls_with_evidence)

        return {
            "state": state,
            "control_coverage_percentage": coverage,
            "total_required_controls": total_required,
            "controls_with_evidence": controls_with_evidence,
            "gaps": {"missing_controls": missing_controls},
        }
