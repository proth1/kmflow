"""Tests for pure IR metric functions in src.evaluation.retrieval_evaluator.

All tests are deterministic (no LLM or DB calls). Each function is tested
against expected values derived from hand-calculation.
"""

from __future__ import annotations

import math

import pytest

from src.evaluation.retrieval_evaluator import (
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestPrecisionAtK:
    def test_two_hits_in_five_at_k5(self) -> None:
        retrieved = ["a", "b", "c", "d", "e"]
        expected = {"a", "c"}
        assert precision_at_k(retrieved, expected, 5) == pytest.approx(0.4)

    def test_two_hits_in_three_at_k3(self) -> None:
        retrieved = ["a", "b", "c", "d", "e"]
        expected = {"a", "c"}
        assert precision_at_k(retrieved, expected, 3) == pytest.approx(2 / 3)

    def test_zero_hits(self) -> None:
        retrieved = ["a", "b", "c"]
        expected = {"x", "y"}
        assert precision_at_k(retrieved, expected, 3) == pytest.approx(0.0)

    def test_all_hits(self) -> None:
        retrieved = ["a", "b", "c"]
        expected = {"a", "b", "c"}
        assert precision_at_k(retrieved, expected, 3) == pytest.approx(1.0)

    def test_k_zero_returns_zero(self) -> None:
        assert precision_at_k(["a", "b"], {"a"}, 0) == 0.0

    def test_k_larger_than_retrieved(self) -> None:
        # k=10 but only 3 retrieved — top_k is capped at len(retrieved)
        retrieved = ["a", "b", "c"]
        expected = {"a"}
        # 1 hit / 10 = 0.1
        assert precision_at_k(retrieved, expected, 10) == pytest.approx(0.1)

    def test_empty_retrieved(self) -> None:
        assert precision_at_k([], {"a"}, 5) == pytest.approx(0.0)

    def test_empty_expected(self) -> None:
        assert precision_at_k(["a", "b"], set(), 2) == pytest.approx(0.0)


class TestRecallAtK:
    def test_two_of_three_relevant_at_k5(self) -> None:
        retrieved = ["a", "b", "c", "d", "e"]
        expected = {"a", "c", "f"}
        assert recall_at_k(retrieved, expected, 5) == pytest.approx(2 / 3)

    def test_all_relevant_retrieved(self) -> None:
        retrieved = ["a", "b", "c"]
        expected = {"a", "b"}
        assert recall_at_k(retrieved, expected, 3) == pytest.approx(1.0)

    def test_none_retrieved(self) -> None:
        retrieved = ["x", "y", "z"]
        expected = {"a", "b"}
        assert recall_at_k(retrieved, expected, 3) == pytest.approx(0.0)

    def test_k_zero_returns_zero(self) -> None:
        assert recall_at_k(["a", "b"], {"a"}, 0) == 0.0

    def test_empty_expected_returns_zero(self) -> None:
        assert recall_at_k(["a", "b", "c"], set(), 3) == 0.0

    def test_empty_retrieved(self) -> None:
        assert recall_at_k([], {"a", "b"}, 5) == pytest.approx(0.0)


class TestMeanReciprocalRank:
    def test_first_relevant_at_rank_2(self) -> None:
        # "b" is not relevant, "a" is — first hit at rank 2
        assert mean_reciprocal_rank(["b", "a", "c"], {"a"}) == pytest.approx(0.5)

    def test_first_relevant_at_rank_1(self) -> None:
        assert mean_reciprocal_rank(["a", "b", "c"], {"a"}) == pytest.approx(1.0)

    def test_no_relevant_returns_zero(self) -> None:
        assert mean_reciprocal_rank(["b", "c", "d"], {"a"}) == pytest.approx(0.0)

    def test_relevant_at_rank_3(self) -> None:
        assert mean_reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1.0 / 3)

    def test_multiple_relevant_uses_first_hit(self) -> None:
        # "b" is relevant at rank 2; "a" is relevant at rank 3
        # MRR uses only the first relevant hit → 1/2
        assert mean_reciprocal_rank(["x", "b", "a"], {"a", "b"}) == pytest.approx(0.5)

    def test_empty_retrieved(self) -> None:
        assert mean_reciprocal_rank([], {"a"}) == 0.0

    def test_empty_expected(self) -> None:
        assert mean_reciprocal_rank(["a", "b"], set()) == 0.0


class TestNdcgAtK:
    def test_two_relevant_at_positions_1_and_3_k3(self) -> None:
        # retrieved = ["a", "b", "c"], relevant = {"a", "c"}
        # gains at positions 1,2,3: [1, 0, 1]
        # discounts: 1/log2(2), 1/log2(3), 1/log2(4)
        # dcg = 1/log2(2) + 0 + 1/log2(4) = 1.0 + 0.5 = 1.5
        # ideal: both relevant at positions 1,2 → 1/log2(2) + 1/log2(3)
        # idcg = 1.0 + 1/log2(3) ≈ 1.6309
        # ndcg ≈ 1.5 / 1.6309 ≈ 0.919
        result = ndcg_at_k(["a", "b", "c"], {"a", "c"}, 3)
        assert result > 0.0
        assert result <= 1.0

    def test_perfect_ranking_returns_one(self) -> None:
        # All relevant docs at top
        result = ndcg_at_k(["a", "b"], {"a", "b"}, 2)
        assert result == pytest.approx(1.0)

    def test_no_relevant_in_retrieved_returns_zero(self) -> None:
        result = ndcg_at_k(["x", "y", "z"], {"a", "b"}, 3)
        assert result == pytest.approx(0.0)

    def test_k_zero_returns_zero(self) -> None:
        assert ndcg_at_k(["a", "b"], {"a"}, 0) == 0.0

    def test_empty_expected_returns_zero(self) -> None:
        assert ndcg_at_k(["a", "b"], set(), 2) == 0.0

    def test_empty_retrieved_returns_zero(self) -> None:
        assert ndcg_at_k([], {"a"}, 5) == 0.0

    def test_single_relevant_at_rank_1(self) -> None:
        # DCG = 1/log2(2) = 1.0, IDCG = 1/log2(2) = 1.0 → NDCG = 1.0
        result = ndcg_at_k(["a", "b", "c"], {"a"}, 3)
        assert result == pytest.approx(1.0)

    def test_single_relevant_at_rank_2(self) -> None:
        # DCG = 1/log2(3) ≈ 0.631, IDCG = 1/log2(2) = 1.0 → NDCG ≈ 0.631
        result = ndcg_at_k(["b", "a", "c"], {"a"}, 3)
        expected = 1.0 / math.log2(3)  # rank 2 → log2(3)
        assert result == pytest.approx(expected)

    def test_ndcg_decreases_as_relevant_moves_further_down(self) -> None:
        """Relevant doc at rank 1 should give higher NDCG than at rank 3."""
        score_rank1 = ndcg_at_k(["a", "b", "c", "d"], {"a"}, 4)
        score_rank3 = ndcg_at_k(["b", "c", "a", "d"], {"a"}, 4)
        assert score_rank1 > score_rank3
