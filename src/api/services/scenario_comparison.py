"""Scenario comparison service for side-by-side analysis (Story #383).

Compares 2-5 scenarios across key metrics: simulation results,
evidence confidence, compliance impact, and governance coverage.
Highlights best/worst values per metric for consultant decision-making.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.simulation import (
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
)

logger = logging.getLogger(__name__)

MIN_SCENARIOS = 2
MAX_SCENARIOS = 5


class ScenarioComparisonService:
    """Builds side-by-side comparison data for multiple scenarios."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compare_scenarios(
        self,
        scenario_ids: list[uuid.UUID],
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compare 2-5 scenarios across key metrics.

        Returns comparison data with per-metric best/worst flags.
        Raises ValueError if any scenario has no completed simulation.
        """
        # Load all scenarios
        scenarios = await self._load_scenarios(scenario_ids, engagement_id)
        if len(scenarios) != len(scenario_ids):
            found_ids = {s.id for s in scenarios}
            missing = [str(sid) for sid in scenario_ids if sid not in found_ids]
            raise ValueError(f"Scenarios not found: {', '.join(missing)}")

        # Load simulation results
        results = await self._load_simulation_results(scenario_ids)
        incomplete = [str(sid) for sid in scenario_ids if sid not in results]
        if incomplete:
            raise ValueError(f"Scenarios without completed simulation: {', '.join(incomplete)}")

        # Load modification counts for compliance impact
        compliance_removals = await self._count_control_removals(scenario_ids)

        # Build comparison entries
        entries = []
        for scenario in scenarios:
            sim_result = results[scenario.id]
            metrics = sim_result.metrics or {}

            cycle_time_delta = metrics.get("cycle_time_delta_pct", 0.0)
            fte_delta = metrics.get("fte_delta", 0.0)
            avg_confidence = scenario.evidence_confidence_score or 0.0
            removals = compliance_removals.get(scenario.id, 0)
            # Governance coverage: 10%-per-removal heuristic. This is a simplified
            # approximation until the compliance-tagged element model is available,
            # at which point the true ratio (remaining/total) should be used.
            governance_coverage = max(0.0, 100.0 - (removals * 10.0))

            entries.append(
                {
                    "scenario_id": str(scenario.id),
                    "name": scenario.name,
                    "metrics": {
                        "cycle_time_delta_pct": cycle_time_delta,
                        "fte_delta": fte_delta,
                        "avg_confidence": avg_confidence,
                        "governance_coverage_pct": governance_coverage,
                        "compliance_flags": removals,
                    },
                }
            )

        # Compute best/worst flags
        self._annotate_best_worst(entries)

        return {"scenarios": entries, "count": len(entries)}

    async def _load_scenarios(
        self,
        scenario_ids: list[uuid.UUID],
        engagement_id: uuid.UUID,
    ) -> list[SimulationScenario]:
        """Load scenarios by IDs, scoped to engagement."""
        stmt = select(SimulationScenario).where(
            SimulationScenario.id.in_(scenario_ids),
            SimulationScenario.engagement_id == engagement_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _load_simulation_results(
        self,
        scenario_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, SimulationResult]:
        """Load completed simulation results keyed by scenario_id."""
        stmt = (
            select(SimulationResult)
            .where(
                SimulationResult.scenario_id.in_(scenario_ids),
                SimulationResult.status == SimulationStatus.COMPLETED,
            )
            .order_by(SimulationResult.completed_at.desc())
        )
        result = await self._session.execute(stmt)
        results = result.scalars().all()
        return {r.scenario_id: r for r in results}

    async def _count_control_removals(
        self,
        scenario_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Count CONTROL_REMOVE modifications per scenario."""
        stmt = (
            select(
                ScenarioModification.scenario_id,
                sa_func.count().label("removal_count"),
            )
            .where(
                ScenarioModification.scenario_id.in_(scenario_ids),
                ScenarioModification.modification_type == ModificationType.CONTROL_REMOVE,
            )
            .group_by(ScenarioModification.scenario_id)
        )
        result = await self._session.execute(stmt)
        return {row.scenario_id: row.removal_count for row in result}

    def _annotate_best_worst(self, entries: list[dict[str, Any]]) -> None:
        """Add best/worst flags per metric across all scenarios.

        Best: highest cycle_time_delta (most improvement), lowest fte_delta,
        highest avg_confidence, highest governance_coverage, lowest compliance_flags.
        """
        if len(entries) < 2:
            return

        metric_comparators = {
            "cycle_time_delta_pct": "min_is_best",  # Most negative = most improvement (-25% > -5%)
            "fte_delta": "min_is_best",  # Most negative = greatest efficiency gain
            "avg_confidence": "max_is_best",
            "governance_coverage_pct": "max_is_best",
            "compliance_flags": "min_is_best",
        }

        for metric_key, direction in metric_comparators.items():
            values = [e["metrics"][metric_key] for e in entries]
            if direction == "max_is_best":
                best_val = max(values)
                worst_val = min(values)
            else:
                best_val = min(values)
                worst_val = max(values)

            for entry in entries:
                val = entry["metrics"][metric_key]
                flags = entry["metrics"].setdefault("flags", {})
                if val == best_val and best_val != worst_val:
                    flags[metric_key] = "best"
                elif val == worst_val and best_val != worst_val:
                    flags[metric_key] = "worst"
