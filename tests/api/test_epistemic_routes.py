"""Tests for epistemic action planner service."""

from __future__ import annotations

from src.simulation.epistemic import (
    MAX_PROJECTED_CONFIDENCE,
    calculate_confidence_uplift,
    compute_information_gain,
)


class TestCalculateConfidenceUplift:
    """Tests for the uplift calculation function."""

    def test_zero_confidence_gets_uplift(self) -> None:
        uplift, projected = calculate_confidence_uplift(0.0, 0, 1.0)
        assert uplift > 0.0
        assert projected > 0.0

    def test_high_confidence_small_uplift(self) -> None:
        uplift, projected = calculate_confidence_uplift(0.9, 3, 1.0)
        assert uplift < 0.1

    def test_projected_capped_at_max(self) -> None:
        _, projected = calculate_confidence_uplift(0.0, 0, 1.0)
        assert projected <= MAX_PROJECTED_CONFIDENCE

    def test_type_weight_scales_uplift(self) -> None:
        uplift_high, _ = calculate_confidence_uplift(0.3, 0, 1.0)
        uplift_low, _ = calculate_confidence_uplift(0.3, 0, 0.3)
        assert uplift_high > uplift_low

    def test_more_sources_reduce_uplift(self) -> None:
        uplift_few, _ = calculate_confidence_uplift(0.3, 1, 1.0)
        uplift_many, _ = calculate_confidence_uplift(0.3, 5, 1.0)
        assert uplift_few > uplift_many


class TestComputeInformationGain:
    """Tests for information gain computation."""

    def test_zero_uplift(self) -> None:
        assert compute_information_gain(0.0, 0.5) == 0.0

    def test_positive_uplift_positive_gain(self) -> None:
        gain = compute_information_gain(0.2, 0.5)
        assert gain > 0.0

    def test_higher_cascade_higher_gain(self) -> None:
        gain_low = compute_information_gain(0.2, 0.1)
        gain_high = compute_information_gain(0.2, 0.9)
        assert gain_high > gain_low

    def test_gain_rounded(self) -> None:
        gain = compute_information_gain(0.15, 0.33)
        assert gain == round(gain, 4)
