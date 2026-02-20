"""Financial impact estimation for simulation scenarios.

Computes cost ranges (optimistic/expected/pessimistic) using financial
assumptions, performs sensitivity analysis, and calculates delta vs baseline.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Variance multipliers for cost range estimation
OPTIMISTIC_FACTOR = 0.75
PESSIMISTIC_FACTOR = 1.40

# Sensitivity perturbation (percentage change for analysis)
SENSITIVITY_PERTURBATION = 0.20  # +/- 20%


def compute_financial_impact(
    assumptions: list[Any],
    baseline_expected: float | None = None,
) -> dict[str, Any]:
    """Compute financial impact from assumptions.

    Args:
        assumptions: List of FinancialAssumption ORM objects.
        baseline_expected: If provided, computes delta_vs_baseline as
            (this scenario's expected cost - baseline).

    Returns:
        Dict with cost_range, sensitivity_analysis, and delta_vs_baseline.
    """
    if not assumptions:
        return {
            "cost_range": {"optimistic": 0.0, "expected": 0.0, "pessimistic": 0.0},
            "sensitivity_analysis": [],
            "delta_vs_baseline": None,
        }

    # Calculate expected total cost
    expected_total = sum(a.value for a in assumptions)
    confidence_weighted_total = sum(a.value * a.confidence for a in assumptions)

    # Cost ranges: adjusted by confidence
    avg_confidence = confidence_weighted_total / expected_total if expected_total else 0.5
    optimistic = expected_total * OPTIMISTIC_FACTOR * max(0.5, avg_confidence)
    pessimistic = expected_total * PESSIMISTIC_FACTOR * (2.0 - avg_confidence)

    cost_range = {
        "optimistic": round(optimistic, 2),
        "expected": round(expected_total, 2),
        "pessimistic": round(pessimistic, 2),
    }

    # Sensitivity analysis: how each assumption affects the total
    sensitivity: list[dict[str, Any]] = []
    for a in assumptions:
        delta = a.value * SENSITIVITY_PERTURBATION
        sensitivity.append(
            {
                "assumption_name": a.name,
                "base_value": a.value,
                "impact_range": {
                    "optimistic": round(expected_total - delta, 2),
                    "expected": round(expected_total, 2),
                    "pessimistic": round(expected_total + delta, 2),
                },
            }
        )

    # Sort by impact magnitude (largest delta first)
    sensitivity.sort(
        key=lambda s: abs(s["base_value"]),
        reverse=True,
    )

    baseline_delta: float | None = None
    if baseline_expected is not None:
        baseline_delta = round(expected_total - baseline_expected, 2)

    return {
        "cost_range": cost_range,
        "sensitivity_analysis": sensitivity,
        "delta_vs_baseline": baseline_delta,
    }
