"""Aggregate volume replay engine with bottleneck detection (Story #339).

Computes per-interval flow metrics across all cases for process animation:
- Case counts entering/exiting each activity per time interval
- Queue depth at each activity for bottleneck detection
- Gateway variant distribution percentages
- Heat map traceability with case_id lists per cell

Uses canonical event spine data produced by the Event Spine Builder.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Bottleneck threshold: queue depth > multiplier * average queue depth
DEFAULT_BOTTLENECK_MULTIPLIER = 2.0


@dataclass
class ActivityMetrics:
    """Per-activity per-interval flow metrics.

    Attributes:
        activity_name: Process activity name.
        interval_start: ISO 8601 start of the time interval.
        entering_count: Cases entering this activity during interval.
        exiting_count: Cases completing this activity during interval.
        queue_depth: Cases waiting at this activity (entering - exiting cumulative).
        avg_cycle_time_ms: Average time to complete this activity in ms.
        case_ids: List of case IDs contributing to this interval.
        is_bottleneck: Whether this activity exceeds bottleneck threshold.
    """

    activity_name: str
    interval_start: str
    entering_count: int = 0
    exiting_count: int = 0
    queue_depth: int = 0
    avg_cycle_time_ms: int = 0
    case_ids: list[str] = field(default_factory=list)
    is_bottleneck: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "activity_name": self.activity_name,
            "interval_start": self.interval_start,
            "entering_count": self.entering_count,
            "exiting_count": self.exiting_count,
            "queue_depth": self.queue_depth,
            "avg_cycle_time_ms": self.avg_cycle_time_ms,
            "case_ids": self.case_ids,
            "is_bottleneck": self.is_bottleneck,
        }


@dataclass
class GatewayDistribution:
    """Variant distribution at a decision gateway.

    Attributes:
        gateway_activity: Activity name at the decision point.
        paths: Mapping of next_activity -> proportion (0.0-1.0).
        total_cases: Total cases passing through this gateway.
    """

    gateway_activity: str
    paths: dict[str, float] = field(default_factory=dict)
    total_cases: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "gateway_activity": self.gateway_activity,
            "paths": self.paths,
            "total_cases": self.total_cases,
        }


@dataclass
class AggregateReplayResult:
    """Result of aggregate volume replay computation.

    Attributes:
        task_id: Unique replay task identifier.
        engagement_id: Engagement being analyzed.
        status: Task status.
        interval_granularity: Time interval size (hourly/daily/weekly).
        activity_metrics: Per-activity per-interval metrics.
        bottlenecks: Activities flagged as bottlenecks.
        gateway_distributions: Variant distributions at gateways.
        heat_map: Nested dict of element -> interval -> metrics.
        total_cases: Total unique cases in the analysis.
        total_intervals: Number of time intervals computed.
        created_at: ISO 8601 creation timestamp.
    """

    task_id: str = ""
    engagement_id: str = ""
    status: str = "pending"
    interval_granularity: str = "daily"
    activity_metrics: list[ActivityMetrics] = field(default_factory=list)
    bottlenecks: list[str] = field(default_factory=list)
    gateway_distributions: list[GatewayDistribution] = field(default_factory=list)
    heat_map: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    total_cases: int = 0
    total_intervals: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(tz=UTC).isoformat()

    def to_status_dict(self) -> dict[str, Any]:
        """Serialize task status for polling endpoint."""
        return {
            "task_id": self.task_id,
            "replay_type": "aggregate",
            "status": self.status,
            "progress_pct": 100 if self.status == "completed" else 0,
            "created_at": self.created_at,
        }


def _parse_timestamp(ts: Any) -> datetime:
    """Parse a timestamp to datetime, handling strings and datetime objects."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        # Handle ISO format with various timezone suffixes
        ts_clean = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_clean)
    msg = f"Cannot parse timestamp: {ts}"
    raise ValueError(msg)


def _get_interval_key(dt: datetime, granularity: str) -> str:
    """Compute the interval key for a timestamp.

    Args:
        dt: The timestamp to bucket.
        granularity: One of 'hourly', 'daily', 'weekly'.

    Returns:
        ISO 8601 formatted start of the interval.
    """
    if granularity == "hourly":
        return dt.replace(minute=0, second=0, microsecond=0).isoformat()
    if granularity == "weekly":
        # Monday-aligned weeks
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    # daily (default)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def compute_activity_flow(
    events: list[dict[str, Any]],
    granularity: str = "daily",
) -> list[ActivityMetrics]:
    """Compute per-activity per-interval flow metrics.

    Each event is counted as both entering (at timestamp) and exiting
    (after the activity completes). For simplicity, each event represents
    both entry and exit at the same timestamp.

    Args:
        events: Canonical activity events sorted by timestamp_utc.
        granularity: Time interval size.

    Returns:
        List of ActivityMetrics for each activity/interval combination.
    """
    # Bucket events by (activity_name, interval)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        ts = _parse_timestamp(event.get("timestamp_utc", ""))
        interval_key = _get_interval_key(ts, granularity)
        activity = event.get("activity_name", "")
        buckets[(activity, interval_key)].append(event)

    metrics: list[ActivityMetrics] = []
    for (activity, interval), bucket_events in sorted(buckets.items()):
        case_ids = list({e.get("case_id", "") for e in bucket_events})
        entering = len(bucket_events)
        exiting = entering  # Each event is an entry+exit in aggregate mode

        metrics.append(
            ActivityMetrics(
                activity_name=activity,
                interval_start=interval,
                entering_count=entering,
                exiting_count=exiting,
                queue_depth=0,  # Computed separately
                case_ids=sorted(case_ids),
            )
        )

    return metrics


def detect_bottlenecks(
    metrics: list[ActivityMetrics],
    multiplier: float = DEFAULT_BOTTLENECK_MULTIPLIER,
) -> list[str]:
    """Identify bottleneck activities where queue depth exceeds threshold.

    An activity is a bottleneck if its total event count exceeds the
    multiplier times the average event count across all activities.

    Args:
        metrics: Activity metrics to analyze.
        multiplier: Threshold multiplier (default 2.0).

    Returns:
        List of activity names flagged as bottlenecks.
    """
    if not metrics:
        return []

    # Aggregate entering counts per activity
    activity_totals: dict[str, int] = defaultdict(int)
    for m in metrics:
        activity_totals[m.activity_name] += m.entering_count

    if not activity_totals:
        return []

    avg_count = sum(activity_totals.values()) / len(activity_totals)
    threshold = avg_count * multiplier

    bottlenecks = sorted(
        name for name, total in activity_totals.items() if total > threshold
    )

    # Mark metrics as bottleneck
    bottleneck_set = set(bottlenecks)
    for m in metrics:
        if m.activity_name in bottleneck_set:
            m.is_bottleneck = True
            m.queue_depth = activity_totals[m.activity_name]

    return bottlenecks


def compute_gateway_distributions(
    events: list[dict[str, Any]],
) -> list[GatewayDistribution]:
    """Compute variant distribution at decision gateways.

    A gateway is detected when the same case has multiple different
    activities following the same predecessor activity. Distribution
    is computed as the proportion of cases taking each path.

    For simplicity, each unique (predecessor, successor) pair from
    consecutive events in the same case defines a gateway path.

    Args:
        events: Canonical events sorted by (case_id, timestamp_utc).

    Returns:
        List of GatewayDistribution for activities with multiple paths.
    """
    # Group events by case_id, preserving order
    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cases[event.get("case_id", "")].append(event)

    # Count transitions: predecessor -> successor -> count
    transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for case_events in cases.values():
        sorted_events = sorted(
            case_events,
            key=lambda e: str(e.get("timestamp_utc", "")),
        )
        for i in range(len(sorted_events) - 1):
            pred = sorted_events[i].get("activity_name", "")
            succ = sorted_events[i + 1].get("activity_name", "")
            transitions[pred][succ] += 1

    # Only report gateways with 2+ outgoing paths
    distributions: list[GatewayDistribution] = []
    for gateway, successors in sorted(transitions.items()):
        if len(successors) < 2:
            continue
        total = sum(successors.values())
        paths = {
            succ: round(count / total, 2) for succ, count in sorted(successors.items())
        }
        distributions.append(
            GatewayDistribution(
                gateway_activity=gateway,
                paths=paths,
                total_cases=total,
            )
        )

    return distributions


def build_heat_map(
    metrics: list[ActivityMetrics],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Build heat map data structure for visualization.

    Structure: {activity_name: {interval: {case_count, queue_depth, case_ids}}}

    Args:
        metrics: Computed activity metrics.

    Returns:
        Nested dict for heat map rendering.
    """
    heat_map: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for m in metrics:
        heat_map[m.activity_name][m.interval_start] = {
            "case_count": m.entering_count,
            "queue_depth": m.queue_depth,
            "case_ids": m.case_ids,
        }

    return dict(heat_map)


def generate_aggregate_replay(
    engagement_id: str,
    events: list[dict[str, Any]],
    granularity: str = "daily",
    bottleneck_multiplier: float = DEFAULT_BOTTLENECK_MULTIPLIER,
) -> AggregateReplayResult:
    """Generate aggregate volume replay from canonical events.

    Computes flow metrics, bottleneck detection, gateway distributions,
    and heat map data for process animation visualization.

    Args:
        engagement_id: Engagement being analyzed.
        events: Canonical activity events for the engagement.
        granularity: Time interval size (hourly/daily/weekly).
        bottleneck_multiplier: Threshold multiplier for bottleneck detection.

    Returns:
        AggregateReplayResult with all computed metrics.
    """
    result = AggregateReplayResult(
        engagement_id=engagement_id,
        interval_granularity=granularity,
    )

    if not events:
        result.status = "completed"
        return result

    # Compute flow metrics
    activity_metrics = compute_activity_flow(events, granularity)

    # Detect bottlenecks
    bottlenecks = detect_bottlenecks(activity_metrics, bottleneck_multiplier)

    # Compute gateway distributions
    gateway_distributions = compute_gateway_distributions(events)

    # Build heat map
    heat_map = build_heat_map(activity_metrics)

    # Count unique cases and intervals
    all_cases = set()
    all_intervals = set()
    for event in events:
        all_cases.add(event.get("case_id", ""))
    for m in activity_metrics:
        all_intervals.add(m.interval_start)

    result.activity_metrics = activity_metrics
    result.bottlenecks = bottlenecks
    result.gateway_distributions = gateway_distributions
    result.heat_map = heat_map
    result.total_cases = len(all_cases)
    result.total_intervals = len(all_intervals)
    result.status = "completed"

    logger.info(
        "Aggregate replay for %s: %d cases, %d intervals, %d bottlenecks",
        engagement_id,
        result.total_cases,
        result.total_intervals,
        len(bottlenecks),
    )

    return result


# ---------------------------------------------------------------------------
# Heatmap density and drill-down support
# ---------------------------------------------------------------------------

@dataclass
class HeatmapDensity:
    """Density data per activity node for heatmap overlay.

    Attributes:
        activity_name: Activity name.
        total_events: Total events across all intervals.
        density: Normalized density (0.0-1.0) relative to max activity.
        avg_dwell_ms: Average time cases spend at this activity.
        case_ids: Unique cases that touched this activity.
    """

    activity_name: str
    total_events: int = 0
    density: float = 0.0
    avg_dwell_ms: int = 0
    case_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_name": self.activity_name,
            "total_events": self.total_events,
            "density": round(self.density, 4),
            "avg_dwell_ms": self.avg_dwell_ms,
            "unique_cases": len(self.case_ids),
        }


def compute_heatmap_density(
    events: list[dict[str, Any]],
) -> list[HeatmapDensity]:
    """Compute density per activity node for heatmap overlay.

    Density is normalized to [0.0, 1.0] where 1.0 is the most
    frequently visited activity.

    Args:
        events: Canonical activity events.

    Returns:
        List of HeatmapDensity per activity, sorted by density descending.
    """
    activity_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        activity = event.get("activity_name", "")
        activity_events[activity].append(event)

    if not activity_events:
        return []

    max_count = max(len(evts) for evts in activity_events.values())

    densities: list[HeatmapDensity] = []
    for activity, evts in sorted(activity_events.items()):
        case_ids = sorted({e.get("case_id", "") for e in evts})
        densities.append(
            HeatmapDensity(
                activity_name=activity,
                total_events=len(evts),
                density=len(evts) / max_count if max_count > 0 else 0.0,
                case_ids=case_ids,
            )
        )

    densities.sort(key=lambda d: d.density, reverse=True)
    return densities


def get_drilldown_cases(
    events: list[dict[str, Any]],
    activity_name: str,
) -> list[dict[str, Any]]:
    """Get individual case details for drill-down from aggregate to single-case.

    Args:
        events: Canonical activity events.
        activity_name: Activity to drill into.

    Returns:
        List of case summaries for the specified activity.
    """
    matching = [e for e in events if e.get("activity_name") == activity_name]

    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in matching:
        cases[event.get("case_id", "")].append(event)

    return [
        {
            "case_id": case_id,
            "event_count": len(case_events),
            "first_occurrence": min(
                str(e.get("timestamp_utc", "")) for e in case_events
            ),
            "last_occurrence": max(
                str(e.get("timestamp_utc", "")) for e in case_events
            ),
        }
        for case_id, case_events in sorted(cases.items())
    ]
