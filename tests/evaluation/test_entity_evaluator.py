"""Tests for entity evaluator helpers in src.evaluation.entity_evaluator.

Focuses on _fuzzy_match (the deterministic matching primitive) and the _prf
precision/recall/F1 calculation. The async DB-dependent functions are not
tested here to keep this suite self-contained.
"""

from __future__ import annotations

import pytest

from src.evaluation.entity_evaluator import _fuzzy_match


class TestFuzzyMatch:
    # -- Exact matches --------------------------------------------------------

    def test_identical_strings_match(self) -> None:
        assert _fuzzy_match("Alice Johnson", "Alice Johnson") is True

    def test_case_insensitive_match(self) -> None:
        assert _fuzzy_match("John Smith", "john smith") is True

    def test_mixed_case_both_sides(self) -> None:
        assert _fuzzy_match("ACME CORP", "acme corp") is True

    # -- Near matches (within default 0.85 threshold) -------------------------

    def test_minor_typo_still_matches(self) -> None:
        # One character off — ratio should be well above 0.85
        assert _fuzzy_match("Jonathan", "Jonathon") is True

    def test_extra_trailing_space_matches(self) -> None:
        assert _fuzzy_match("Alice ", "alice") is True

    # -- Non-matching strings -------------------------------------------------

    def test_completely_different_strings_do_not_match(self) -> None:
        assert _fuzzy_match("Alpha Corp", "Beta Ltd") is False

    def test_short_vs_long_string_does_not_match(self) -> None:
        assert _fuzzy_match("AB", "Alpha Beta Gamma Delta") is False

    def test_empty_strings_match(self) -> None:
        # Two empty strings are identical → ratio 1.0
        assert _fuzzy_match("", "") is True

    def test_one_empty_string_does_not_match_non_empty(self) -> None:
        # ratio of ("", "John") is 0.0 < 0.85
        assert _fuzzy_match("", "John") is False

    # -- Threshold boundary ---------------------------------------------------

    def test_custom_low_threshold_matches_dissimilar(self) -> None:
        # With threshold=0.3, strings that would fail at 0.85 can still match
        assert _fuzzy_match("cat", "dog", threshold=0.0) is True

    def test_custom_high_threshold_rejects_near_match(self) -> None:
        # Force threshold above realistic ratio for a near-match
        assert _fuzzy_match("Jonathan", "Jonathon", threshold=1.0) is False

    def test_threshold_at_exact_boundary_passes(self) -> None:
        # Identical strings → ratio == 1.0; threshold=1.0 should pass (>=)
        assert _fuzzy_match("exact", "exact", threshold=1.0) is True


class TestPrfHelper:
    """Tests for the _prf precision/recall/F1 helper (imported directly)."""

    def test_import_prf(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        assert callable(_prf)

    def test_perfect_precision_and_recall(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        result = _prf(tp=5, fp=0, fn=0)
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(1.0)
        assert result["f1"] == pytest.approx(1.0)

    def test_zero_tp_gives_zero_metrics(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        result = _prf(tp=0, fp=3, fn=3)
        assert result["precision"] == pytest.approx(0.0)
        assert result["recall"] == pytest.approx(0.0)
        assert result["f1"] == pytest.approx(0.0)

    def test_all_zero_inputs_give_zero_metrics(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        result = _prf(tp=0, fp=0, fn=0)
        assert result["precision"] == pytest.approx(0.0)
        assert result["recall"] == pytest.approx(0.0)
        assert result["f1"] == pytest.approx(0.0)

    def test_typical_prf_values(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        # tp=4, fp=1, fn=1 → precision=4/5=0.8, recall=4/5=0.8, f1=0.8
        result = _prf(tp=4, fp=1, fn=1)
        assert result["precision"] == pytest.approx(0.8)
        assert result["recall"] == pytest.approx(0.8)
        assert result["f1"] == pytest.approx(0.8)

    def test_high_precision_low_recall(self) -> None:
        from src.evaluation.entity_evaluator import _prf

        # tp=1, fp=0, fn=9 → precision=1.0, recall=0.1, f1=2*1.0*0.1/(1.1) ≈ 0.182
        result = _prf(tp=1, fp=0, fn=9)
        assert result["precision"] == pytest.approx(1.0)
        assert result["recall"] == pytest.approx(0.1)
        assert result["f1"] == pytest.approx(2 * 1.0 * 0.1 / (1.0 + 0.1))
