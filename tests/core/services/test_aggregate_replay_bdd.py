"""BDD tests for aggregate volume replay engine (Story #339).

Scenarios:
  1. Volume Flow Animation Data — per-interval per-activity case counts
  2. Bottleneck Detection — queue depth exceeding threshold
  3. Gateway Variant Distribution — proportional flow splits
  4. Heat Map Traceability — per-element per-interval metrics with case IDs
"""

from __future__ import annotations

import uuid
from typing import Any

from src.core.services.aggregate_replay import (
    ActivityMetrics,
    AggregateReplayResult,
    GatewayDistribution,
    build_heat_map,
    compute_activity_flow,
    compute_gateway_distributions,
    detect_bottlenecks,
    generate_aggregate_replay,
)

# -- Helpers ------------------------------------------------------------------


def _make_event(
    case_id: str = "case-001",
    activity: str = "Submit Application",
    timestamp: str = "2026-01-15T10:00:00+00:00",
    confidence: float = 0.85,
) -> dict[str, Any]:
    """Create a canonical event dict for testing."""
    return {
        "case_id": case_id,
        "activity_name": activity,
        "timestamp_utc": timestamp,
        "confidence_score": confidence,
        "performer_role_ref": "Analyst",
        "evidence_refs": [],
    }


def _make_case_events(
    case_id: str,
    activities: list[str],
    base_hour: int = 10,
    day: int = 15,
    month: int = 1,
) -> list[dict[str, Any]]:
    """Create sequential events for a single case."""
    return [
        _make_event(
            case_id=case_id,
            activity=activity,
            timestamp=f"2026-{month:02d}-{day:02d}T{(base_hour + i) % 24:02d}:00:00+00:00",
        )
        for i, activity in enumerate(activities)
    ]


def _make_bulk_events(
    case_count: int,
    activities: list[str],
) -> list[dict[str, Any]]:
    """Create events for multiple cases with the same activity sequence."""
    events = []
    for i in range(case_count):
        # Spread across months to avoid day overflow
        total_day = i // 12  # 12 cases per day
        month = 1 + (total_day // 28)  # 28 days per month
        day = 1 + (total_day % 28)
        hour = 10 + (i % 12)
        events.extend(
            _make_case_events(f"case-{i:03d}", activities, base_hour=hour, day=day, month=month)
        )
    return events


# -- Scenario 1: Volume Flow Animation Data ----------------------------------


class TestVolumeFlowAnimation:
    """Scenario 1: Per-interval per-activity case counts."""

    def test_500_cases_produce_metrics(self) -> None:
        activities = ["Submit", "Review", "Approve"]
        events = _make_bulk_events(500, activities)
        result = generate_aggregate_replay("eng-001", events, granularity="daily")
        assert result.total_cases == 500
        assert result.status == "completed"

    def test_entering_and_exiting_counts(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
            _make_event(case_id="c3", activity="Submit", timestamp="2026-01-15T12:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        # All 3 events in same daily interval for "Submit"
        assert len(metrics) == 1
        assert metrics[0].entering_count == 3
        assert metrics[0].exiting_count == 3

    def test_per_interval_bucketing_daily(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-16T10:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        assert len(metrics) == 2

    def test_per_interval_bucketing_hourly(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "hourly")
        assert len(metrics) == 2

    def test_task_id_returned(self) -> None:
        events = [_make_event()]
        result = generate_aggregate_replay("eng-001", events)
        assert result.task_id
        uuid.UUID(result.task_id)

    def test_empty_events(self) -> None:
        result = generate_aggregate_replay("eng-001", [])
        assert result.status == "completed"
        assert result.total_cases == 0
        assert result.activity_metrics == []

    def test_case_ids_in_metrics(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        assert sorted(metrics[0].case_ids) == ["c1", "c2"]

    def test_multiple_activities_separate_metrics(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c1", activity="Review", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        activity_names = {m.activity_name for m in metrics}
        assert activity_names == {"Submit", "Review"}


# -- Scenario 2: Bottleneck Detection ----------------------------------------


class TestBottleneckDetection:
    """Scenario 2: Activities with queue depth exceeding threshold."""

    def test_bottleneck_detected_above_threshold(self) -> None:
        # 10 events for Submit, 2 for Review, 2 for Approve
        # Average = (10+2+2)/3 = 4.67, threshold = 9.33
        events = []
        for i in range(10):
            events.append(_make_event(case_id=f"c{i}", activity="Submit", timestamp=f"2026-01-15T{10+i}:00:00+00:00"))
        for i in range(2):
            events.append(_make_event(case_id=f"c{i}", activity="Review", timestamp=f"2026-01-15T{10+i}:00:00+00:00"))
        for i in range(2):
            events.append(_make_event(case_id=f"c{i}", activity="Approve", timestamp=f"2026-01-15T{10+i}:00:00+00:00"))

        metrics = compute_activity_flow(events, "daily")
        bottlenecks = detect_bottlenecks(metrics, multiplier=2.0)
        assert "Submit" in bottlenecks
        assert "Review" not in bottlenecks

    def test_no_bottleneck_when_balanced(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit"),
            _make_event(case_id="c2", activity="Review"),
            _make_event(case_id="c3", activity="Approve"),
        ]
        metrics = compute_activity_flow(events, "daily")
        bottlenecks = detect_bottlenecks(metrics, multiplier=2.0)
        assert bottlenecks == []

    def test_bottleneck_flag_on_metrics(self) -> None:
        # 10 Submit, 1 Review, 1 Approve → avg=4, threshold at 1.5x = 6
        events = []
        for i in range(10):
            events.append(_make_event(case_id=f"c{i}", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"))
        events.append(_make_event(case_id="c0", activity="Review", timestamp="2026-01-15T11:00:00+00:00"))
        events.append(_make_event(case_id="c1", activity="Approve", timestamp="2026-01-15T12:00:00+00:00"))

        metrics = compute_activity_flow(events, "daily")
        detect_bottlenecks(metrics, multiplier=1.5)

        submit_metrics = [m for m in metrics if m.activity_name == "Submit"]
        assert all(m.is_bottleneck for m in submit_metrics)

    def test_queue_depth_set_for_bottleneck(self) -> None:
        # 10 Submit, 1 Review, 1 Approve → avg=4, threshold at 1.5x = 6
        events = []
        for i in range(10):
            events.append(_make_event(case_id=f"c{i}", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"))
        events.append(_make_event(case_id="c0", activity="Review", timestamp="2026-01-15T11:00:00+00:00"))
        events.append(_make_event(case_id="c1", activity="Approve", timestamp="2026-01-15T12:00:00+00:00"))

        metrics = compute_activity_flow(events, "daily")
        detect_bottlenecks(metrics, multiplier=1.5)

        submit_metrics = [m for m in metrics if m.activity_name == "Submit"]
        assert submit_metrics[0].queue_depth == 10

    def test_custom_multiplier(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit"),
            _make_event(case_id="c2", activity="Submit"),
            _make_event(case_id="c3", activity="Review"),
        ]
        metrics = compute_activity_flow(events, "daily")
        # With multiplier 1.0, Submit (2) > avg (1.5) * 1.0, so bottleneck
        bottlenecks = detect_bottlenecks(metrics, multiplier=1.0)
        assert "Submit" in bottlenecks

    def test_empty_metrics(self) -> None:
        bottlenecks = detect_bottlenecks([], multiplier=2.0)
        assert bottlenecks == []

    def test_bottleneck_threshold_boundary(self) -> None:
        # 4 Submit, 2 Review — avg = 3, threshold at 2x = 6
        # Submit (4) < 6, so NOT a bottleneck
        events = []
        for i in range(4):
            events.append(_make_event(case_id=f"c{i}", activity="Submit", timestamp=f"2026-01-15T{10+i}:00:00+00:00"))
        for i in range(2):
            events.append(_make_event(case_id=f"c{i}", activity="Review", timestamp=f"2026-01-15T{10+i}:00:00+00:00"))
        metrics = compute_activity_flow(events, "daily")
        bottlenecks = detect_bottlenecks(metrics, multiplier=2.0)
        assert bottlenecks == []


# -- Scenario 3: Gateway Variant Distribution ---------------------------------


class TestGatewayDistribution:
    """Scenario 3: Proportional flow splits at decision gateways."""

    def test_60_40_split(self) -> None:
        events = []
        # 6 cases go Submit -> Approve
        for i in range(6):
            events.extend(_make_case_events(f"c{i}", ["Submit", "Approve"], base_hour=10 + i))
        # 4 cases go Submit -> Reject
        for i in range(6, 10):
            events.extend(_make_case_events(f"c{i}", ["Submit", "Reject"], base_hour=10 + i))

        distributions = compute_gateway_distributions(events)
        submit_dist = next(d for d in distributions if d.gateway_activity == "Submit")
        assert submit_dist.paths["Approve"] == 0.6
        assert submit_dist.paths["Reject"] == 0.4
        assert submit_dist.total_cases == 10

    def test_no_gateway_for_single_path(self) -> None:
        events = _make_case_events("c1", ["Submit", "Review", "Approve"])
        events.extend(_make_case_events("c2", ["Submit", "Review", "Approve"], base_hour=14))
        distributions = compute_gateway_distributions(events)
        # Submit -> Review always, Review -> Approve always: no gateways
        assert len(distributions) == 0

    def test_gateway_with_three_paths(self) -> None:
        events = []
        events.extend(_make_case_events("c1", ["Submit", "PathA"]))
        events.extend(_make_case_events("c2", ["Submit", "PathB"], base_hour=12))
        events.extend(_make_case_events("c3", ["Submit", "PathC"], base_hour=14))

        distributions = compute_gateway_distributions(events)
        submit_dist = next(d for d in distributions if d.gateway_activity == "Submit")
        assert len(submit_dist.paths) == 3
        # Each 1/3 ≈ 0.33
        assert all(0.32 <= v <= 0.34 for v in submit_dist.paths.values())

    def test_distribution_sums_to_one(self) -> None:
        events = []
        for i in range(5):
            events.extend(_make_case_events(f"c{i}", ["Submit", "Approve"], base_hour=10 + i))
        for i in range(5, 8):
            events.extend(_make_case_events(f"c{i}", ["Submit", "Reject"], base_hour=10 + i))

        distributions = compute_gateway_distributions(events)
        submit_dist = next(d for d in distributions if d.gateway_activity == "Submit")
        total = sum(submit_dist.paths.values())
        assert abs(total - 1.0) < 0.01

    def test_empty_events(self) -> None:
        distributions = compute_gateway_distributions([])
        assert distributions == []

    def test_to_dict_serialization(self) -> None:
        dist = GatewayDistribution(
            gateway_activity="Submit",
            paths={"Approve": 0.6, "Reject": 0.4},
            total_cases=10,
        )
        d = dist.to_dict()
        assert d["gateway_activity"] == "Submit"
        assert d["paths"]["Approve"] == 0.6


# -- Scenario 4: Heat Map Traceability ---------------------------------------


class TestHeatMapTraceability:
    """Scenario 4: Per-element per-interval metrics with case IDs."""

    def test_heat_map_structure(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        hm = build_heat_map(metrics)
        assert "Submit" in hm
        # One daily interval
        intervals = list(hm["Submit"].keys())
        assert len(intervals) == 1

    def test_heat_map_case_count(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
            _make_event(case_id="c3", activity="Submit", timestamp="2026-01-15T12:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        hm = build_heat_map(metrics)
        interval_data = list(hm["Submit"].values())[0]
        assert interval_data["case_count"] == 3

    def test_heat_map_case_ids_traceable(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        hm = build_heat_map(metrics)
        interval_data = list(hm["Submit"].values())[0]
        assert sorted(interval_data["case_ids"]) == ["c1", "c2"]

    def test_heat_map_multiple_intervals(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-16T10:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        hm = build_heat_map(metrics)
        assert len(hm["Submit"]) == 2

    def test_heat_map_multiple_activities(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c1", activity="Review", timestamp="2026-01-15T11:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "daily")
        hm = build_heat_map(metrics)
        assert "Submit" in hm
        assert "Review" in hm

    def test_heat_map_in_aggregate_result(self) -> None:
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
        ]
        result = generate_aggregate_replay("eng-001", events)
        assert result.heat_map
        assert "Submit" in result.heat_map

    def test_heat_map_queue_depth(self) -> None:
        # 10 Submit, 1 Review, 1 Approve → avg=4, threshold at 1.5x = 6
        events = []
        for i in range(10):
            events.append(_make_event(case_id=f"c{i}", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"))
        events.append(_make_event(case_id="c0", activity="Review", timestamp="2026-01-15T11:00:00+00:00"))
        events.append(_make_event(case_id="c1", activity="Approve", timestamp="2026-01-15T12:00:00+00:00"))

        metrics = compute_activity_flow(events, "daily")
        detect_bottlenecks(metrics, multiplier=1.5)
        hm = build_heat_map(metrics)
        submit_data = list(hm["Submit"].values())[0]
        assert submit_data["queue_depth"] == 10


# -- ActivityMetrics unit tests -----------------------------------------------


class TestActivityMetrics:
    """Unit tests for ActivityMetrics dataclass."""

    def test_to_dict(self) -> None:
        m = ActivityMetrics(
            activity_name="Submit",
            interval_start="2026-01-15T00:00:00+00:00",
            entering_count=5,
            exiting_count=5,
            queue_depth=3,
            case_ids=["c1", "c2"],
            is_bottleneck=True,
        )
        d = m.to_dict()
        assert d["activity_name"] == "Submit"
        assert d["entering_count"] == 5
        assert d["is_bottleneck"] is True

    def test_default_values(self) -> None:
        m = ActivityMetrics(activity_name="X", interval_start="2026-01-15T00:00:00+00:00")
        assert m.entering_count == 0
        assert m.is_bottleneck is False
        assert m.case_ids == []


# -- AggregateReplayResult unit tests ----------------------------------------


class TestAggregateReplayResult:
    """Unit tests for result dataclass."""

    def test_auto_generated_task_id(self) -> None:
        result = AggregateReplayResult(engagement_id="eng-001")
        assert result.task_id
        uuid.UUID(result.task_id)

    def test_status_dict(self) -> None:
        result = AggregateReplayResult(engagement_id="eng-001", status="completed")
        d = result.to_status_dict()
        assert d["replay_type"] == "aggregate"
        assert d["progress_pct"] == 100

    def test_pending_progress_zero(self) -> None:
        result = AggregateReplayResult(engagement_id="eng-001")
        d = result.to_status_dict()
        assert d["progress_pct"] == 0

    def test_total_intervals_computed(self) -> None:
        events = [
            _make_event(case_id="c1", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", timestamp="2026-01-16T10:00:00+00:00"),
        ]
        result = generate_aggregate_replay("eng-001", events, granularity="daily")
        assert result.total_intervals == 2


# -- Weekly granularity -------------------------------------------------------


class TestWeeklyGranularity:
    """Test weekly interval bucketing."""

    def test_same_week_events_grouped(self) -> None:
        # 2026-01-15 is a Thursday, 2026-01-16 is a Friday — same week
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-16T10:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "weekly")
        assert len(metrics) == 1  # Same Monday-aligned week

    def test_different_week_events_separated(self) -> None:
        # 2026-01-15 and 2026-01-22 are different weeks
        events = [
            _make_event(case_id="c1", activity="Submit", timestamp="2026-01-15T10:00:00+00:00"),
            _make_event(case_id="c2", activity="Submit", timestamp="2026-01-22T10:00:00+00:00"),
        ]
        metrics = compute_activity_flow(events, "weekly")
        assert len(metrics) == 2
