"""Tests for success metrics API and seed data."""

from __future__ import annotations

from src.data.seed_metrics import get_metric_seeds


class TestMetricSeedData:
    """Tests for metric seed data completeness and structure."""

    def test_metric_seeds_count(self) -> None:
        """Should have 15 metric definitions."""
        seeds = get_metric_seeds()
        assert len(seeds) == 15

    def test_metric_seeds_cover_all_categories(self) -> None:
        """Should cover all 6 metric categories."""
        seeds = get_metric_seeds()
        categories = {s["category"] for s in seeds}
        assert categories == {
            "process_efficiency",
            "quality",
            "compliance",
            "customer_satisfaction",
            "cost",
            "timeliness",
        }

    def test_metric_seeds_required_fields(self) -> None:
        """Each seed should have all required fields."""
        seeds = get_metric_seeds()
        for seed in seeds:
            assert seed["name"], "Missing name"
            assert seed["unit"], "Missing unit"
            assert seed["target_value"] is not None, "Missing target_value"
            assert seed["category"], "Missing category"

    def test_metric_seeds_positive_targets(self) -> None:
        """All target values should be positive."""
        seeds = get_metric_seeds()
        for seed in seeds:
            assert seed["target_value"] > 0, f"{seed['name']} has non-positive target"

    def test_metric_seeds_unique_names(self) -> None:
        """All metric names should be unique."""
        seeds = get_metric_seeds()
        names = [s["name"] for s in seeds]
        assert len(names) == len(set(names)), "Duplicate metric names found"

    def test_metric_category_distribution(self) -> None:
        """Should have reasonable distribution across categories."""
        seeds = get_metric_seeds()
        from collections import Counter

        counts = Counter(s["category"] for s in seeds)
        # At least 2 per category
        for cat, count in counts.items():
            assert count >= 2, f"Category {cat} has only {count} metrics"
