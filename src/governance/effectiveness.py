"""Control effectiveness scoring service.

Scores each control's effectiveness based on evidence of execution,
frequency of execution, and coverage breadth via knowledge graph queries.

Effectiveness thresholds:
  >= 90% execution rate → HIGHLY_EFFECTIVE
  70-89% → EFFECTIVE
  50-69% → MODERATELY_EFFECTIVE
  < 50% → INEFFECTIVE
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from src.core.models import ControlEffectiveness

logger = logging.getLogger(__name__)

THRESHOLD_HIGHLY_EFFECTIVE = Decimal("90.00")
THRESHOLD_EFFECTIVE = Decimal("70.00")
THRESHOLD_MODERATELY_EFFECTIVE = Decimal("50.00")


def classify_effectiveness(execution_rate: Decimal) -> ControlEffectiveness:
    """Classify execution rate into effectiveness tier.

    Args:
        execution_rate: Percentage of required instances with execution evidence.

    Returns:
        ControlEffectiveness enum value.
    """
    if execution_rate >= THRESHOLD_HIGHLY_EFFECTIVE:
        return ControlEffectiveness.HIGHLY_EFFECTIVE
    elif execution_rate >= THRESHOLD_EFFECTIVE:
        return ControlEffectiveness.EFFECTIVE
    elif execution_rate >= THRESHOLD_MODERATELY_EFFECTIVE:
        return ControlEffectiveness.MODERATELY_EFFECTIVE
    else:
        return ControlEffectiveness.INEFFECTIVE


def generate_recommendation(
    effectiveness: ControlEffectiveness,
    control_name: str,
    execution_rate: Decimal,
) -> str | None:
    """Generate recommendation for controls below HIGHLY_EFFECTIVE.

    Returns None for HIGHLY_EFFECTIVE controls.
    """
    if effectiveness == ControlEffectiveness.HIGHLY_EFFECTIVE:
        return None
    elif effectiveness == ControlEffectiveness.INEFFECTIVE:
        return (
            f"Control '{control_name}' has an execution rate of {execution_rate}%, "
            f"which is below the 50% threshold. Recommend obtaining additional "
            f"execution evidence through targeted evidence collection and creating "
            f"a shelf data request for missing execution logs."
        )
    elif effectiveness == ControlEffectiveness.MODERATELY_EFFECTIVE:
        return (
            f"Control '{control_name}' has an execution rate of {execution_rate}%, "
            f"which indicates moderate effectiveness. Consider strengthening monitoring "
            f"and evidence collection processes to improve coverage."
        )
    else:
        return (
            f"Control '{control_name}' has an execution rate of {execution_rate}%. "
            f"Effectiveness could be improved by addressing gaps in execution coverage."
        )


class ControlEffectivenessScoringService:
    """Scores control effectiveness from graph evidence."""

    def __init__(self, graph_service: Any) -> None:
        self._graph = graph_service

    async def get_execution_evidence(self, control_id: str, engagement_id: str) -> dict[str, Any]:
        """Query SUPPORTED_BY edges to count execution evidence.

        Returns dict with: total_required, evidenced_count, evidence_ids.
        """
        try:
            query = (
                "MATCH (c:Control)-[:SUPPORTED_BY]->(e:Evidence) "
                "WHERE c.id = $control_id AND c.engagement_id = $engagement_id "
                "RETURN e.id AS evidence_id, e.has_execution_marker AS has_marker"
            )
            records = await self._graph.run_query(query, {"control_id": control_id, "engagement_id": engagement_id})

            evidence_ids = []
            evidenced_count = 0
            total = len(records)

            for r in records:
                eid = r.get("evidence_id")
                if eid:
                    evidence_ids.append(eid)
                if r.get("has_marker", False):
                    evidenced_count += 1

            return {
                "total_required": total,
                "evidenced_count": evidenced_count,
                "evidence_ids": evidence_ids,
            }
        except Exception:
            logger.warning("Failed to query SUPPORTED_BY edges for control %s", control_id)
            return {"total_required": 0, "evidenced_count": 0, "evidence_ids": []}

    async def score_control(
        self,
        control_id: str,
        control_name: str,
        engagement_id: str,
    ) -> dict[str, Any]:
        """Score a single control's effectiveness.

        Returns dict with: effectiveness, execution_rate, evidence_source_ids,
        total_required, evidenced_count, recommendation.
        """
        evidence = await self.get_execution_evidence(control_id, engagement_id)
        total = evidence["total_required"]
        evidenced = evidence["evidenced_count"]

        if total == 0:
            return {
                "effectiveness": ControlEffectiveness.INEFFECTIVE,
                "execution_rate": Decimal("0.00"),
                "evidence_source_ids": [],
                "total_required": 0,
                "evidenced_count": 0,
                "recommendation": generate_recommendation(
                    ControlEffectiveness.INEFFECTIVE,
                    control_name,
                    Decimal("0.00"),
                ),
            }

        rate = (Decimal(evidenced) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))
        effectiveness = classify_effectiveness(rate)
        recommendation = generate_recommendation(effectiveness, control_name, rate)

        return {
            "effectiveness": effectiveness,
            "execution_rate": rate,
            "evidence_source_ids": evidence["evidence_ids"],
            "total_required": total,
            "evidenced_count": evidenced,
            "recommendation": recommendation,
        }
