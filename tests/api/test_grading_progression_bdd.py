"""BDD tests for Evidence Grading Progression Tracking (Story #357).

Tests all three acceptance scenarios from the GitHub issue.
"""

from __future__ import annotations

import pytest

from src.validation.grading_progression import (
    DEFAULT_IMPROVEMENT_TARGET,
    GRADE_ORDINAL,
    compute_grade_distributions,
    compute_improvement_rate,
)

# ── Scenario 1: Per-Cycle Improvement Calculation ──────────────────────


class TestPerCycleImprovement:
    """Given POV v1 has 10 elements with Grade D
      And after one validation cycle 3 elements are promoted to Grade C
    When the grading progression is computed
    Then the improvement rate is reported as 30% (3 of 10 promoted)
      And the per-version grade distribution shows v1: {D:10} and v2: {D:7, C:3}
    """

    def test_exact_element_comparison_30_pct(self) -> None:
        """3 of 10 elements promoted from D to C = 30%."""
        pairs = [
            ("e1", "D", "C"),
            ("e2", "D", "C"),
            ("e3", "D", "C"),
            ("e4", "D", "D"),
            ("e5", "D", "D"),
            ("e6", "D", "D"),
            ("e7", "D", "D"),
            ("e8", "D", "D"),
            ("e9", "D", "D"),
            ("e10", "D", "D"),
        ]
        rate = compute_improvement_rate({}, {}, element_grade_pairs=pairs)
        assert rate == pytest.approx(30.0)

    def test_aggregate_improvement(self) -> None:
        """Using aggregate grade counts: D:10 -> D:7,C:3 = 30%."""
        prior = {"U": 0, "D": 10, "C": 0, "B": 0, "A": 0}
        current = {"U": 0, "D": 7, "C": 3, "B": 0, "A": 0}
        rate = compute_improvement_rate(prior, current)
        assert rate == pytest.approx(30.0)

    def test_grade_distribution_snapshots(self) -> None:
        """Verify per-version distribution includes both versions."""
        snapshots = [
            {
                "version_number": 1,
                "pov_version_id": "pov_v1",
                "grade_u": 0, "grade_d": 10, "grade_c": 0, "grade_b": 0, "grade_a": 0,
                "total_elements": 10,
                "snapshot_at": "2026-02-01",
            },
            {
                "version_number": 2,
                "pov_version_id": "pov_v2",
                "grade_u": 0, "grade_d": 7, "grade_c": 3, "grade_b": 0, "grade_a": 0,
                "total_elements": 10,
                "snapshot_at": "2026-02-10",
            },
        ]

        result = compute_grade_distributions(snapshots)
        assert len(result) == 2

        # First version has no improvement (no prior)
        assert result[0].version_number == 1
        assert result[0].grade_d == 10
        assert result[0].improvement_pct is None

        # Second version shows improvement
        assert result[1].version_number == 2
        assert result[1].grade_d == 7
        assert result[1].grade_c == 3
        assert result[1].improvement_pct == pytest.approx(30.0)

    def test_100_percent_improvement(self) -> None:
        """All elements promoted by one grade."""
        prior = {"U": 0, "D": 0, "C": 10, "B": 0, "A": 0}
        current = {"U": 0, "D": 0, "C": 0, "B": 10, "A": 0}
        rate = compute_improvement_rate(prior, current)
        assert rate == pytest.approx(100.0)

    def test_zero_percent_improvement(self) -> None:
        """No elements promoted."""
        prior = {"U": 0, "D": 5, "C": 5, "B": 0, "A": 0}
        current = {"U": 0, "D": 5, "C": 5, "B": 0, "A": 0}
        rate = compute_improvement_rate(prior, current)
        assert rate == pytest.approx(0.0)

    def test_all_at_grade_a_no_improvement_possible(self) -> None:
        """All elements at A already — 0% possible improvement."""
        prior = {"U": 0, "D": 0, "C": 0, "B": 0, "A": 10}
        current = {"U": 0, "D": 0, "C": 0, "B": 0, "A": 10}
        rate = compute_improvement_rate(prior, current)
        assert rate == pytest.approx(0.0)

    def test_empty_prior_zero_elements(self) -> None:
        """Edge case: prior version has 0 elements."""
        prior = {"U": 0, "D": 0, "C": 0, "B": 0, "A": 0}
        current = {"U": 0, "D": 0, "C": 5, "B": 0, "A": 0}
        rate = compute_improvement_rate(prior, current)
        assert rate == pytest.approx(0.0)


# ── Scenario 2: Grade Progression API ─────────────────────────────────


class TestGradeProgressionAPI:
    """Given an engagement with 2 completed POV versions
    When GET /api/v1/validation/grading-progression is called
    Then per-version grade distribution data is returned
      And each version entry includes counts for grades U, D, C, B, A
      And the improvement percentage from prior version is included
    """

    def test_distributions_have_all_grades(self) -> None:
        snapshots = [
            {
                "version_number": 1,
                "pov_version_id": "pov_1",
                "grade_u": 2, "grade_d": 3, "grade_c": 3, "grade_b": 1, "grade_a": 1,
                "total_elements": 10,
                "snapshot_at": "2026-02-01",
            },
        ]
        result = compute_grade_distributions(snapshots)
        d = result[0]
        assert d.grade_u == 2
        assert d.grade_d == 3
        assert d.grade_c == 3
        assert d.grade_b == 1
        assert d.grade_a == 1
        assert d.total_elements == 10

    def test_first_version_no_improvement(self) -> None:
        snapshots = [
            {
                "version_number": 1,
                "pov_version_id": "pov_1",
                "grade_u": 5, "grade_d": 5, "grade_c": 0, "grade_b": 0, "grade_a": 0,
                "total_elements": 10,
                "snapshot_at": "2026-02-01",
            },
        ]
        result = compute_grade_distributions(snapshots)
        assert result[0].improvement_pct is None

    def test_improvement_target_default(self) -> None:
        assert DEFAULT_IMPROVEMENT_TARGET == 20.0


# ── Scenario 3: Multi-Cycle Trend Visualization Data ──────────────────


class TestMultiCycleTrend:
    """Given an engagement with 4 POV versions showing grade progression
    When the trend data is retrieved
    Then the grade distribution shift across all 4 versions is included
      And the data is structured for stacked bar chart rendering
    """

    def test_four_version_trend(self) -> None:
        snapshots = [
            {
                "version_number": 1, "pov_version_id": "v1",
                "grade_u": 10, "grade_d": 0, "grade_c": 0, "grade_b": 0, "grade_a": 0,
                "total_elements": 10, "snapshot_at": "2026-01-01",
            },
            {
                "version_number": 2, "pov_version_id": "v2",
                "grade_u": 5, "grade_d": 5, "grade_c": 0, "grade_b": 0, "grade_a": 0,
                "total_elements": 10, "snapshot_at": "2026-01-15",
            },
            {
                "version_number": 3, "pov_version_id": "v3",
                "grade_u": 2, "grade_d": 3, "grade_c": 5, "grade_b": 0, "grade_a": 0,
                "total_elements": 10, "snapshot_at": "2026-02-01",
            },
            {
                "version_number": 4, "pov_version_id": "v4",
                "grade_u": 0, "grade_d": 1, "grade_c": 3, "grade_b": 4, "grade_a": 2,
                "total_elements": 10, "snapshot_at": "2026-02-15",
            },
        ]

        result = compute_grade_distributions(snapshots)
        assert len(result) == 4

        # First version has no improvement
        assert result[0].improvement_pct is None

        # Each subsequent version shows positive improvement
        for i in range(1, 4):
            assert result[i].improvement_pct is not None
            assert result[i].improvement_pct > 0

    def test_stacked_bar_chart_data_structure(self) -> None:
        """Each version has distinct counts for U/D/C/B/A — chart-ready."""
        snapshots = [
            {
                "version_number": 1, "pov_version_id": "v1",
                "grade_u": 4, "grade_d": 3, "grade_c": 2, "grade_b": 1, "grade_a": 0,
                "total_elements": 10, "snapshot_at": "2026-02-01",
            },
        ]
        result = compute_grade_distributions(snapshots)
        d = result[0]
        # Sum of all grades equals total_elements
        assert d.grade_u + d.grade_d + d.grade_c + d.grade_b + d.grade_a == d.total_elements


# ── Grade Ordinal Mapping ─────────────────────────────────────────────


class TestGradeOrdinal:
    """Verify the ordinal ranking of evidence grades."""

    def test_ordinal_ordering(self) -> None:
        assert GRADE_ORDINAL["U"] < GRADE_ORDINAL["D"]
        assert GRADE_ORDINAL["D"] < GRADE_ORDINAL["C"]
        assert GRADE_ORDINAL["C"] < GRADE_ORDINAL["B"]
        assert GRADE_ORDINAL["B"] < GRADE_ORDINAL["A"]

    def test_all_grades_present(self) -> None:
        assert set(GRADE_ORDINAL.keys()) == {"U", "D", "C", "B", "A"}
