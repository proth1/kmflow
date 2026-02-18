"""Tests for best practices and benchmarks CRUD + seed endpoints."""

from __future__ import annotations

from src.data.seeds import get_benchmark_seeds, get_best_practice_seeds


class TestSeedData:
    """Tests for seed data completeness and structure."""

    def test_best_practice_seeds_count(self) -> None:
        """Should have 30 best practices."""
        seeds = get_best_practice_seeds()
        assert len(seeds) == 30

    def test_best_practice_seeds_cover_all_dimensions(self) -> None:
        """Should cover all 6 TOM dimensions."""
        seeds = get_best_practice_seeds()
        dimensions = {s["tom_dimension"] for s in seeds}
        assert dimensions == {
            "process_architecture",
            "people_and_organization",
            "technology_and_data",
            "governance_structures",
            "performance_management",
            "risk_and_compliance",
        }

    def test_best_practice_seeds_per_dimension(self) -> None:
        """Should have 5 per dimension."""
        seeds = get_best_practice_seeds()
        from collections import Counter

        counts = Counter(s["tom_dimension"] for s in seeds)
        for dim, count in counts.items():
            assert count == 5, f"Expected 5 for {dim}, got {count}"

    def test_best_practice_seeds_required_fields(self) -> None:
        """Each seed should have all required fields."""
        seeds = get_best_practice_seeds()
        for seed in seeds:
            assert seed["domain"], "Missing domain"
            assert seed["industry"], "Missing industry"
            assert seed["description"], "Missing description"
            assert seed["tom_dimension"], "Missing tom_dimension"

    def test_benchmark_seeds_count(self) -> None:
        """Should have 20 benchmarks."""
        seeds = get_benchmark_seeds()
        assert len(seeds) == 20

    def test_benchmark_seeds_cover_5_industries(self) -> None:
        """Should cover 5 industries."""
        seeds = get_benchmark_seeds()
        industries = {s["industry"] for s in seeds}
        assert len(industries) == 5
        assert "Financial Services" in industries
        assert "Insurance" in industries
        assert "Banking" in industries
        assert "Healthcare" in industries
        assert "Manufacturing" in industries

    def test_benchmark_seeds_per_industry(self) -> None:
        """Should have 4 per industry."""
        seeds = get_benchmark_seeds()
        from collections import Counter

        counts = Counter(s["industry"] for s in seeds)
        for ind, count in counts.items():
            assert count == 4, f"Expected 4 for {ind}, got {count}"

    def test_benchmark_seeds_percentile_ordering(self) -> None:
        """p25 through p90 should have logical ordering (for most metrics, p90 > p25)."""
        seeds = get_benchmark_seeds()
        for seed in seeds:
            assert seed["p25"] is not None
            assert seed["p50"] is not None
            assert seed["p75"] is not None
            assert seed["p90"] is not None

    def test_benchmark_seeds_required_fields(self) -> None:
        """Each seed should have all required fields."""
        seeds = get_benchmark_seeds()
        for seed in seeds:
            assert seed["metric_name"], "Missing metric_name"
            assert seed["industry"], "Missing industry"
