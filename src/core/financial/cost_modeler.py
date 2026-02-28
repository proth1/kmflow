"""Cost modeling service with interval arithmetic (Story #359).

Computes staffing costs and volume-based processing costs as ranges,
not point estimates. Supports seasonal quarterly projections and
FTE savings delta between as-is and to-be scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CostRange:
    """A cost range with low, mid, and high estimates."""

    low: float
    mid: float
    high: float

    def __add__(self, other: CostRange) -> CostRange:
        return CostRange(
            low=self.low + other.low,
            mid=self.mid + other.mid,
            high=self.high + other.high,
        )

    def __sub__(self, other: CostRange) -> CostRange:
        return CostRange(
            low=self.low - other.high,
            mid=self.mid - other.mid,
            high=self.high - other.low,
        )

    def scale(self, factor: float) -> CostRange:
        """Multiply all components by a scalar."""
        return CostRange(
            low=self.low * factor,
            mid=self.mid * factor,
            high=self.high * factor,
        )

    def to_dict(self) -> dict[str, float]:
        return {"low": round(self.low, 2), "mid": round(self.mid, 2), "high": round(self.high, 2)}


def compute_staffing_cost(
    role_rates: list[dict[str, Any]],
    task_assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute staffing cost ranges per role and aggregate.

    Args:
        role_rates: List of dicts with keys: role_name, hourly_rate, rate_variance_pct.
        task_assignments: List of dicts with keys: role_name, task_count, avg_hours_per_task.

    Returns:
        Dict with per-role cost ranges and an aggregate total.
    """
    rate_lookup: dict[str, dict[str, float]] = {}
    for rr in role_rates:
        variance = rr.get("rate_variance_pct", 0.0) / 100.0
        rate = rr["hourly_rate"]
        rate_lookup[rr["role_name"]] = {
            "low": rate * (1 - variance),
            "mid": rate,
            "high": rate * (1 + variance),
        }

    per_role: dict[str, CostRange] = {}
    total = CostRange(0, 0, 0)

    for ta in task_assignments:
        role = ta["role_name"]
        hours = ta["task_count"] * ta["avg_hours_per_task"]
        rates = rate_lookup.get(role)
        if not rates:
            continue
        role_cost = CostRange(
            low=hours * rates["low"],
            mid=hours * rates["mid"],
            high=hours * rates["high"],
        )
        per_role[role] = per_role.get(role, CostRange(0, 0, 0)) + role_cost
        total = total + role_cost

    return {
        "per_role": {role: cr.to_dict() for role, cr in per_role.items()},
        "total": total.to_dict(),
    }


def compute_volume_cost(
    baseline_volume: int,
    variance_pct: float,
    per_transaction_cost: float,
) -> dict[str, Any]:
    """Compute processing cost range from volume forecast with variance.

    Args:
        baseline_volume: Baseline transaction count per period.
        variance_pct: Variance percentage (e.g. 15.0 for ±15%).
        per_transaction_cost: Cost per transaction.

    Returns:
        Dict with volume range and cost range.
    """
    factor = variance_pct / 100.0
    vol_low = baseline_volume * (1 - factor)
    vol_high = baseline_volume * (1 + factor)

    cost_range = CostRange(
        low=vol_low * per_transaction_cost,
        mid=baseline_volume * per_transaction_cost,
        high=vol_high * per_transaction_cost,
    )
    return {
        "volume_range": {"low": vol_low, "mid": baseline_volume, "high": vol_high},
        "cost_range": cost_range.to_dict(),
    }


def compute_quarterly_projections(
    baseline_volume: int,
    variance_pct: float,
    seasonal_factors: dict[str, float],
    per_transaction_cost: float,
) -> dict[str, Any]:
    """Compute quarterly cost ranges applying seasonal adjustment factors.

    Args:
        baseline_volume: Baseline monthly volume.
        variance_pct: Variance percentage on volume.
        seasonal_factors: Dict with Q1, Q2, Q3, Q4 as percentage of baseline
                          (e.g. {"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115}).
        per_transaction_cost: Cost per transaction.

    Returns:
        Dict with quarterly cost ranges and annual total.
    """
    factor = variance_pct / 100.0
    quarters: dict[str, dict[str, Any]] = {}
    annual_total = CostRange(0, 0, 0)

    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        seasonal_pct = seasonal_factors.get(quarter, 100.0) / 100.0
        q_volume = baseline_volume * seasonal_pct

        q_cost = CostRange(
            low=q_volume * (1 - factor) * per_transaction_cost,
            mid=q_volume * per_transaction_cost,
            high=q_volume * (1 + factor) * per_transaction_cost,
        )
        quarters[quarter] = {
            "volume_mid": q_volume,
            "cost_range": q_cost.to_dict(),
        }
        annual_total = annual_total + q_cost

    return {
        "quarters": quarters,
        "annual_total": annual_total.to_dict(),
    }


def compute_fte_savings(
    role_rates: list[dict[str, Any]],
    as_is_tasks: list[dict[str, Any]],
    to_be_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute FTE savings delta between as-is and to-be scenarios.

    Args:
        role_rates: Role rate definitions.
        as_is_tasks: Task assignments in the as-is scenario.
        to_be_tasks: Task assignments in the to-be scenario.

    Returns:
        Dict with per-role savings ranges and aggregate savings.
    """
    as_is = compute_staffing_cost(role_rates, as_is_tasks)
    to_be = compute_staffing_cost(role_rates, to_be_tasks)

    as_is_total = CostRange(**as_is["total"])
    to_be_total = CostRange(**to_be["total"])
    savings = as_is_total - to_be_total

    per_role_savings: dict[str, dict[str, float]] = {}
    all_roles = set(as_is["per_role"].keys()) | set(to_be["per_role"].keys())
    for role in all_roles:
        as_is_role = CostRange(**(as_is["per_role"].get(role, {"low": 0, "mid": 0, "high": 0})))
        to_be_role = CostRange(**(to_be["per_role"].get(role, {"low": 0, "mid": 0, "high": 0})))
        role_savings = as_is_role - to_be_role
        per_role_savings[role] = role_savings.to_dict()

    return {
        "as_is_total": as_is_total.to_dict(),
        "to_be_total": to_be_total.to_dict(),
        "savings": savings.to_dict(),
        "per_role_savings": per_role_savings,
    }
