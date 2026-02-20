"""Scenario ranking with composite scoring.

Ranks scenarios across four dimensions:
  evidence(0.30) + simulation(0.25) + financial(0.25) + governance(0.20)

Weights are configurable via the API.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _evidence_score(scenario: Any) -> float:
    """Compute evidence dimension score from scenario confidence."""
    conf = scenario.evidence_confidence_score
    if conf is not None:
        return min(1.0, max(0.0, conf))
    return 0.0


def _simulation_score(result: Any | None) -> float:
    """Compute simulation dimension score from result metrics."""
    if not result or not result.metrics:
        return 0.0

    metrics = result.metrics
    # Use efficiency_score if available, otherwise average available metrics
    if "efficiency_score" in metrics:
        return min(1.0, max(0.0, float(metrics["efficiency_score"])))

    numeric_values = [
        float(v) for v in metrics.values()
        if isinstance(v, (int, float)) and 0 <= v <= 1
    ]
    if numeric_values:
        return sum(numeric_values) / len(numeric_values)

    return 0.0


def _financial_score(assumptions: list[Any]) -> float:
    """Compute financial dimension score from assumption confidence."""
    if not assumptions:
        return 0.0

    confidences = [a.confidence for a in assumptions]
    return sum(confidences) / len(confidences)


def _governance_score(scenario: Any, result: Any | None) -> float:
    """Compute governance dimension score.

    Based on:
    - Whether the scenario has been executed (completeness)
    - Risk metrics from simulation results
    """
    score = 0.0

    # Executed scenarios get base governance credit
    if result:
        score += 0.5

    # Lower risk score is better governance
    if result and result.metrics:
        risk = result.metrics.get("risk_score", 0.5)
        if isinstance(risk, (int, float)):
            score += 0.5 * (1.0 - min(1.0, max(0.0, float(risk))))
    else:
        score += 0.25  # Default middle score

    return min(1.0, score)


def rank_scenarios(
    scenarios: list[Any],
    results_map: dict[UUID, Any],
    assumptions: list[Any],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    """Rank scenarios by composite score.

    Args:
        scenarios: List of SimulationScenario objects.
        results_map: Map of scenario_id -> latest SimulationResult.
        assumptions: List of FinancialAssumption objects.
        weights: Dict with evidence/simulation/financial/governance weights.

    Returns:
        List of ranking entries sorted by composite score DESC.
    """
    w_ev = weights.get("evidence", 0.30)
    w_sim = weights.get("simulation", 0.25)
    w_fin = weights.get("financial", 0.25)
    w_gov = weights.get("governance", 0.20)

    fin_score = _financial_score(assumptions)

    rankings: list[dict[str, Any]] = []
    for scenario in scenarios:
        result = results_map.get(scenario.id)
        ev = _evidence_score(scenario)
        sim = _simulation_score(result)
        gov = _governance_score(scenario, result)

        composite = (
            w_ev * ev
            + w_sim * sim
            + w_fin * fin_score
            + w_gov * gov
        )

        rankings.append({
            "scenario_id": str(scenario.id),
            "scenario_name": scenario.name,
            "composite_score": round(composite, 4),
            "evidence_score": round(ev, 4),
            "simulation_score": round(sim, 4),
            "financial_score": round(fin_score, 4),
            "governance_score": round(gov, 4),
        })

    rankings.sort(key=lambda r: r["composite_score"], reverse=True)
    return rankings
