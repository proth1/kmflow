"""BDD tests for Cost-Per-Role and Volume Forecast Modeling (Story #359).

Tests the 4 acceptance scenarios:
1. Per-scenario staffing cost range from role rates and task counts
2. Volume forecast variance propagates into processing cost range
3. Seasonal patterns produce quarterly volume projections
4. Role removal produces FTE savings range
"""

from __future__ import annotations

from src.core.financial.cost_modeler import (
    CostRange,
    compute_fte_savings,
    compute_quarterly_projections,
    compute_staffing_cost,
    compute_volume_cost,
)


class TestStaffingCostRange:
    """Scenario 1: Per-scenario staffing cost range from role rates and task counts."""

    def test_computes_range_from_rates_and_tasks(self) -> None:
        """Given role rates with variance and task assignments, produces a range."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
            {"role_name": "Manager", "hourly_rate": 175.0, "rate_variance_pct": 15.0},
        ]
        task_assignments = [
            {"role_name": "Analyst", "task_count": 5, "avg_hours_per_task": 2.0},
            {"role_name": "Manager", "task_count": 2, "avg_hours_per_task": 1.0},
        ]

        result = compute_staffing_cost(role_rates, task_assignments)

        # Returns range, not point estimate
        assert "total" in result
        total = result["total"]
        assert total["low"] < total["mid"] < total["high"]

        # Per-role breakdown
        assert "Analyst" in result["per_role"]
        assert "Manager" in result["per_role"]

    def test_analyst_cost_range_reflects_variance(self) -> None:
        """Analyst cost range reflects ±10% rate variance."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
        ]
        task_assignments = [
            {"role_name": "Analyst", "task_count": 5, "avg_hours_per_task": 2.0},
        ]

        result = compute_staffing_cost(role_rates, task_assignments)
        analyst = result["per_role"]["Analyst"]

        # 10 hours * $100 = $1000 mid
        # 10 hours * $90 = $900 low
        # 10 hours * $110 = $1100 high
        assert analyst["mid"] == 1000.0
        assert analyst["low"] == 900.0
        assert analyst["high"] == 1100.0

    def test_distinguishes_roles(self) -> None:
        """Output distinguishes Analyst cost range from Manager cost range."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
            {"role_name": "Manager", "hourly_rate": 175.0, "rate_variance_pct": 15.0},
        ]
        task_assignments = [
            {"role_name": "Analyst", "task_count": 5, "avg_hours_per_task": 2.0},
            {"role_name": "Manager", "task_count": 2, "avg_hours_per_task": 1.0},
        ]

        result = compute_staffing_cost(role_rates, task_assignments)
        assert result["per_role"]["Analyst"]["mid"] != result["per_role"]["Manager"]["mid"]


class TestVolumeCostRange:
    """Scenario 2: Volume forecast variance propagates into processing cost range."""

    def test_volume_variance_propagates_to_cost(self) -> None:
        """±15% volume variance maps to proportional cost range."""
        result = compute_volume_cost(
            baseline_volume=1000,
            variance_pct=15.0,
            per_transaction_cost=10.0,
        )

        cost = result["cost_range"]
        # 850 * $10 = $8,500 low
        # 1000 * $10 = $10,000 mid
        # 1150 * $10 = $11,500 high
        assert cost["low"] == 8500.0
        assert cost["mid"] == 10000.0
        assert cost["high"] == 11500.0

    def test_volume_range_reflects_span(self) -> None:
        """Volume range shows 850–1150 transaction span for ±15%."""
        result = compute_volume_cost(
            baseline_volume=1000,
            variance_pct=15.0,
            per_transaction_cost=10.0,
        )

        vol = result["volume_range"]
        assert vol["low"] == 850.0
        assert vol["mid"] == 1000
        assert vol["high"] == 1150.0

    def test_shows_low_mid_high(self) -> None:
        """Cost output shows low, mid, and high estimates."""
        result = compute_volume_cost(
            baseline_volume=1000,
            variance_pct=15.0,
            per_transaction_cost=10.0,
        )

        cost = result["cost_range"]
        assert "low" in cost
        assert "mid" in cost
        assert "high" in cost
        assert cost["low"] < cost["mid"] < cost["high"]


class TestSeasonalQuarterlyProjections:
    """Scenario 3: Seasonal patterns produce quarterly volume projections."""

    def test_four_quarterly_ranges(self) -> None:
        """Four quarterly cost ranges are produced."""
        result = compute_quarterly_projections(
            baseline_volume=1000,
            variance_pct=10.0,
            seasonal_factors={"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115},
            per_transaction_cost=10.0,
        )

        assert len(result["quarters"]) == 4
        for q in ("Q1", "Q2", "Q3", "Q4"):
            assert q in result["quarters"]
            assert "cost_range" in result["quarters"][q]

    def test_q4_higher_than_q1(self) -> None:
        """Q4 range is higher than Q1 range (115% vs 80%)."""
        result = compute_quarterly_projections(
            baseline_volume=1000,
            variance_pct=10.0,
            seasonal_factors={"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115},
            per_transaction_cost=10.0,
        )

        q1_mid = result["quarters"]["Q1"]["cost_range"]["mid"]
        q4_mid = result["quarters"]["Q4"]["cost_range"]["mid"]
        assert q4_mid > q1_mid

    def test_annual_total_is_sum(self) -> None:
        """Annual total range is the sum of the four quarterly ranges."""
        result = compute_quarterly_projections(
            baseline_volume=1000,
            variance_pct=10.0,
            seasonal_factors={"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115},
            per_transaction_cost=10.0,
        )

        expected_mid = sum(
            result["quarters"][q]["cost_range"]["mid"] for q in ("Q1", "Q2", "Q3", "Q4")
        )
        assert abs(result["annual_total"]["mid"] - expected_mid) < 0.01


class TestFteSavings:
    """Scenario 4: Role removal produces FTE savings range."""

    def test_fte_savings_as_range(self) -> None:
        """Delta is expressed as a savings range, not a fixed number."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
        ]
        as_is_tasks = [
            {"role_name": "Analyst", "task_count": 4, "avg_hours_per_task": 2.0},
        ]
        to_be_tasks = [
            {"role_name": "Analyst", "task_count": 2, "avg_hours_per_task": 2.0},
        ]

        result = compute_fte_savings(role_rates, as_is_tasks, to_be_tasks)
        savings = result["savings"]

        assert "low" in savings
        assert "mid" in savings
        assert "high" in savings

    def test_savings_accounts_for_rate_uncertainty(self) -> None:
        """Savings range accounts for the Analyst hourly rate uncertainty."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
        ]
        as_is_tasks = [
            {"role_name": "Analyst", "task_count": 4, "avg_hours_per_task": 2.0},
        ]
        to_be_tasks = [
            {"role_name": "Analyst", "task_count": 2, "avg_hours_per_task": 2.0},
        ]

        result = compute_fte_savings(role_rates, as_is_tasks, to_be_tasks)
        savings = result["savings"]

        # Savings low and high differ due to interval subtraction
        assert savings["low"] != savings["high"]
        # Mid savings = 4 hours * $100 = $400
        assert savings["mid"] == 400.0

    def test_per_role_savings(self) -> None:
        """Output includes per-role savings breakdown."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
        ]
        as_is_tasks = [
            {"role_name": "Analyst", "task_count": 4, "avg_hours_per_task": 2.0},
        ]
        to_be_tasks = [
            {"role_name": "Analyst", "task_count": 2, "avg_hours_per_task": 2.0},
        ]

        result = compute_fte_savings(role_rates, as_is_tasks, to_be_tasks)
        assert "Analyst" in result["per_role_savings"]

    def test_output_labels_as_range(self) -> None:
        """Output clearly expresses the delta as a range (low/mid/high)."""
        role_rates = [
            {"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
        ]
        as_is = [{"role_name": "Analyst", "task_count": 4, "avg_hours_per_task": 2.0}]
        to_be = [{"role_name": "Analyst", "task_count": 2, "avg_hours_per_task": 2.0}]

        result = compute_fte_savings(role_rates, as_is, to_be)
        # Savings has low/mid/high — this is a range, not a single number
        savings = result["savings"]
        assert len(savings) == 3
        assert set(savings.keys()) == {"low", "mid", "high"}


class TestCostRangeDataclass:
    """CostRange dataclass used consistently."""

    def test_addition(self) -> None:
        a = CostRange(10, 20, 30)
        b = CostRange(5, 10, 15)
        c = a + b
        assert c == CostRange(15, 30, 45)

    def test_subtraction_uses_interval_arithmetic(self) -> None:
        """Subtraction: a.low - b.high, a.mid - b.mid, a.high - b.low."""
        a = CostRange(90, 100, 110)
        b = CostRange(40, 50, 60)
        c = a - b
        assert c == CostRange(30, 50, 70)

    def test_scale(self) -> None:
        a = CostRange(10, 20, 30)
        b = a.scale(2.0)
        assert b == CostRange(20, 40, 60)

    def test_to_dict(self) -> None:
        a = CostRange(10.001, 20.006, 30.009)
        d = a.to_dict()
        assert d == {"low": 10.0, "mid": 20.01, "high": 30.01}
