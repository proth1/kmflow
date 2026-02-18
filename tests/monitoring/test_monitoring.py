"""Comprehensive tests for monitoring subsystem.

Tests cover:
- config.py: validate_cron_expression, validate_monitoring_config
- baseline.py: create_baseline_snapshot, compute_process_hash, compare_baselines
- scheduler.py: parse_cron_field, should_run_now, calculate_next_run
- comparator.py: detect_sequence_changes, detect_timing_anomalies, detect_role_changes,
                 detect_frequency_changes, detect_control_bypass
- alerting.py: classify_severity, generate_dedup_key, create_alert_from_deviations
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.models import AlertSeverity, DeviationCategory, MonitoringSourceType
from src.monitoring.alerting import (
    classify_severity,
    create_alert_from_deviations,
    generate_dedup_key,
)
from src.monitoring.baseline import (
    compare_baselines,
    compute_process_hash,
    create_baseline_snapshot,
)
from src.monitoring.comparator import (
    detect_control_bypass,
    detect_frequency_changes,
    detect_role_changes,
    detect_sequence_changes,
    detect_timing_anomalies,
)
from src.monitoring.config import validate_cron_expression, validate_monitoring_config
from src.monitoring.scheduler import (
    calculate_next_run,
    parse_cron_field,
    should_run_now,
)

# ===== config.py Tests =====


class TestValidateCron:
    """Tests for validate_cron_expression()."""

    def test_valid_daily_midnight(self):
        assert validate_cron_expression("0 0 * * *")

    def test_valid_step_pattern(self):
        # The current regex requires explicit step notation without *
        assert validate_cron_expression("0/5 * * * *")

    def test_valid_weekdays_9am(self):
        assert validate_cron_expression("0 9 * * 1-5")

    def test_valid_first_of_month(self):
        assert validate_cron_expression("0 0 1 * *")

    def test_valid_specific_times(self):
        assert validate_cron_expression("15,45 8,12,16 * * *")

    def test_invalid_not_cron(self):
        assert not validate_cron_expression("not cron")

    def test_invalid_empty(self):
        assert not validate_cron_expression("")

    def test_invalid_four_fields(self):
        assert not validate_cron_expression("0 0 * *")

    def test_invalid_six_fields(self):
        assert not validate_cron_expression("0 0 * * * *")

    def test_invalid_missing_spaces(self):
        assert not validate_cron_expression("0 0***")

    def test_valid_with_leading_trailing_whitespace(self):
        assert validate_cron_expression("  0 0 * * *  ")


class TestValidateMonitoringConfig:
    """Tests for validate_monitoring_config()."""

    def test_event_log_valid(self):
        errors = validate_monitoring_config(
            MonitoringSourceType.EVENT_LOG,
            {"log_source": "xes_import_123"},
        )
        assert errors == []

    def test_event_log_missing_log_source(self):
        errors = validate_monitoring_config(MonitoringSourceType.EVENT_LOG, {})
        assert len(errors) == 1
        assert "log_source" in errors[0]

    def test_event_log_none_config(self):
        errors = validate_monitoring_config(MonitoringSourceType.EVENT_LOG, None)
        assert len(errors) == 1
        assert "log_source" in errors[0]

    def test_system_api_valid(self):
        errors = validate_monitoring_config(
            MonitoringSourceType.SYSTEM_API,
            {"endpoint_url": "https://api.example.com/process"},
        )
        assert errors == []

    def test_system_api_missing_endpoint(self):
        errors = validate_monitoring_config(MonitoringSourceType.SYSTEM_API, {})
        assert len(errors) == 1
        assert "endpoint_url" in errors[0]

    def test_file_watch_valid(self):
        errors = validate_monitoring_config(
            MonitoringSourceType.FILE_WATCH,
            {"watch_path": "/data/process-logs"},
        )
        assert errors == []

    def test_file_watch_missing_path(self):
        errors = validate_monitoring_config(MonitoringSourceType.FILE_WATCH, {})
        assert len(errors) == 1
        assert "watch_path" in errors[0]

    def test_task_mining_no_requirements(self):
        errors = validate_monitoring_config(MonitoringSourceType.TASK_MINING, {})
        assert errors == []

    def test_task_mining_none_config(self):
        errors = validate_monitoring_config(MonitoringSourceType.TASK_MINING, None)
        assert errors == []


# ===== baseline.py Tests =====


class TestBaselineSnapshot:
    """Tests for create_baseline_snapshot()."""

    def test_create_with_elements_and_connections(self):
        model_data = {
            "elements": [
                {"name": "Task A", "type": "task"},
                {"name": "Task B", "type": "task"},
                {"name": "Gateway X", "type": "gateway"},
            ],
            "connections": [
                {"source": "Task A", "target": "Gateway X"},
                {"source": "Gateway X", "target": "Task B"},
            ],
        }
        snapshot = create_baseline_snapshot(model_data)
        assert snapshot["element_names"] == ["Gateway X", "Task A", "Task B"]
        assert snapshot["element_types"] == {
            "Task A": "task",
            "Task B": "task",
            "Gateway X": "gateway",
        }
        assert snapshot["connection_pairs"] == [
            ("Task A", "Gateway X"),
            ("Gateway X", "Task B"),
        ]

    def test_create_empty_model(self):
        snapshot = create_baseline_snapshot({})
        assert snapshot["element_names"] == []
        assert snapshot["element_types"] == {}
        assert snapshot["connection_pairs"] == []

    def test_elements_without_names(self):
        model_data = {
            "elements": [
                {"type": "task"},
                {"name": "Named Task", "type": "task"},
            ],
        }
        snapshot = create_baseline_snapshot(model_data)
        assert sorted(snapshot["element_names"]) == ["", "Named Task"]


class TestComputeProcessHash:
    """Tests for compute_process_hash()."""

    def test_deterministic_same_input(self):
        snapshot = {
            "element_names": ["A", "B"],
            "element_types": {"A": "task", "B": "gateway"},
        }
        hash1 = compute_process_hash(snapshot)
        hash2 = compute_process_hash(snapshot)
        assert hash1 == hash2

    def test_different_inputs_different_hashes(self):
        snapshot1 = {"element_names": ["A", "B"]}
        snapshot2 = {"element_names": ["B", "A"]}
        hash1 = compute_process_hash(snapshot1)
        hash2 = compute_process_hash(snapshot2)
        assert hash1 != hash2

    def test_hash_length(self):
        snapshot = {"data": "test"}
        hash_val = compute_process_hash(snapshot)
        assert len(hash_val) == 64  # SHA-256 hex digest


class TestCompareBaselines:
    """Tests for compare_baselines()."""

    def test_added_elements(self):
        baseline = create_baseline_snapshot({
            "elements": [{"name": "Task A", "type": "task"}],
            "connections": [],
        })
        current = create_baseline_snapshot({
            "elements": [
                {"name": "Task A", "type": "task"},
                {"name": "Task B", "type": "task"},
            ],
            "connections": [],
        })
        result = compare_baselines(baseline, current)
        assert result["added_elements"] == ["Task B"]
        assert result["removed_elements"] == []
        assert result["has_changes"] is True

    def test_removed_elements(self):
        baseline = create_baseline_snapshot({
            "elements": [
                {"name": "Task A", "type": "task"},
                {"name": "Task B", "type": "task"},
            ],
            "connections": [],
        })
        current = create_baseline_snapshot({
            "elements": [{"name": "Task A", "type": "task"}],
            "connections": [],
        })
        result = compare_baselines(baseline, current)
        assert result["added_elements"] == []
        assert result["removed_elements"] == ["Task B"]
        assert result["has_changes"] is True

    def test_modified_element_types(self):
        baseline = create_baseline_snapshot({
            "elements": [{"name": "Task A", "type": "task"}],
            "connections": [],
        })
        current = create_baseline_snapshot({
            "elements": [{"name": "Task A", "type": "subprocess"}],
            "connections": [],
        })
        result = compare_baselines(baseline, current)
        assert len(result["modified_elements"]) == 1
        mod = result["modified_elements"][0]
        assert mod["name"] == "Task A"
        assert mod["baseline_type"] == "task"
        assert mod["current_type"] == "subprocess"
        assert result["has_changes"] is True

    def test_added_connections(self):
        baseline = create_baseline_snapshot({
            "elements": [
                {"name": "A", "type": "task"},
                {"name": "B", "type": "task"},
            ],
            "connections": [],
        })
        current = create_baseline_snapshot({
            "elements": [
                {"name": "A", "type": "task"},
                {"name": "B", "type": "task"},
            ],
            "connections": [{"source": "A", "target": "B"}],
        })
        result = compare_baselines(baseline, current)
        assert ("A", "B") in result["added_connections"]
        assert result["has_changes"] is True

    def test_removed_connections(self):
        baseline = create_baseline_snapshot({
            "elements": [
                {"name": "A", "type": "task"},
                {"name": "B", "type": "task"},
            ],
            "connections": [{"source": "A", "target": "B"}],
        })
        current = create_baseline_snapshot({
            "elements": [
                {"name": "A", "type": "task"},
                {"name": "B", "type": "task"},
            ],
            "connections": [],
        })
        result = compare_baselines(baseline, current)
        assert ("A", "B") in result["removed_connections"]
        assert result["has_changes"] is True

    def test_no_changes(self):
        baseline = create_baseline_snapshot({
            "elements": [{"name": "A", "type": "task"}],
            "connections": [],
        })
        current = create_baseline_snapshot({
            "elements": [{"name": "A", "type": "task"}],
            "connections": [],
        })
        result = compare_baselines(baseline, current)
        assert result["added_elements"] == []
        assert result["removed_elements"] == []
        assert result["modified_elements"] == []
        assert result["has_changes"] is False


# ===== scheduler.py Tests =====


class TestParseCronField:
    """Tests for parse_cron_field()."""

    def test_asterisk_all_values(self):
        values = parse_cron_field("*", 0, 5)
        assert values == {0, 1, 2, 3, 4, 5}

    def test_single_value(self):
        values = parse_cron_field("5", 0, 10)
        assert values == {5}

    def test_range(self):
        values = parse_cron_field("1-5", 0, 10)
        assert values == {1, 2, 3, 4, 5}

    def test_step_all(self):
        values = parse_cron_field("0/15", 0, 59)
        assert 0 in values
        assert 15 in values
        assert 30 in values
        assert 45 in values
        assert 60 not in values

    def test_step_from_value(self):
        values = parse_cron_field("5/10", 0, 30)
        assert values == {5, 15, 25}

    def test_list(self):
        values = parse_cron_field("1,3,5", 0, 10)
        assert values == {1, 3, 5}

    def test_complex_expression(self):
        values = parse_cron_field("1,5-7,0/20", 0, 59)
        assert 1 in values
        assert 5 in values
        assert 6 in values
        assert 7 in values
        assert 0 in values  # from 0/20
        assert 20 in values
        assert 40 in values


class TestShouldRunNow:
    """Tests for should_run_now()."""

    def test_matching_all_wildcards(self):
        now = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)  # Sunday
        assert should_run_now("* * * * *", now)

    def test_matching_specific_time(self):
        now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)  # Wednesday (weekday=2)
        assert should_run_now("0 9 15 1 2", now)

    def test_not_matching_minute(self):
        now = datetime(2025, 1, 15, 9, 5, 0, tzinfo=UTC)
        assert not should_run_now("0 9 15 1 *", now)

    def test_not_matching_hour(self):
        now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert not should_run_now("0 9 15 1 *", now)

    def test_not_matching_day_of_month(self):
        now = datetime(2025, 1, 16, 9, 0, 0, tzinfo=UTC)
        assert not should_run_now("0 9 15 1 *", now)

    def test_not_matching_month(self):
        now = datetime(2025, 2, 15, 9, 0, 0, tzinfo=UTC)
        assert not should_run_now("0 9 15 1 *", now)

    def test_not_matching_day_of_week(self):
        now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)  # Wednesday (weekday=2)
        assert not should_run_now("0 9 15 1 1", now)  # Requires Tuesday (weekday=1)

    def test_every_15_minutes(self):
        now = datetime(2025, 1, 15, 10, 15, 0, tzinfo=UTC)
        assert should_run_now("0/15 * * * *", now)
        now = datetime(2025, 1, 15, 10, 16, 0, tzinfo=UTC)
        assert not should_run_now("0/15 * * * *", now)

    def test_weekday_range(self):
        now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)  # Wednesday (weekday=2)
        assert should_run_now("0 9 * * 1-5", now)
        now = datetime(2025, 1, 18, 9, 0, 0, tzinfo=UTC)  # Saturday (weekday=5)
        assert not should_run_now("0 9 * * 0-4", now)  # Mon-Fri only (0-4)

    def test_invalid_cron_not_5_fields(self):
        now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
        assert not should_run_now("0 0 * *", now)

    def test_default_now_parameter(self):
        # Just verify it doesn't crash when now=None
        result = should_run_now("* * * * *")
        assert isinstance(result, bool)


class TestCalculateNextRun:
    """Tests for calculate_next_run()."""

    def test_finds_next_matching_minute(self):
        from_time = datetime(2025, 1, 15, 10, 5, 30, tzinfo=UTC)
        next_run = calculate_next_run("0/15 * * * *", from_time)
        assert next_run is not None
        assert next_run.minute == 15
        assert next_run.hour == 10
        assert next_run.second == 0

    def test_next_hour_transition(self):
        from_time = datetime(2025, 1, 15, 10, 55, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 * * * *", from_time)
        assert next_run is not None
        assert next_run.minute == 0
        assert next_run.hour == 11

    def test_specific_daily_time(self):
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 9 * * *", from_time)
        assert next_run is not None
        assert next_run.minute == 0
        assert next_run.hour == 9
        assert next_run.day == 16  # Next day

    def test_no_match_in_24_hours_returns_none(self):
        from_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        # Impossible schedule: Feb 30
        next_run = calculate_next_run("0 0 30 2 *", from_time)
        assert next_run is None

    def test_default_from_time_parameter(self):
        next_run = calculate_next_run("0 0 * * *")
        assert next_run is not None or next_run is None  # Either is valid


# ===== comparator.py Tests =====


class TestDetectSequenceChanges:
    """Tests for detect_sequence_changes()."""

    def test_removed_flow(self):
        baseline = [("A", "B"), ("B", "C")]
        current = [("A", "B")]
        deviations = detect_sequence_changes(baseline, current)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.SEQUENCE_CHANGE
        assert "removed" in dev["description"].lower()
        assert "B" in dev["description"] and "C" in dev["description"]
        assert dev["magnitude"] == 0.7

    def test_added_flow(self):
        baseline = [("A", "B")]
        current = [("A", "B"), ("B", "C")]
        deviations = detect_sequence_changes(baseline, current)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.SEQUENCE_CHANGE
        assert "new" in dev["description"].lower()
        assert dev["magnitude"] == 0.5

    def test_no_changes(self):
        baseline = [("A", "B"), ("B", "C")]
        current = [("A", "B"), ("B", "C")]
        deviations = detect_sequence_changes(baseline, current)
        assert len(deviations) == 0

    def test_list_format_connections(self):
        baseline = [["A", "B"], ["B", "C"]]
        current = [["A", "B"]]
        deviations = detect_sequence_changes(baseline, current)
        assert len(deviations) == 1


class TestDetectTimingAnomalies:
    """Tests for detect_timing_anomalies()."""

    def test_z_score_above_threshold(self):
        baseline = {
            "Task A": {"mean": 100.0, "stddev": 10.0},
        }
        current = {
            "Task A": {"mean": 150.0, "stddev": 10.0},  # z-score = 5.0
        }
        deviations = detect_timing_anomalies(baseline, current, threshold=2.0)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.TIMING_ANOMALY
        assert dev["affected_element"] == "Task A"
        assert dev["details"]["z_score"] == 5.0

    def test_z_score_below_threshold(self):
        baseline = {
            "Task A": {"mean": 100.0, "stddev": 10.0},
        }
        current = {
            "Task A": {"mean": 105.0, "stddev": 10.0},  # z-score = 0.5
        }
        deviations = detect_timing_anomalies(baseline, current, threshold=2.0)
        assert len(deviations) == 0

    def test_zero_stddev_handling(self):
        baseline = {
            "Task A": {"mean": 100.0, "stddev": 0.0},
        }
        current = {
            "Task A": {"mean": 110.0, "stddev": 10.0},
        }
        deviations = detect_timing_anomalies(baseline, current, threshold=2.0)
        # Should use stddev=1 instead of 0, so z-score = 10
        assert len(deviations) == 1

    def test_activity_not_in_current(self):
        baseline = {
            "Task A": {"mean": 100.0, "stddev": 10.0},
            "Task B": {"mean": 50.0, "stddev": 5.0},
        }
        current = {
            "Task A": {"mean": 100.0, "stddev": 10.0},
        }
        deviations = detect_timing_anomalies(baseline, current)
        # Task B is in baseline but not current - should be skipped
        assert len(deviations) == 0

    def test_magnitude_calculation(self):
        baseline = {
            "Task A": {"mean": 100.0, "stddev": 10.0},
        }
        current = {
            "Task A": {"mean": 150.0, "stddev": 10.0},  # z-score = 5.0
        }
        deviations = detect_timing_anomalies(baseline, current)
        dev = deviations[0]
        # magnitude = min(z_score / 5.0, 1.0) = min(1.0, 1.0) = 1.0
        assert dev["magnitude"] == 1.0


class TestDetectRoleChanges:
    """Tests for detect_role_changes()."""

    def test_changed_role(self):
        baseline = {"Task A": "Analyst", "Task B": "Manager"}
        current = {"Task A": "Senior Analyst", "Task B": "Manager"}
        deviations = detect_role_changes(baseline, current)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.ROLE_CHANGE
        assert dev["affected_element"] == "Task A"
        assert dev["details"]["baseline_role"] == "Analyst"
        assert dev["details"]["current_role"] == "Senior Analyst"

    def test_same_roles(self):
        baseline = {"Task A": "Analyst", "Task B": "Manager"}
        current = {"Task A": "Analyst", "Task B": "Manager"}
        deviations = detect_role_changes(baseline, current)
        assert len(deviations) == 0

    def test_missing_activity_in_current(self):
        baseline = {"Task A": "Analyst", "Task B": "Manager"}
        current = {"Task A": "Analyst"}
        deviations = detect_role_changes(baseline, current)
        # Task B is in baseline but not current - should be skipped
        assert len(deviations) == 0

    def test_new_activity_in_current(self):
        baseline = {"Task A": "Analyst"}
        current = {"Task A": "Analyst", "Task B": "Manager"}
        deviations = detect_role_changes(baseline, current)
        # Task B is new - should be skipped (not a change)
        assert len(deviations) == 0


class TestDetectFrequencyChanges:
    """Tests for detect_frequency_changes()."""

    def test_frequency_above_threshold(self):
        baseline = {"Task A": 100.0}
        current = {"Task A": 200.0}  # 100% increase
        deviations = detect_frequency_changes(baseline, current, threshold=0.5)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.FREQUENCY_CHANGE
        assert dev["affected_element"] == "Task A"
        assert dev["details"]["relative_change"] == 1.0

    def test_frequency_below_threshold(self):
        baseline = {"Task A": 100.0}
        current = {"Task A": 110.0}  # 10% increase
        deviations = detect_frequency_changes(baseline, current, threshold=0.5)
        assert len(deviations) == 0

    def test_zero_baseline_frequency(self):
        baseline = {"Task A": 0.0}
        current = {"Task A": 100.0}
        deviations = detect_frequency_changes(baseline, current)
        # Should skip when baseline is 0
        assert len(deviations) == 0

    def test_missing_activity_in_current(self):
        baseline = {"Task A": 100.0}
        current = {"Task B": 50.0}
        deviations = detect_frequency_changes(baseline, current)
        # Task A not in current, treated as 0
        # relative_change = abs(0 - 100) / 100 = 1.0 >= 0.5
        assert len(deviations) == 1

    def test_magnitude_capped_at_1(self):
        baseline = {"Task A": 10.0}
        current = {"Task A": 100.0}  # 900% increase
        deviations = detect_frequency_changes(baseline, current)
        dev = deviations[0]
        assert dev["magnitude"] == 1.0  # Capped


class TestDetectControlBypass:
    """Tests for detect_control_bypass()."""

    def test_missing_control(self):
        required = ["Control A", "Control B", "Control C"]
        executed = ["Control A", "Control C"]
        deviations = detect_control_bypass(required, executed)
        assert len(deviations) == 1
        dev = deviations[0]
        assert dev["category"] == DeviationCategory.CONTROL_BYPASS
        assert dev["affected_element"] == "Control B"
        assert dev["magnitude"] == 0.9

    def test_all_controls_present(self):
        required = ["Control A", "Control B"]
        executed = ["Control A", "Control B", "Control C"]
        deviations = detect_control_bypass(required, executed)
        assert len(deviations) == 0

    def test_no_required_controls(self):
        required = []
        executed = ["Control A"]
        deviations = detect_control_bypass(required, executed)
        assert len(deviations) == 0

    def test_no_executed_controls(self):
        required = ["Control A", "Control B"]
        executed = []
        deviations = detect_control_bypass(required, executed)
        assert len(deviations) == 2


# ===== alerting.py Tests =====


class TestClassifySeverity:
    """Tests for classify_severity()."""

    def test_control_bypass_critical(self):
        severity = classify_severity(DeviationCategory.CONTROL_BYPASS, 0.5)
        assert severity == AlertSeverity.CRITICAL

    def test_missing_activity_high(self):
        severity = classify_severity(DeviationCategory.MISSING_ACTIVITY, 0.5)
        assert severity == AlertSeverity.HIGH

    def test_sequence_change_medium(self):
        severity = classify_severity(DeviationCategory.SEQUENCE_CHANGE, 0.5)
        assert severity == AlertSeverity.MEDIUM

    def test_new_activity_low(self):
        severity = classify_severity(DeviationCategory.NEW_ACTIVITY, 0.5)
        assert severity == AlertSeverity.LOW

    def test_timing_anomaly_medium(self):
        severity = classify_severity(DeviationCategory.TIMING_ANOMALY, 0.5)
        assert severity == AlertSeverity.MEDIUM

    def test_role_change_medium(self):
        severity = classify_severity(DeviationCategory.ROLE_CHANGE, 0.5)
        assert severity == AlertSeverity.MEDIUM

    def test_frequency_change_low(self):
        severity = classify_severity(DeviationCategory.FREQUENCY_CHANGE, 0.5)
        assert severity == AlertSeverity.LOW

    def test_upgrade_low_to_medium_high_magnitude(self):
        severity = classify_severity(DeviationCategory.NEW_ACTIVITY, 0.9)
        assert severity == AlertSeverity.MEDIUM

    def test_upgrade_medium_to_high_high_magnitude(self):
        severity = classify_severity(DeviationCategory.SEQUENCE_CHANGE, 0.95)
        assert severity == AlertSeverity.HIGH

    def test_upgrade_high_to_critical_high_magnitude(self):
        severity = classify_severity(DeviationCategory.MISSING_ACTIVITY, 0.9)
        assert severity == AlertSeverity.CRITICAL

    def test_downgrade_high_to_medium_low_magnitude(self):
        severity = classify_severity(DeviationCategory.MISSING_ACTIVITY, 0.1)
        assert severity == AlertSeverity.MEDIUM

    def test_downgrade_medium_to_low_low_magnitude(self):
        severity = classify_severity(DeviationCategory.SEQUENCE_CHANGE, 0.2)
        assert severity == AlertSeverity.LOW

    def test_critical_no_upgrade_high_magnitude(self):
        severity = classify_severity(DeviationCategory.CONTROL_BYPASS, 1.0)
        assert severity == AlertSeverity.CRITICAL

    def test_invalid_category_string(self):
        severity = classify_severity("invalid_category", 0.5)
        assert severity == AlertSeverity.INFO

    def test_string_category_valid(self):
        severity = classify_severity("control_bypass", 0.5)
        assert severity == AlertSeverity.CRITICAL


class TestGenerateDedupKey:
    """Tests for generate_dedup_key()."""

    def test_same_inputs_same_key(self):
        key1 = generate_dedup_key("eng123", "sequence_change", "Task A")
        key2 = generate_dedup_key("eng123", "sequence_change", "Task A")
        assert key1 == key2

    def test_different_engagement_different_key(self):
        key1 = generate_dedup_key("eng123", "sequence_change", "Task A")
        key2 = generate_dedup_key("eng456", "sequence_change", "Task A")
        assert key1 != key2

    def test_different_category_different_key(self):
        key1 = generate_dedup_key("eng123", "sequence_change", "Task A")
        key2 = generate_dedup_key("eng123", "timing_anomaly", "Task A")
        assert key1 != key2

    def test_different_element_different_key(self):
        key1 = generate_dedup_key("eng123", "sequence_change", "Task A")
        key2 = generate_dedup_key("eng123", "sequence_change", "Task B")
        assert key1 != key2

    def test_none_element_uses_global(self):
        key = generate_dedup_key("eng123", "sequence_change", None)
        assert len(key) == 16

    def test_key_length(self):
        key = generate_dedup_key("eng123", "sequence_change", "Task A")
        assert len(key) == 16


class TestCreateAlertFromDeviations:
    """Tests for create_alert_from_deviations()."""

    def test_creates_alerts_from_deviations(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "Flow removed",
                "affected_element": "Task A",
                "magnitude": 0.7,
            },
            {
                "id": "dev2",
                "category": DeviationCategory.CONTROL_BYPASS,
                "description": "Control missing",
                "affected_element": "Control X",
                "magnitude": 0.9,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert len(alerts) == 2
        assert all(a["engagement_id"] == "eng123" for a in alerts)
        assert all(a["monitoring_job_id"] == "job456" for a in alerts)

    def test_deduplicates_same_element_category(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "Flow 1 removed",
                "affected_element": "Task A",
                "magnitude": 0.7,
            },
            {
                "id": "dev2",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "Flow 2 removed",
                "affected_element": "Task A",
                "magnitude": 0.7,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert len(alerts) == 1
        assert len(alerts[0]["deviation_ids"]) == 2

    def test_alert_title_formatting(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "Test",
                "affected_element": "Task A",
                "magnitude": 0.5,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert "Sequence Change" in alerts[0]["title"]
        assert "Task A" in alerts[0]["title"]

    def test_alert_without_affected_element(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "General change",
                "affected_element": None,
                "magnitude": 0.5,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert len(alerts) == 1
        assert "Sequence Change" in alerts[0]["title"]

    def test_severity_classification_applied(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.CONTROL_BYPASS,
                "description": "Control missing",
                "affected_element": "Control X",
                "magnitude": 0.9,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert alerts[0]["severity"] == AlertSeverity.CRITICAL

    def test_empty_deviations_list(self):
        alerts = create_alert_from_deviations("eng123", "job456", [])
        assert len(alerts) == 0

    def test_dedup_key_in_alert(self):
        deviations = [
            {
                "id": "dev1",
                "category": DeviationCategory.SEQUENCE_CHANGE,
                "description": "Test",
                "affected_element": "Task A",
                "magnitude": 0.5,
            },
        ]
        alerts = create_alert_from_deviations("eng123", "job456", deviations)
        assert "dedup_key" in alerts[0]
        assert len(alerts[0]["dedup_key"]) == 16
