"""Sensitivity analysis engine for financial estimates (Story #364).

One-at-a-time (OAT) sensitivity analysis: for each assumption, hold
others at midpoint and vary the target from its low to high bound.
Produces tornado chart data and confidence-weighted P10/P50/P90 estimates.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssumptionInput:
    """A financial assumption with its range for sensitivity analysis."""

    name: str
    value: float  # midpoint / baseline
    confidence: float  # 0.0 to 1.0
    confidence_range: float  # ± percentage (e.g. 20.0 for ±20%)


@dataclass(frozen=True)
class TornadoEntry:
    """A single bar in the tornado chart."""

    assumption_name: str
    baseline_cost: float
    low_cost: float
    high_cost: float
    swing_magnitude: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_name": self.assumption_name,
            "baseline_cost": round(self.baseline_cost, 2),
            "low_cost": round(self.low_cost, 2),
            "high_cost": round(self.high_cost, 2),
            "swing_magnitude": round(self.swing_magnitude, 2),
            "rank": self.rank,
        }


@dataclass(frozen=True)
class PercentileEstimate:
    """P10/P50/P90 cost estimates."""

    p10: float
    p50: float
    p90: float

    def to_dict(self) -> dict[str, float]:
        return {
            "p10": round(self.p10, 2),
            "p50": round(self.p50, 2),
            "p90": round(self.p90, 2),
        }


def _default_cost_function(values: dict[str, float]) -> float:
    """Default cost function: sum of all assumption values."""
    return sum(values.values())


def _assumption_bounds(assumption: AssumptionInput) -> tuple[float, float]:
    """Compute low and high bounds for an assumption.

    Uses confidence_range as +/- percentage. If confidence_range is 0,
    uses a default +/-10% range scaled by (1 - confidence).
    """
    if assumption.confidence_range > 0:
        pct = assumption.confidence_range / 100.0
    else:
        # Fallback: derive range from confidence level
        pct = 0.1 * (1.0 - assumption.confidence)

    low = assumption.value * (1.0 - pct)
    high = assumption.value * (1.0 + pct)
    return low, high


def compute_sensitivity(
    assumptions: list[AssumptionInput],
    cost_function: Callable[[dict[str, float]], float] | None = None,
) -> dict[str, Any]:
    """Run OAT sensitivity analysis over a set of financial assumptions.

    For each assumption, vary it from its low to high bound while holding
    all others at their midpoint value. Rank assumptions by swing magnitude.

    Args:
        assumptions: List of financial assumptions with ranges.
        cost_function: Optional callable(dict[str, float]) -> float that
            computes cost from assumption values. Defaults to summing values.

    Returns:
        Dict with tornado entries ranked by impact and impact amounts.
    """
    if not assumptions:
        return {"entries": [], "baseline_cost": 0.0}

    fn = cost_function or _default_cost_function

    # Baseline: all assumptions at midpoint
    baseline_values = {a.name: a.value for a in assumptions}
    baseline_cost = fn(baseline_values)

    # OAT: vary each assumption while holding others at midpoint
    entries: list[dict[str, Any]] = []
    for assumption in assumptions:
        low_bound, high_bound = _assumption_bounds(assumption)

        low_values = {**baseline_values, assumption.name: low_bound}
        high_values = {**baseline_values, assumption.name: high_bound}

        low_cost = fn(low_values)
        high_cost = fn(high_values)

        # Ensure low_cost <= high_cost for consistent swing
        if low_cost > high_cost:
            low_cost, high_cost = high_cost, low_cost

        swing = high_cost - low_cost
        entries.append({
            "assumption_name": assumption.name,
            "baseline_cost": baseline_cost,
            "low_cost": low_cost,
            "high_cost": high_cost,
            "swing_magnitude": swing,
            "impact_amount_low": low_cost - baseline_cost,
            "impact_amount_high": high_cost - baseline_cost,
        })

    # Rank by descending swing magnitude
    entries.sort(key=lambda e: e["swing_magnitude"], reverse=True)
    for i, entry in enumerate(entries):
        entry["rank"] = i + 1

    return {
        "entries": entries,
        "baseline_cost": round(baseline_cost, 2),
    }


def compute_tornado_chart(
    assumptions: list[AssumptionInput],
    cost_function: Callable[[dict[str, float]], float] | None = None,
) -> list[TornadoEntry]:
    """Produce tornado chart data sorted by descending swing.

    Returns a list of TornadoEntry objects ready for chart rendering.
    """
    result = compute_sensitivity(assumptions, cost_function)
    return [
        TornadoEntry(
            assumption_name=e["assumption_name"],
            baseline_cost=e["baseline_cost"],
            low_cost=e["low_cost"],
            high_cost=e["high_cost"],
            swing_magnitude=e["swing_magnitude"],
            rank=e["rank"],
        )
        for e in result["entries"]
    ]


def compute_percentile_estimates(
    assumptions: list[AssumptionInput],
    cost_function: Callable[[dict[str, float]], float] | None = None,
) -> PercentileEstimate:
    """Compute confidence-weighted P10/P50/P90 cost estimates.

    Uses a simplified variance aggregation approach:
    - Each assumption contributes variance proportional to its range
      and inversely proportional to its confidence.
    - Lower confidence -> wider contribution to percentile spread.
    - Assumes approximate normality via central limit theorem for
      aggregation of multiple independent assumption ranges.

    Args:
        assumptions: Financial assumptions with confidence levels.
        cost_function: Optional cost function. Defaults to sum.

    Returns:
        PercentileEstimate with p10, p50, p90 values.
    """
    if not assumptions:
        return PercentileEstimate(p10=0.0, p50=0.0, p90=0.0)

    fn = cost_function or _default_cost_function

    # P50 is baseline (all midpoints)
    baseline_values = {a.name: a.value for a in assumptions}
    p50 = fn(baseline_values)

    # Compute total variance from all assumptions
    total_variance = 0.0
    for assumption in assumptions:
        low_bound, high_bound = _assumption_bounds(assumption)

        # Use OAT to get cost impact of this assumption's range
        low_values = {**baseline_values, assumption.name: low_bound}
        high_values = {**baseline_values, assumption.name: high_bound}
        low_cost = fn(low_values)
        high_cost = fn(high_values)

        cost_range = abs(high_cost - low_cost)

        # Confidence weighting: lower confidence -> wider effective range
        # At confidence=1.0, the assumption is certain (no contribution)
        # At confidence=0.5, full range contributes
        confidence_weight = 1.0 - assumption.confidence
        effective_range = cost_range * confidence_weight

        # Model as uniform distribution: variance = range^2 / 12
        total_variance += (effective_range ** 2) / 12.0

    std_dev = math.sqrt(total_variance)

    # Z-scores for P10 and P90 (1.282 for 90th percentile of normal)
    z_90 = 1.282
    p10 = p50 - z_90 * std_dev
    p90 = p50 + z_90 * std_dev

    return PercentileEstimate(p10=p10, p50=p50, p90=p90)
