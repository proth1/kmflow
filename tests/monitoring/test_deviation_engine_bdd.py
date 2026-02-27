"""BDD tests for Process Deviation Detection Engine (Story #350).

Tests covering:
- Scenario 1: Skipped activity in telemetry sequence is detected
- Scenario 2: Timing anomaly detected when activity duration exceeds baseline
- Scenario 3: Undocumented activity in telemetry is flagged
- Scenario 4: Deviation list supports filtering by type, severity, and time range
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from uuid import UUID

from src.monitoring.deviation.engine import (
    DeviationEngine,
    PovBaseline,
    PovElement,
    TelemetryEvent,
)
from src.monitoring.deviation.types import (
    DEFAULT_MAGNITUDE_COEFFICIENTS,
    DeviationRecord,
    DeviationSeverity,
    DeviationType,
    classify_severity,
)

# ── Fixtures ──


def _baseline(
    engagement_id: str = "eng-001",
    elements: list[PovElement] | None = None,
) -> PovBaseline:
    """Create a test POV baseline."""
    if elements is None:
        elements = [
            PovElement(id="e1", name="A", importance_score=0.5),
            PovElement(id="e2", name="B", importance_score=0.8),
            PovElement(id="e3", name="C", importance_score=0.6),
        ]
    return PovBaseline(engagement_id=engagement_id, elements=elements)


def _event(
    activity_name: str,
    engagement_id: str = "eng-001",
    duration_hours: float | None = None,
    role: str | None = None,
) -> TelemetryEvent:
    """Create a test telemetry event."""
    return TelemetryEvent(
        id=str(uuid.uuid4()),
        activity_name=activity_name,
        engagement_id=engagement_id,
        duration_hours=duration_hours,
        role=role,
    )


# ── Scenario 1: Skipped activity in telemetry sequence is detected ──


class TestSkippedActivity:
    """Scenario 1: Skipped activity detection."""

    def test_skipped_activity_detected(self):
        """Given A→B→C baseline, when telemetry shows A→C, B is skipped."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["A", "C"])

        assert len(deviations) == 1
        assert deviations[0].deviation_type == DeviationType.SKIPPED_ACTIVITY
        assert deviations[0].affected_element == "B"

    def test_skipped_activity_severity_from_importance(self):
        """B's importance 0.8 → severity HIGH (0.8 * 1.0 = 0.8 >= 0.7)."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["A", "C"])

        assert deviations[0].severity == DeviationSeverity.HIGH
        assert deviations[0].severity_score >= 0.7

    def test_skipped_activity_references_pov_element(self):
        """Deviation references the POV element ID."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["A", "C"])

        assert deviations[0].process_element_id == "e2"

    def test_no_skipped_when_all_present(self):
        """No deviations when all baseline activities appear in telemetry."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["A", "B", "C"])

        assert len(deviations) == 0

    def test_multiple_skipped_activities(self):
        """Multiple activities can be skipped."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["C"])

        assert len(deviations) == 2
        names = {d.affected_element for d in deviations}
        assert names == {"A", "B"}

    def test_skipped_activity_description(self):
        """Description mentions the skipped activity name."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_skipped_activities(["A", "C"])

        assert "B" in deviations[0].description
        assert "absent" in deviations[0].description.lower()


# ── Scenario 2: Timing anomaly detected ──


class TestTimingAnomaly:
    """Scenario 2: Timing anomaly when duration exceeds baseline."""

    def test_timing_anomaly_detected(self):
        """Activity X took 24h vs baseline 2-4h → TIMING_ANOMALY."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.7, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        events = [_event("Activity X", duration_hours=24.0)]
        deviations = engine.detect_timing_anomalies(events)

        assert len(deviations) == 1
        assert deviations[0].deviation_type == DeviationType.TIMING_ANOMALY

    def test_timing_anomaly_includes_details(self):
        """Deviation includes observed_duration_hours and baseline_range."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.7, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        events = [_event("Activity X", duration_hours=24.0)]
        deviations = engine.detect_timing_anomalies(events)

        details = deviations[0].details
        assert details["observed_duration_hours"] == 24.0
        assert details["baseline_range"] == [2.0, 4.0]

    def test_timing_within_range_no_deviation(self):
        """Activity within baseline range generates no deviation."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.7, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        events = [_event("Activity X", duration_hours=3.0)]
        deviations = engine.detect_timing_anomalies(events)

        assert len(deviations) == 0

    def test_timing_anomaly_references_telemetry(self):
        """Deviation includes telemetry event reference."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.7, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        events = [_event("Activity X", duration_hours=24.0)]
        deviations = engine.detect_timing_anomalies(events)

        assert deviations[0].telemetry_ref == events[0].id

    def test_timing_severity_proportional(self):
        """Severity scales with deviation magnitude."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.8, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        # Large deviation
        events_large = [_event("Activity X", duration_hours=100.0)]
        devs_large = engine.detect_timing_anomalies(events_large)

        # Small deviation
        events_small = [_event("Activity X", duration_hours=5.0)]
        devs_small = engine.detect_timing_anomalies(events_small)

        assert devs_large[0].severity_score > devs_small[0].severity_score

    def test_no_duration_skips_check(self):
        """Events without duration_hours are skipped."""
        elements = [
            PovElement(id="x1", name="Activity X", importance_score=0.7, expected_duration_range=(2.0, 4.0)),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        events = [_event("Activity X", duration_hours=None)]
        deviations = engine.detect_timing_anomalies(events)

        assert len(deviations) == 0


# ── Scenario 3: Undocumented activity flagged ──


class TestUndocumentedActivity:
    """Scenario 3: Undocumented activity detection."""

    def test_undocumented_activity_detected(self):
        """Activity not in POV is flagged as UNDOCUMENTED_ACTIVITY."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        events = [_event("Manual Override Review")]
        deviations = engine.detect_undocumented_activities(events)

        assert len(deviations) == 1
        assert deviations[0].deviation_type == DeviationType.UNDOCUMENTED_ACTIVITY
        assert deviations[0].affected_element == "Manual Override Review"

    def test_undocumented_includes_telemetry_ref(self):
        """Deviation includes telemetry event reference and engagement_id."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        events = [_event("Manual Override Review", engagement_id="eng-001")]
        deviations = engine.detect_undocumented_activities(events)

        assert deviations[0].telemetry_ref == events[0].id
        assert deviations[0].engagement_id == "eng-001"

    def test_undocumented_routed_to_review(self):
        """Deviation details flag it for analyst review."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        events = [_event("Unknown Process")]
        deviations = engine.detect_undocumented_activities(events)

        assert deviations[0].details.get("requires_analyst_review") is True

    def test_known_activity_not_flagged(self):
        """Activities matching the POV are not flagged."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        events = [_event("A"), _event("B"), _event("C")]
        deviations = engine.detect_undocumented_activities(events)

        assert len(deviations) == 0

    def test_duplicate_undocumented_only_flagged_once(self):
        """Same undocumented activity appearing multiple times → 1 deviation."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        events = [_event("Unknown"), _event("Unknown"), _event("Unknown")]
        deviations = engine.detect_undocumented_activities(events)

        assert len(deviations) == 1


# ── Scenario 4: Deviation filtering ──


class TestDeviationFiltering:
    """Scenario 4: Tests for the deviations query endpoint schema and route registration."""

    def test_deviation_response_schema(self):
        """DeviationResponse schema has all required fields."""
        from src.api.routes.deviations import DeviationResponse

        fields = DeviationResponse.model_fields
        required_fields = {
            "id",
            "category",
            "severity",
            "process_element_id",
            "detected_at",
            "telemetry_ref",
            "engagement_id",
        }
        assert required_fields.issubset(fields.keys())

    def test_paginated_response_schema(self):
        """PaginatedDeviationResponse has items, total, limit, offset."""
        from src.api.routes.deviations import PaginatedDeviationResponse

        fields = PaginatedDeviationResponse.model_fields
        assert {"items", "total", "limit", "offset"}.issubset(fields.keys())

    def test_deviations_route_registered(self):
        """GET /api/v1/deviations route is registered."""
        from src.api.routes.deviations import router

        paths = [r.path for r in router.routes]
        assert any("/deviations" in p or p == "" for p in paths)

    def test_deviations_route_in_app(self):
        """Deviations router included in the FastAPI app."""
        from src.api.main import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert any("deviations" in r for r in routes)


# ── Engine integration tests ──


class TestDeviationEngineIntegration:
    """Integration tests for the full DeviationEngine.detect_all method."""

    def test_detect_all_combines_all_types(self):
        """detect_all finds skipped, timing, and undocumented deviations."""
        elements = [
            PovElement(id="e1", name="Step A", importance_score=0.5),
            PovElement(id="e2", name="Step B", importance_score=0.8, expected_duration_range=(1.0, 2.0)),
            PovElement(id="e3", name="Step C", importance_score=0.6),
        ]
        baseline = _baseline(elements=elements)
        engine = DeviationEngine(baseline)

        # Step A present, Step B with timing anomaly, Step C skipped, Unknown new
        events = [
            _event("Step A"),
            _event("Step B", duration_hours=10.0),
            _event("Unknown Step"),
        ]

        deviations = engine.detect_all(events)

        types = {d.deviation_type for d in deviations}
        assert DeviationType.SKIPPED_ACTIVITY in types  # Step C missing
        assert DeviationType.TIMING_ANOMALY in types  # Step B 10h vs 1-2h
        assert DeviationType.UNDOCUMENTED_ACTIVITY in types  # Unknown Step

    def test_detect_all_empty_events(self):
        """No events → all baseline activities are skipped."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_all([])

        assert len(deviations) == 3  # All 3 baseline activities skipped
        assert all(d.deviation_type == DeviationType.SKIPPED_ACTIVITY for d in deviations)

    def test_deviation_record_has_unique_id(self):
        """Every DeviationRecord gets a unique UUID."""
        baseline = _baseline()
        engine = DeviationEngine(baseline)

        deviations = engine.detect_all([])

        ids = [d.id for d in deviations]
        assert len(ids) == len(set(ids))

    def test_custom_magnitude_coefficients(self):
        """Custom coefficients change severity scoring."""
        baseline = _baseline()
        engine_default = DeviationEngine(baseline)
        engine_custom = DeviationEngine(
            baseline,
            magnitude_coefficients={
                DeviationType.SKIPPED_ACTIVITY: 0.1,  # Much lower
            },
        )

        devs_default = engine_default.detect_skipped_activities(["C"])
        devs_custom = engine_custom.detect_skipped_activities(["C"])

        # Default coefficient = 1.0, custom = 0.1
        assert devs_default[0].severity_score > devs_custom[0].severity_score


# ── Helper unit tests ──


class TestClassifySeverity:
    """Unit tests for the classify_severity helper."""

    def test_critical_threshold(self):
        assert classify_severity(0.95) == DeviationSeverity.CRITICAL

    def test_high_threshold(self):
        assert classify_severity(0.75) == DeviationSeverity.HIGH

    def test_medium_threshold(self):
        assert classify_severity(0.50) == DeviationSeverity.MEDIUM

    def test_low_threshold(self):
        assert classify_severity(0.25) == DeviationSeverity.LOW

    def test_info_threshold(self):
        assert classify_severity(0.10) == DeviationSeverity.INFO

    def test_zero_is_info(self):
        assert classify_severity(0.0) == DeviationSeverity.INFO

    def test_boundary_high(self):
        assert classify_severity(0.70) == DeviationSeverity.HIGH

    def test_boundary_critical(self):
        assert classify_severity(0.90) == DeviationSeverity.CRITICAL


class TestDeviationTypes:
    """Tests for DeviationType and DeviationSeverity enums."""

    def test_deviation_types_are_strings(self):
        assert DeviationType.SKIPPED_ACTIVITY == "skipped_activity"
        assert DeviationType.TIMING_ANOMALY == "timing_anomaly"
        assert DeviationType.UNDOCUMENTED_ACTIVITY == "undocumented_activity"

    def test_severity_ordering(self):
        severities = list(DeviationSeverity)
        assert severities[0] == DeviationSeverity.CRITICAL
        assert severities[-1] == DeviationSeverity.INFO

    def test_default_coefficients_exist(self):
        assert DeviationType.SKIPPED_ACTIVITY in DEFAULT_MAGNITUDE_COEFFICIENTS
        assert DeviationType.TIMING_ANOMALY in DEFAULT_MAGNITUDE_COEFFICIENTS
        assert DeviationType.UNDOCUMENTED_ACTIVITY in DEFAULT_MAGNITUDE_COEFFICIENTS


class TestDeviationRecord:
    """Tests for the DeviationRecord dataclass."""

    def test_auto_generates_id(self):
        record = DeviationRecord()
        assert record.id != ""
        # Should be a valid UUID
        UUID(record.id)

    def test_explicit_id_preserved(self):
        record = DeviationRecord(id="custom-id-123")
        assert record.id == "custom-id-123"

    def test_default_values(self):
        record = DeviationRecord()
        assert record.deviation_type == DeviationType.SKIPPED_ACTIVITY
        assert record.severity == DeviationSeverity.INFO
        assert record.severity_score == 0.0
        assert record.details == {}


class TestPovBaseline:
    """Tests for PovBaseline auto-initialization."""

    def test_element_map_built_from_elements(self):
        elements = [PovElement(id="e1", name="Task A")]
        baseline = PovBaseline(elements=elements)
        assert "Task A" in baseline.element_map
        assert baseline.element_map["Task A"].id == "e1"

    def test_expected_sequence_built_from_elements(self):
        elements = [PovElement(name="A"), PovElement(name="B")]
        baseline = PovBaseline(elements=elements)
        assert baseline.expected_sequence == ["A", "B"]

    def test_explicit_map_not_overridden(self):
        custom_map = {"X": PovElement(id="x1", name="X")}
        baseline = PovBaseline(element_map=custom_map)
        assert "X" in baseline.element_map


class TestMigration041Structure:
    """Tests for the Alembic migration 041 structure."""

    def test_migration_file_exists(self):
        migration_path = (
            Path(__file__).resolve().parents[2] / "alembic" / "versions" / "041_deviation_engine_enhancements.py"
        )
        assert migration_path.exists()

    def test_migration_has_revision(self):
        migration_path = (
            Path(__file__).resolve().parents[2] / "alembic" / "versions" / "041_deviation_engine_enhancements.py"
        )
        spec = importlib.util.spec_from_file_location("migration_041", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "041"
        assert mod.down_revision == "040"

    def test_migration_has_upgrade_downgrade(self):
        migration_path = (
            Path(__file__).resolve().parents[2] / "alembic" / "versions" / "041_deviation_engine_enhancements.py"
        )
        spec = importlib.util.spec_from_file_location("migration_041", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
