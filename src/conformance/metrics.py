"""Conformance metrics and deviation classification."""

from __future__ import annotations

from dataclasses import dataclass

from src.conformance.checker import ConformanceCheckResult, Deviation


@dataclass
class ConformanceMetrics:
    """Aggregated conformance metrics."""

    fitness: float
    precision: float
    f1_score: float
    deviation_count: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    deviation_breakdown: dict[str, int]


def calculate_metrics(result: ConformanceCheckResult) -> ConformanceMetrics:
    """Calculate aggregated metrics from a conformance check result."""
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    type_counts: dict[str, int] = {}

    for dev in result.deviations:
        severity_counts[dev.severity] = severity_counts.get(dev.severity, 0) + 1
        type_counts[dev.deviation_type] = type_counts.get(dev.deviation_type, 0) + 1

    f = result.fitness_score
    p = result.precision_score
    f1 = 2 * f * p / (f + p) if (f + p) > 0 else 0.0

    return ConformanceMetrics(
        fitness=f,
        precision=p,
        f1_score=round(f1, 4),
        deviation_count=len(result.deviations),
        high_severity_count=severity_counts["high"],
        medium_severity_count=severity_counts["medium"],
        low_severity_count=severity_counts["low"],
        deviation_breakdown=type_counts,
    )


def classify_deviation_impact(deviation: Deviation) -> str:
    """Classify the business impact of a deviation."""
    if deviation.deviation_type == "missing_activity":
        return "compliance_risk"
    elif deviation.deviation_type == "extra_activity":
        return "efficiency_concern"
    elif deviation.deviation_type == "sequence_mismatch":
        return "process_variant"
    elif deviation.deviation_type == "different_path":
        return "control_gap"
    return "informational"
