"""Evidence grading progression computation (Story #357).

Computes per-version grade distributions and improvement rates.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default KPI target: >20% improvement per validation cycle
DEFAULT_IMPROVEMENT_TARGET = 20.0

# Grade ordinal for comparison (higher = better)
GRADE_ORDINAL: dict[str, int] = {
    "U": 0,
    "D": 1,
    "C": 2,
    "B": 3,
    "A": 4,
}


@dataclass
class GradeDistribution:
    """Grade distribution for a single POV version."""

    version_number: int
    pov_version_id: str
    grade_u: int
    grade_d: int
    grade_c: int
    grade_b: int
    grade_a: int
    total_elements: int
    improvement_pct: float | None
    snapshot_at: str


def compute_improvement_rate(
    prior_grades: dict[str, int],
    current_grades: dict[str, int],
    element_grade_pairs: list[tuple[str, str, str]] | None = None,
) -> float:
    """Compute the improvement percentage between two versions.

    Args:
        prior_grades: Grade counts for the prior version {U, D, C, B, A}.
        current_grades: Grade counts for the current version.
        element_grade_pairs: Optional list of (element_id, prior_grade, current_grade)
            for exact per-element comparison. If not provided, uses aggregate comparison.

    Returns:
        Improvement percentage (0-100).
    """
    if element_grade_pairs:
        # Exact per-element comparison
        total = len(element_grade_pairs)
        if total == 0:
            return 0.0
        promoted = sum(
            1 for _, prior, current in element_grade_pairs
            if GRADE_ORDINAL.get(current, 0) > GRADE_ORDINAL.get(prior, 0)
        )
        return (promoted / total) * 100

    # Aggregate comparison: count how many elements shifted up
    prior_total = sum(prior_grades.values())
    if prior_total == 0:
        return 0.0

    # Compute weighted grade score for each version
    prior_score = sum(
        GRADE_ORDINAL.get(g, 0) * count for g, count in prior_grades.items()
    )
    current_score = sum(
        GRADE_ORDINAL.get(g, 0) * count for g, count in current_grades.items()
    )

    # Improvement = net upward shifts / total elements
    max_possible = prior_total * 4  # All elements at A
    if max_possible == prior_score:
        return 0.0  # Already all at max

    score_diff = current_score - prior_score
    if score_diff <= 0:
        return 0.0

    # Normalize to percentage of elements that effectively moved up one grade
    return (score_diff / prior_total) * 100


def compute_grade_distributions(
    snapshots: list[dict[str, int | str | float | None]],
) -> list[GradeDistribution]:
    """Compute grade distributions with improvement rates.

    Args:
        snapshots: List of snapshot dicts with grade counts, ordered by version_number.

    Returns:
        List of GradeDistribution with computed improvement percentages.
    """
    results: list[GradeDistribution] = []

    for i, snap in enumerate(snapshots):
        improvement: float | None = None

        if i > 0:
            prior = snapshots[i - 1]
            prior_grades = {
                "U": int(prior.get("grade_u", 0) or 0),
                "D": int(prior.get("grade_d", 0) or 0),
                "C": int(prior.get("grade_c", 0) or 0),
                "B": int(prior.get("grade_b", 0) or 0),
                "A": int(prior.get("grade_a", 0) or 0),
            }
            current_grades = {
                "U": int(snap.get("grade_u", 0) or 0),
                "D": int(snap.get("grade_d", 0) or 0),
                "C": int(snap.get("grade_c", 0) or 0),
                "B": int(snap.get("grade_b", 0) or 0),
                "A": int(snap.get("grade_a", 0) or 0),
            }
            improvement = compute_improvement_rate(prior_grades, current_grades)

        results.append(
            GradeDistribution(
                version_number=int(snap.get("version_number", 0) or 0),
                pov_version_id=str(snap.get("pov_version_id", "")),
                grade_u=int(snap.get("grade_u", 0) or 0),
                grade_d=int(snap.get("grade_d", 0) or 0),
                grade_c=int(snap.get("grade_c", 0) or 0),
                grade_b=int(snap.get("grade_b", 0) or 0),
                grade_a=int(snap.get("grade_a", 0) or 0),
                total_elements=int(snap.get("total_elements", 0) or 0),
                improvement_pct=improvement,
                snapshot_at=str(snap.get("snapshot_at", "")),
            )
        )

    return results
