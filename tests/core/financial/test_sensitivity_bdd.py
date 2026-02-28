"""BDD tests for the sensitivity analysis engine (Story #364).

Scenario 1: Assumptions ranked by impact
Scenario 2: Tornado chart swing data
Scenario 3: Confidence-weighted P10/P50/P90
Scenario 4: Tornado chart rendering data
"""

from __future__ import annotations

from src.core.financial.sensitivity import (
    AssumptionInput,
    PercentileEstimate,
    TornadoEntry,
    compute_percentile_estimates,
    compute_sensitivity,
    compute_tornado_chart,
)


class TestOATSensitivityRanking:
    """Scenario 1: Assumptions are ranked by impact on total cost estimate."""

    def test_5_assumptions_ranked_by_impact(self) -> None:
        """Given 5 financial assumptions of varying magnitude,
        When sensitivity analysis is run,
        Then assumptions are ranked from highest to lowest impact."""
        assumptions = [
            AssumptionInput(name="transaction_volume", value=100_000, confidence=0.7, confidence_range=30.0),
            AssumptionInput(name="hourly_rate", value=150, confidence=0.9, confidence_range=10.0),
            AssumptionInput(name="license_cost", value=50_000, confidence=0.8, confidence_range=20.0),
            AssumptionInput(name="travel_expenses", value=5_000, confidence=0.6, confidence_range=40.0),
            AssumptionInput(name="misc_overhead", value=2_000, confidence=0.5, confidence_range=15.0),
        ]
        result = compute_sensitivity(assumptions)

        entries = result["entries"]
        assert len(entries) == 5

        # Verify ranking order: each entry has rank 1-5
        ranks = [e["rank"] for e in entries]
        assert ranks == [1, 2, 3, 4, 5]

        # Verify descending swing magnitude
        swings = [e["swing_magnitude"] for e in entries]
        for i in range(len(swings) - 1):
            assert swings[i] >= swings[i + 1]

    def test_each_entry_has_required_fields(self) -> None:
        """Then each entry includes: assumption_name, impact_amount_low, impact_amount_high, rank."""
        assumptions = [
            AssumptionInput(name="cost_a", value=1000, confidence=0.8, confidence_range=20.0),
            AssumptionInput(name="cost_b", value=500, confidence=0.7, confidence_range=30.0),
        ]
        result = compute_sensitivity(assumptions)

        for entry in result["entries"]:
            assert "assumption_name" in entry
            assert "impact_amount_low" in entry
            assert "impact_amount_high" in entry
            assert "rank" in entry

    def test_ranking_uses_absolute_impact(self) -> None:
        """And the ranking uses absolute impact magnitude (not percentage)."""
        # Large value with small % range should rank higher than small value with large % range
        assumptions = [
            AssumptionInput(name="big_value", value=1_000_000, confidence=0.9, confidence_range=5.0),
            AssumptionInput(name="small_value", value=100, confidence=0.5, confidence_range=50.0),
        ]
        result = compute_sensitivity(assumptions)

        # big_value: swing = 1M * 1.05 - 1M * 0.95 = 100_000
        # small_value: swing = 100 * 1.5 - 100 * 0.5 = 100
        assert result["entries"][0]["assumption_name"] == "big_value"
        assert result["entries"][0]["rank"] == 1

    def test_empty_assumptions_returns_empty(self) -> None:
        """Given no assumptions, return empty result."""
        result = compute_sensitivity([])
        assert result["entries"] == []
        assert result["baseline_cost"] == 0.0


class TestTornadoChartData:
    """Scenario 2 & 4: Tornado chart data with swing from low to high."""

    def test_highest_impact_assumption_swing(self) -> None:
        """Given transaction_volume is highest impact,
        When varied by +/-30%,
        Then swing from low to high is expressed in absolute cost delta."""
        assumptions = [
            AssumptionInput(name="transaction_volume", value=100_000, confidence=0.7, confidence_range=30.0),
            AssumptionInput(name="hourly_rate", value=150, confidence=0.9, confidence_range=10.0),
        ]
        entries = compute_tornado_chart(assumptions)

        # transaction_volume has wider absolute swing
        assert entries[0].assumption_name == "transaction_volume"
        assert entries[0].swing_magnitude > 0

        # Swing = high_cost - low_cost
        expected_swing = entries[0].high_cost - entries[0].low_cost
        assert abs(entries[0].swing_magnitude - expected_swing) < 0.01

    def test_tornado_entries_have_all_fields(self) -> None:
        """Then each entry includes: name, baseline_cost, low_cost, high_cost, swing_magnitude."""
        assumptions = [
            AssumptionInput(name="cost_a", value=1000, confidence=0.8, confidence_range=20.0),
        ]
        entries = compute_tornado_chart(assumptions)
        assert len(entries) == 1

        entry = entries[0]
        assert isinstance(entry, TornadoEntry)
        assert entry.assumption_name == "cost_a"
        assert entry.baseline_cost == 1000.0
        assert entry.low_cost < entry.baseline_cost
        assert entry.high_cost > entry.baseline_cost
        assert entry.swing_magnitude > 0
        assert entry.rank == 1

    def test_tornado_sorted_descending_by_swing(self) -> None:
        """Then assumptions are ordered by descending swing magnitude (widest bar first)."""
        assumptions = [
            AssumptionInput(name="small", value=100, confidence=0.9, confidence_range=10.0),
            AssumptionInput(name="large", value=50_000, confidence=0.7, confidence_range=25.0),
            AssumptionInput(name="medium", value=5_000, confidence=0.8, confidence_range=20.0),
        ]
        entries = compute_tornado_chart(assumptions)

        # Verify descending order
        for i in range(len(entries) - 1):
            assert entries[i].swing_magnitude >= entries[i + 1].swing_magnitude

    def test_tornado_entry_to_dict(self) -> None:
        """The response is suitable for rendering without further transformation."""
        entry = TornadoEntry(
            assumption_name="test",
            baseline_cost=1000.0,
            low_cost=800.0,
            high_cost=1200.0,
            swing_magnitude=400.0,
            rank=1,
        )
        d = entry.to_dict()
        assert d["assumption_name"] == "test"
        assert d["baseline_cost"] == 1000.0
        assert d["low_cost"] == 800.0
        assert d["high_cost"] == 1200.0
        assert d["swing_magnitude"] == 400.0
        assert d["rank"] == 1


class TestPercentileEstimates:
    """Scenario 3: Confidence-weighted analysis returns P10/P50/P90 estimates."""

    def test_p10_less_than_p50_less_than_p90(self) -> None:
        """Then p10_cost < p50_cost < p90_cost."""
        assumptions = [
            AssumptionInput(name="vol", value=10_000, confidence=0.7, confidence_range=20.0),
            AssumptionInput(name="rate", value=5_000, confidence=0.8, confidence_range=15.0),
            AssumptionInput(name="overhead", value=3_000, confidence=0.6, confidence_range=25.0),
        ]
        est = compute_percentile_estimates(assumptions)

        assert est.p10 < est.p50
        assert est.p50 < est.p90

    def test_lower_confidence_wider_spread(self) -> None:
        """And assumptions with lower confidence contribute wider spread."""
        # All high confidence → narrow spread
        high_conf = [
            AssumptionInput(name="a", value=10_000, confidence=0.95, confidence_range=20.0),
            AssumptionInput(name="b", value=5_000, confidence=0.95, confidence_range=20.0),
        ]
        # Same ranges but low confidence → wider spread
        low_conf = [
            AssumptionInput(name="a", value=10_000, confidence=0.5, confidence_range=20.0),
            AssumptionInput(name="b", value=5_000, confidence=0.5, confidence_range=20.0),
        ]

        high_est = compute_percentile_estimates(high_conf)
        low_est = compute_percentile_estimates(low_conf)

        # Both should have same P50 (same midpoint values)
        assert abs(high_est.p50 - low_est.p50) < 0.01

        # Low confidence should have wider spread
        high_spread = high_est.p90 - high_est.p10
        low_spread = low_est.p90 - low_est.p10
        assert low_spread > high_spread

    def test_percentile_estimate_to_dict(self) -> None:
        """Percentile estimate serializes correctly."""
        est = PercentileEstimate(p10=100.123, p50=200.456, p90=300.789)
        d = est.to_dict()
        assert d["p10"] == 100.12
        assert d["p50"] == 200.46
        assert d["p90"] == 300.79

    def test_empty_assumptions_returns_zeros(self) -> None:
        """Given no assumptions, all percentiles are zero."""
        est = compute_percentile_estimates([])
        assert est.p10 == 0.0
        assert est.p50 == 0.0
        assert est.p90 == 0.0

    def test_single_high_confidence_assumption(self) -> None:
        """A single assumption at 0.95 confidence produces narrow spread."""
        assumptions = [
            AssumptionInput(name="certain_cost", value=50_000, confidence=0.95, confidence_range=10.0),
        ]
        est = compute_percentile_estimates(assumptions)

        assert est.p50 == 50_000
        # Spread should be narrow because confidence is high
        spread = est.p90 - est.p10
        assert spread < 5_000  # Less than 10% of value


class TestCustomCostFunction:
    """Sensitivity analysis with custom cost functions."""

    def test_multiplicative_cost_function(self) -> None:
        """A multiplicative cost function correctly computes sensitivity."""
        assumptions = [
            AssumptionInput(name="volume", value=1000, confidence=0.8, confidence_range=20.0),
            AssumptionInput(name="unit_cost", value=50, confidence=0.9, confidence_range=10.0),
        ]

        def multiply(values: dict[str, float]) -> float:
            return values["volume"] * values["unit_cost"]

        result = compute_sensitivity(assumptions, cost_function=multiply)

        # Baseline: 1000 * 50 = 50000
        assert result["baseline_cost"] == 50_000.0

        # Volume varied: low = 800*50=40000, high = 1200*50=60000 → swing = 20000
        # Unit cost varied: low = 1000*45=45000, high = 1000*55=55000 → swing = 10000
        # Volume should rank first
        assert result["entries"][0]["assumption_name"] == "volume"

    def test_percentiles_with_custom_function(self) -> None:
        """Percentiles work with custom cost function."""
        assumptions = [
            AssumptionInput(name="vol", value=100, confidence=0.7, confidence_range=30.0),
            AssumptionInput(name="rate", value=10, confidence=0.8, confidence_range=20.0),
        ]

        def multiply(values: dict[str, float]) -> float:
            return values["vol"] * values["rate"]

        est = compute_percentile_estimates(assumptions, cost_function=multiply)
        assert est.p50 == 1000.0  # 100 * 10
        assert est.p10 < est.p50
        assert est.p90 > est.p50


class TestAssumptionBounds:
    """Edge cases for assumption bound computation."""

    def test_zero_confidence_range_uses_fallback(self) -> None:
        """When confidence_range is 0, use confidence-derived fallback."""
        # confidence=0.5 → fallback pct = 0.1 * (1-0.5) = 0.05 = ±5%
        assumptions = [
            AssumptionInput(name="test", value=1000, confidence=0.5, confidence_range=0.0),
        ]
        result = compute_sensitivity(assumptions)
        entry = result["entries"][0]

        # With ±5%: low = 950, high = 1050, swing = 100
        assert abs(entry["low_cost"] - 950.0) < 0.01
        assert abs(entry["high_cost"] - 1050.0) < 0.01

    def test_high_confidence_narrow_fallback(self) -> None:
        """High confidence with no range produces very narrow bounds."""
        assumptions = [
            AssumptionInput(name="test", value=1000, confidence=0.95, confidence_range=0.0),
        ]
        result = compute_sensitivity(assumptions)
        entry = result["entries"][0]

        # confidence=0.95 → fallback pct = 0.1 * 0.05 = 0.005 = ±0.5%
        assert entry["swing_magnitude"] < 20  # Very narrow swing

    def test_negative_assumption_value(self) -> None:
        """Negative values (cost credits/rebates) produce correct swing."""
        assumptions = [
            AssumptionInput(name="rebate", value=-5000, confidence=0.8, confidence_range=20.0),
        ]
        result = compute_sensitivity(assumptions)
        entry = result["entries"][0]

        # value=-5000, ±20%: bounds are -6000 and -4000
        # low_cost should be the smaller value, high_cost the larger
        assert entry["low_cost"] < entry["high_cost"]
        assert entry["swing_magnitude"] > 0
        # Swing should be 2000 (|-4000 - (-6000)|)
        assert abs(entry["swing_magnitude"] - 2000.0) < 0.01
