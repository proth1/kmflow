"""Monitoring dashboard aggregation service (Story #371).

Aggregates monitoring metrics for a single engagement dashboard view:
- Agent statuses and health
- Deviation counts by severity
- Evidence flow rate
- Alert summary
- Compliance score trend over date range
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentStatusSummary:
    """Summary of monitoring agent health statuses."""

    total: int = 0
    healthy: int = 0
    degraded: int = 0
    unhealthy: int = 0
    agents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DeviationSummary:
    """Deviation counts by severity."""

    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


@dataclass
class AlertSummary:
    """Alert status summary."""

    total_open: int = 0
    new: int = 0
    acknowledged: int = 0
    critical_open: int = 0


@dataclass
class ComplianceDataPoint:
    """A single compliance score data point."""

    date: str
    score: float


@dataclass
class ComplianceTrend:
    """Compliance score trend over time."""

    current_score: float = 0.0
    trend_direction: str = "flat"  # "up", "down", "flat"
    data_points: list[ComplianceDataPoint] = field(default_factory=list)


@dataclass
class DashboardData:
    """Complete monitoring dashboard data."""

    engagement_id: str
    date_from: str
    date_to: str
    agent_status: AgentStatusSummary
    deviations: DeviationSummary
    evidence_flow_rate: float  # items/min over last 5 minutes
    alerts: AlertSummary
    compliance_trend: ComplianceTrend


def compute_trend_direction(scores: list[float], window: int = 7) -> str:
    """Compute trend direction from recent compliance scores.

    Args:
        scores: Chronologically ordered list of scores.
        window: Number of recent points to consider for trend.

    Returns:
        "up", "down", or "flat".
    """
    if len(scores) < 2:
        return "flat"

    recent = scores[-window:] if len(scores) >= window else scores
    if len(recent) < 2:
        return "flat"

    # Compare first half average to second half average
    mid = len(recent) // 2
    first_half_avg = sum(recent[:mid]) / mid
    second_half_avg = sum(recent[mid:]) / (len(recent) - mid)

    diff = second_half_avg - first_half_avg
    threshold = 0.01  # 1% change threshold

    if diff > threshold:
        return "up"
    elif diff < -threshold:
        return "down"
    return "flat"


def aggregate_deviation_counts(
    severity_counts: dict[str, int],
) -> DeviationSummary:
    """Aggregate deviation counts by severity.

    Args:
        severity_counts: Dict mapping severity string to count.

    Returns:
        DeviationSummary with populated severity breakdowns.
    """
    summary = DeviationSummary()
    for severity, count in severity_counts.items():
        severity_lower = severity.lower()
        if severity_lower == "critical":
            summary.critical = count
        elif severity_lower == "high":
            summary.high = count
        elif severity_lower == "medium":
            summary.medium = count
        elif severity_lower == "low":
            summary.low = count
        elif severity_lower == "info":
            summary.info = count
        summary.total += count
    return summary


def build_compliance_trend(
    data_points: list[dict[str, Any]],
) -> ComplianceTrend:
    """Build compliance trend from data points.

    Args:
        data_points: List of dicts with 'date' and 'score' keys,
            ordered chronologically.

    Returns:
        ComplianceTrend with computed trend direction.
    """
    if not data_points:
        return ComplianceTrend()

    points = [ComplianceDataPoint(date=str(dp["date"]), score=dp["score"]) for dp in data_points]
    scores = [dp["score"] for dp in data_points]

    return ComplianceTrend(
        current_score=scores[-1],
        trend_direction=compute_trend_direction(scores),
        data_points=points,
    )
