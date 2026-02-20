"""Tests for scenario ranking with composite scoring."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from src.simulation.ranking import (
    _evidence_score,
    _financial_score,
    _governance_score,
    _simulation_score,
    rank_scenarios,
)


def _make_scenario(
    name: str = "Test",
    confidence: float | None = 0.7,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        evidence_confidence_score=confidence,
    )


def _make_result(
    metrics: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(metrics=metrics or {})


def _make_assumption(confidence: float = 0.8) -> SimpleNamespace:
    return SimpleNamespace(confidence=confidence)


class TestEvidenceScore:
    def test_normal_value(self) -> None:
        s = _make_scenario(confidence=0.85)
        assert _evidence_score(s) == 0.85

    def test_none_confidence(self) -> None:
        s = _make_scenario(confidence=None)
        assert _evidence_score(s) == 0.0

    def test_clamped_high(self) -> None:
        s = _make_scenario(confidence=1.5)
        assert _evidence_score(s) == 1.0

    def test_clamped_low(self) -> None:
        s = _make_scenario(confidence=-0.1)
        assert _evidence_score(s) == 0.0


class TestSimulationScore:
    def test_no_result(self) -> None:
        assert _simulation_score(None) == 0.0

    def test_empty_metrics(self) -> None:
        r = _make_result({})
        assert _simulation_score(r) == 0.0

    def test_efficiency_score_present(self) -> None:
        r = _make_result({"efficiency_score": 0.8})
        assert _simulation_score(r) == 0.8

    def test_average_of_numeric_metrics(self) -> None:
        r = _make_result({"a": 0.6, "b": 0.4})
        assert abs(_simulation_score(r) - 0.5) < 0.001

    def test_non_numeric_ignored(self) -> None:
        r = _make_result({"text": "hello", "score": 0.7})
        assert _simulation_score(r) == 0.7


class TestFinancialScore:
    def test_empty_assumptions(self) -> None:
        assert _financial_score([]) == 0.0

    def test_single_assumption(self) -> None:
        assert _financial_score([_make_assumption(0.9)]) == 0.9

    def test_averaged(self) -> None:
        assumptions = [_make_assumption(0.8), _make_assumption(0.6)]
        assert abs(_financial_score(assumptions) - 0.7) < 0.001

    def test_with_cost_ratio_under_budget(self) -> None:
        """cost_ratio < 1.0 means under budget → high score."""
        r = _make_result({"cost_ratio": 0.8})
        score = _financial_score([], r)
        assert score > 0.5

    def test_with_cost_ratio_over_budget(self) -> None:
        """cost_ratio > 1.0 means over budget → lower score."""
        r = _make_result({"cost_ratio": 2.0})
        score = _financial_score([], r)
        assert score < 0.5

    def test_cost_ratio_blended_with_assumptions(self) -> None:
        """When both assumptions and cost_ratio present, score is blended."""
        r = _make_result({"cost_ratio": 0.8})
        score_with = _financial_score([_make_assumption(0.9)], r)
        score_without = _financial_score([_make_assumption(0.9)])
        # Blended score should differ from assumption-only
        assert score_with != score_without

    def test_cost_efficiency_used_as_fallback(self) -> None:
        r = _make_result({"cost_efficiency": 0.75})
        score = _financial_score([], r)
        assert abs(score - 0.75) < 0.001


class TestGovernanceScore:
    def test_no_result(self) -> None:
        s = _make_scenario()
        score = _governance_score(s, None)
        assert score == 0.25  # default middle

    def test_with_result_low_risk(self) -> None:
        s = _make_scenario()
        r = _make_result({"risk_score": 0.0})
        score = _governance_score(s, r)
        assert score == 1.0  # 0.5 base + 0.5 * (1.0 - 0.0)

    def test_with_result_high_risk(self) -> None:
        s = _make_scenario()
        r = _make_result({"risk_score": 1.0})
        score = _governance_score(s, r)
        assert score == 0.5  # 0.5 base + 0.5 * 0.0

    def test_capped_at_one(self) -> None:
        s = _make_scenario()
        r = _make_result({"risk_score": -1.0})
        assert _governance_score(s, r) <= 1.0


class TestRankScenarios:
    def test_empty_scenarios(self) -> None:
        result = rank_scenarios([], {}, [], {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2})
        assert result == []

    def test_single_scenario(self) -> None:
        s = _make_scenario("Alpha", 0.8)
        result = rank_scenarios(
            [s], {}, [], {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2}
        )
        assert len(result) == 1
        assert result[0]["scenario_name"] == "Alpha"
        assert "composite_score" in result[0]

    def test_sorted_descending(self) -> None:
        s1 = _make_scenario("Low", 0.2)
        s2 = _make_scenario("High", 0.9)
        result = rank_scenarios(
            [s1, s2],
            {},
            [],
            {"evidence": 1.0, "simulation": 0.0, "financial": 0.0, "governance": 0.0},
        )
        assert result[0]["scenario_name"] == "High"
        assert result[1]["scenario_name"] == "Low"

    def test_custom_weights(self) -> None:
        s = _make_scenario("Test", 0.5)
        assumptions = [_make_assumption(1.0)]
        result_ev = rank_scenarios(
            [s],
            {},
            assumptions,
            {"evidence": 1.0, "simulation": 0.0, "financial": 0.0, "governance": 0.0},
        )
        result_fin = rank_scenarios(
            [s],
            {},
            assumptions,
            {"evidence": 0.0, "simulation": 0.0, "financial": 1.0, "governance": 0.0},
        )
        # With full weight on evidence (0.5) vs financial (1.0)
        assert result_ev[0]["composite_score"] != result_fin[0]["composite_score"]

    def test_response_keys(self) -> None:
        s = _make_scenario("Key Test", 0.7)
        result = rank_scenarios(
            [s], {}, [], {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2}
        )
        entry = result[0]
        expected_keys = {
            "scenario_id",
            "scenario_name",
            "composite_score",
            "evidence_score",
            "simulation_score",
            "financial_score",
            "governance_score",
        }
        assert set(entry.keys()) == expected_keys

    def test_scores_rounded(self) -> None:
        s = _make_scenario("Round", 0.777)
        result = rank_scenarios(
            [s], {}, [], {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2}
        )
        entry = result[0]
        # All scores should be rounded to 4 decimal places
        for key in ["composite_score", "evidence_score", "simulation_score", "financial_score", "governance_score"]:
            val = entry[key]
            assert val == round(val, 4)
