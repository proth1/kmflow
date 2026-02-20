"""Tests for financial impact estimation."""

from __future__ import annotations

from types import SimpleNamespace

from src.simulation.financial import (
    OPTIMISTIC_FACTOR,
    PESSIMISTIC_FACTOR,
    SENSITIVITY_PERTURBATION,
    compute_financial_impact,
)


def _make_assumption(name: str, value: float, confidence: float) -> SimpleNamespace:
    return SimpleNamespace(name=name, value=value, confidence=confidence)


class TestComputeFinancialImpact:
    """Tests for compute_financial_impact."""

    def test_empty_assumptions(self) -> None:
        result = compute_financial_impact([])
        assert result["cost_range"]["optimistic"] == 0.0
        assert result["cost_range"]["expected"] == 0.0
        assert result["cost_range"]["pessimistic"] == 0.0
        assert result["sensitivity_analysis"] == []
        assert result["delta_vs_baseline"] is None

    def test_single_assumption(self) -> None:
        a = _make_assumption("Dev Cost", 100_000, 0.9)
        result = compute_financial_impact([a])

        assert result["cost_range"]["expected"] == 100_000.0
        assert result["cost_range"]["optimistic"] < result["cost_range"]["expected"]
        assert result["cost_range"]["pessimistic"] > result["cost_range"]["expected"]

    def test_multiple_assumptions(self) -> None:
        assumptions = [
            _make_assumption("Dev", 80_000, 0.9),
            _make_assumption("Infra", 20_000, 0.7),
        ]
        result = compute_financial_impact(assumptions)
        assert result["cost_range"]["expected"] == 100_000.0

    def test_optimistic_less_than_expected(self) -> None:
        a = _make_assumption("Cost", 50_000, 0.8)
        result = compute_financial_impact([a])
        assert result["cost_range"]["optimistic"] < result["cost_range"]["expected"]

    def test_pessimistic_greater_than_expected(self) -> None:
        a = _make_assumption("Cost", 50_000, 0.8)
        result = compute_financial_impact([a])
        assert result["cost_range"]["pessimistic"] > result["cost_range"]["expected"]

    def test_sensitivity_analysis_count(self) -> None:
        assumptions = [
            _make_assumption("A", 10_000, 0.8),
            _make_assumption("B", 5_000, 0.6),
        ]
        result = compute_financial_impact(assumptions)
        assert len(result["sensitivity_analysis"]) == 2

    def test_sensitivity_sorted_by_base_value(self) -> None:
        assumptions = [
            _make_assumption("Small", 1_000, 0.8),
            _make_assumption("Large", 50_000, 0.9),
        ]
        result = compute_financial_impact(assumptions)
        entries = result["sensitivity_analysis"]
        assert entries[0]["base_value"] >= entries[1]["base_value"]

    def test_sensitivity_impact_range(self) -> None:
        a = _make_assumption("Cost", 10_000, 0.8)
        result = compute_financial_impact([a])
        entry = result["sensitivity_analysis"][0]
        delta = a.value * SENSITIVITY_PERTURBATION
        assert entry["impact_range"]["optimistic"] == round(10_000 - delta, 2)
        assert entry["impact_range"]["pessimistic"] == round(10_000 + delta, 2)

    def test_delta_vs_baseline_is_none(self) -> None:
        a = _make_assumption("Cost", 10_000, 0.8)
        result = compute_financial_impact([a])
        assert result["delta_vs_baseline"] is None

    def test_high_confidence_tighter_range(self) -> None:
        high = compute_financial_impact([_make_assumption("A", 100_000, 1.0)])
        low = compute_financial_impact([_make_assumption("A", 100_000, 0.5)])
        high_spread = high["cost_range"]["pessimistic"] - high["cost_range"]["optimistic"]
        low_spread = low["cost_range"]["pessimistic"] - low["cost_range"]["optimistic"]
        assert high_spread < low_spread

    def test_constants_reasonable(self) -> None:
        assert 0.5 <= OPTIMISTIC_FACTOR <= 1.0
        assert PESSIMISTIC_FACTOR > 1.0
        assert 0.0 < SENSITIVITY_PERTURBATION < 1.0
