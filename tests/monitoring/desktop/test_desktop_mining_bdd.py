"""BDD tests for desktop task mining pipeline and gap detector (Story #355).

Tests cover all acceptance criteria from the story:
- Soroco Scout app-switching patterns mapped to process activities
- KM4Work desktop captures identify navigation patterns and workarounds
- Desktop data compared against system logs to reveal in-between work
- Continuous desktop monitoring creates evidence items incrementally
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.monitoring.desktop.gap_detector import (
    GapItem,
    TimelineEvent,
    detect_gaps,
)
from src.monitoring.desktop.pipeline import (
    EVIDENCE_CATEGORY_DESKTOP,
    DesktopCapture,
    PipelineResult,
    classify_brightness,
    compute_confidence,
    process_batch,
    process_capture,
)


def _make_capture(
    source_type: str = "soroco_scout",
    app_category: str = "email",
    application_name: str = "Outlook",
    window_title: str = "Inbox - Outlook",
    user_id: str = "user-1",
    session_id: str = "session-1",
    engagement_id: str = "eng-1",
    action_type: str = "app_switch",
    duration_ms: int = 5000,
    timestamp: datetime | None = None,
) -> DesktopCapture:
    """Build a test desktop capture."""
    return DesktopCapture(
        source_type=source_type,
        app_category=app_category,
        application_name=application_name,
        window_title=window_title,
        user_id=user_id,
        session_id=session_id,
        engagement_id=engagement_id,
        action_type=action_type,
        duration_ms=duration_ms,
        timestamp=timestamp or datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC),
    )


def _make_timeline_event(
    source: str = "system",
    activity_name: str = "Submit",
    user_id: str = "user-1",
    timestamp: datetime | None = None,
) -> TimelineEvent:
    """Build a test timeline event."""
    return TimelineEvent(
        source=source,
        activity_name=activity_name,
        user_id=user_id,
        timestamp=timestamp or datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC),
    )


# ============================================================
# Scenario 1: Soroco Scout app-switching patterns mapped
# ============================================================


class TestSorocoScoutMapping:
    """Given Soroco Scout data containing app switching sequences,
    activities are mapped using telemetric epistemic frames and
    stored as CanonicalActivityEvent with source=SOROCO_SCOUT."""

    def test_app_switch_mapped_to_activity(self) -> None:
        """App category maps to a process activity name."""
        capture = _make_capture(app_category="email")
        activity = process_capture(capture)
        assert activity.activity_name == "Communication"

    def test_soroco_source_type_preserved(self) -> None:
        """Source type is preserved as soroco_scout."""
        capture = _make_capture(source_type="soroco_scout")
        activity = process_capture(capture)
        assert activity.source_type == "soroco_scout"

    def test_confidence_uses_telemetric_weight(self) -> None:
        """Confidence score uses telemetric epistemic frame weighting."""
        confidence = compute_confidence("soroco_scout", duration_ms=5000)
        assert confidence == 0.75  # Base weight for soroco_scout

    def test_activity_has_canonical_event_fields(self) -> None:
        """Processed activity can be converted to canonical event dict."""
        capture = _make_capture()
        activity = process_capture(capture)
        event_dict = activity.to_canonical_event_dict()

        assert "case_id" in event_dict
        assert "activity_name" in event_dict
        assert "performer_role_ref" in event_dict
        assert "timestamp_utc" in event_dict
        assert "confidence_score" in event_dict
        assert "brightness" in event_dict
        assert event_dict["source"] == "soroco_scout"

    def test_session_id_used_as_case_id(self) -> None:
        """Session ID becomes the case_id for the canonical event."""
        capture = _make_capture(session_id="session-42")
        activity = process_capture(capture)
        assert activity.case_id == "session-42"

    def test_user_id_used_as_performer(self) -> None:
        """User ID becomes the performer_role_ref."""
        capture = _make_capture(user_id="analyst-bob")
        activity = process_capture(capture)
        assert activity.performer_role_ref == "analyst-bob"

    def test_multiple_app_categories_mapped(self) -> None:
        """Different app categories map to appropriate activities."""
        mappings = {
            "email": "Communication",
            "browser": "Research",
            "spreadsheet": "Data Analysis",
            "erp": "System Transaction",
        }
        for category, expected in mappings.items():
            capture = _make_capture(app_category=category)
            activity = process_capture(capture)
            assert activity.activity_name == expected, (
                f"{category} should map to {expected}"
            )

    def test_unknown_category_falls_back_to_app_name(self) -> None:
        """Unknown app category falls back to application_name."""
        capture = _make_capture(
            app_category="unknown_tool",
            application_name="CustomApp",
        )
        activity = process_capture(capture)
        assert activity.activity_name == "CustomApp"


# ============================================================
# Scenario 2: KM4Work captures identify workarounds
# ============================================================


class TestKM4WorkWorkaroundDetection:
    """Given KM4Work desktop capture data, workarounds (deviations
    from documented paths) are flagged and tagged with category 7."""

    def test_workaround_detected_when_outside_documented_paths(self) -> None:
        """Activity not in documented paths is flagged as workaround."""
        capture = _make_capture(
            source_type="km4work",
            app_category="spreadsheet",
        )
        documented = {"Communication", "System Transaction"}
        activity = process_capture(capture, documented_paths=documented)
        assert activity.is_workaround is True

    def test_documented_activity_not_flagged(self) -> None:
        """Activity in documented paths is NOT flagged as workaround."""
        capture = _make_capture(
            source_type="km4work",
            app_category="email",
        )
        documented = {"Communication", "System Transaction"}
        activity = process_capture(capture, documented_paths=documented)
        assert activity.is_workaround is False

    def test_evidence_category_7_applied(self) -> None:
        """All desktop captures tagged with evidence category 7."""
        capture = _make_capture(source_type="km4work")
        activity = process_capture(capture)
        assert activity.evidence_category == EVIDENCE_CATEGORY_DESKTOP
        assert activity.evidence_category == 7

    def test_km4work_confidence_coefficient(self) -> None:
        """KM4Work source uses its specific confidence coefficient."""
        confidence = compute_confidence("km4work", duration_ms=5000)
        assert confidence == 0.70

    def test_workaround_included_in_batch_result(self) -> None:
        """Workarounds are collected in PipelineResult.workarounds."""
        captures = [
            _make_capture(app_category="email"),       # Not workaround
            _make_capture(app_category="spreadsheet"),  # Workaround
        ]
        documented = {"Communication"}
        result = process_batch(captures, documented_paths=documented)
        assert result.total_workarounds == 1
        assert result.workarounds[0].activity_name == "Data Analysis"

    def test_batch_without_documented_paths_no_workarounds(self) -> None:
        """Without documented paths, no workarounds are detected."""
        captures = [_make_capture()]
        result = process_batch(captures)
        assert result.total_workarounds == 0


# ============================================================
# Scenario 3: Desktop vs system logs reveal in-between work
# ============================================================


class TestInBetweenWorkDetection:
    """Given desktop and system event log data covering the same window,
    discrepancies are identified as candidate in-between work items."""

    def test_gap_detected_between_system_events(self) -> None:
        """Gap found where desktop activity exists but no system events."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(
                activity_name="Submit", timestamp=base_ts
            ),
            _make_timeline_event(
                activity_name="Approve",
                timestamp=base_ts + timedelta(minutes=30),
            ),
        ]

        desktop_events = [
            _make_timeline_event(
                source="desktop",
                activity_name="Email check",
                timestamp=base_ts + timedelta(minutes=10),
            ),
            _make_timeline_event(
                source="desktop",
                activity_name="Spreadsheet work",
                timestamp=base_ts + timedelta(minutes=20),
            ),
        ]

        result = detect_gaps(desktop_events, system_events, user_id="user-1")

        assert result.total_gaps == 1
        gap = result.gaps[0]
        assert gap.desktop_event_count == 2
        assert gap.preceding_system_event == "Submit"
        assert gap.following_system_event == "Approve"

    def test_gap_duration_calculated_correctly(self) -> None:
        """Gap duration equals time between system events."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=15)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=5),
            ),
        ]

        result = detect_gaps(desktop_events, system_events)
        assert result.gaps[0].gap_duration_seconds == 900  # 15 min

    def test_no_gap_when_no_desktop_activity(self) -> None:
        """No gap flagged when there's no desktop activity between events."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=15)),
        ]

        result = detect_gaps([], system_events)
        assert result.total_gaps == 0

    def test_gap_below_min_threshold_ignored(self) -> None:
        """Gaps shorter than min_gap_seconds are not flagged."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(seconds=30)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(seconds=15),
            ),
        ]

        result = detect_gaps(
            desktop_events, system_events, min_gap_seconds=60
        )
        assert result.total_gaps == 0

    def test_gap_above_max_threshold_ignored(self) -> None:
        """Gaps longer than max_gap_seconds are not flagged (break periods)."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(hours=3)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(hours=1),
            ),
        ]

        result = detect_gaps(
            desktop_events, system_events, max_gap_seconds=7200
        )
        assert result.total_gaps == 0

    def test_recommended_action_for_long_gap(self) -> None:
        """Long gaps (>30min) recommend SME interview."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=45)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=10),
            ),
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=20),
            ),
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=30),
            ),
        ]

        result = detect_gaps(desktop_events, system_events)
        assert "SME interview" in result.gaps[0].recommended_action

    def test_recommended_action_for_short_gap(self) -> None:
        """Short gaps recommend reviewing desktop actions."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=10)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=5),
            ),
        ]

        result = detect_gaps(desktop_events, system_events)
        assert "Review" in result.gaps[0].recommended_action

    def test_multiple_gaps_detected(self) -> None:
        """Multiple gaps between different system event pairs are found."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=10)),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=25)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=5),
            ),
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=15),
            ),
        ]

        result = detect_gaps(desktop_events, system_events)
        assert result.total_gaps == 2

    def test_total_gap_seconds_aggregated(self) -> None:
        """Total gap seconds is the sum of all gap durations."""
        base_ts = datetime(2026, 2, 15, 9, 0, 0, tzinfo=UTC)

        system_events = [
            _make_timeline_event(timestamp=base_ts),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=5)),
            _make_timeline_event(timestamp=base_ts + timedelta(minutes=15)),
        ]
        desktop_events = [
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=2),
            ),
            _make_timeline_event(
                source="desktop",
                timestamp=base_ts + timedelta(minutes=10),
            ),
        ]

        result = detect_gaps(desktop_events, system_events)
        assert result.total_gap_seconds == 300 + 600  # 5min + 10min


# ============================================================
# Scenario 4: Incremental evidence creation
# ============================================================


class TestIncrementalIngestion:
    """Given desktop monitoring is active, new captures create
    evidence items incrementally without full re-ingestion."""

    def test_single_capture_produces_single_activity(self) -> None:
        """Processing a single capture produces exactly one activity."""
        captures = [_make_capture()]
        result = process_batch(captures)
        assert result.total_activities == 1

    def test_batch_preserves_engagement_id(self) -> None:
        """Pipeline result carries the engagement_id."""
        captures = [_make_capture(engagement_id="eng-42")]
        result = process_batch(captures)
        assert result.engagement_id == "eng-42"

    def test_incremental_batches_produce_independent_results(self) -> None:
        """Two batches produce independent results (no state leakage)."""
        batch1 = [_make_capture(session_id="s1")]
        batch2 = [_make_capture(session_id="s2")]

        result1 = process_batch(batch1)
        result2 = process_batch(batch2)

        assert result1.total_activities == 1
        assert result2.total_activities == 1
        assert result1.activities[0].case_id == "s1"
        assert result2.activities[0].case_id == "s2"

    def test_each_activity_has_unique_event_id(self) -> None:
        """Each processed activity gets a unique event_id."""
        captures = [
            _make_capture(session_id="s1"),
            _make_capture(session_id="s2"),
        ]
        result = process_batch(captures)
        ids = [a.event_id for a in result.activities]
        assert len(set(ids)) == 2

    def test_empty_batch_returns_empty_result(self) -> None:
        """Empty batch produces zero activities."""
        result = process_batch([])
        assert result.total_activities == 0
        assert result.total_captures == 0


# ============================================================
# Confidence and brightness tests
# ============================================================


class TestConfidenceComputation:
    """Tests for telemetric confidence scoring."""

    def test_short_duration_reduces_confidence(self) -> None:
        """Actions < 500ms get a confidence penalty."""
        normal = compute_confidence("soroco_scout", duration_ms=5000)
        short = compute_confidence("soroco_scout", duration_ms=200)
        assert short < normal

    def test_missing_window_title_reduces_confidence(self) -> None:
        """Missing window title slightly reduces confidence."""
        with_title = compute_confidence("soroco_scout", has_window_title=True)
        without = compute_confidence("soroco_scout", has_window_title=False)
        assert without < with_title

    def test_unknown_source_gets_default_confidence(self) -> None:
        """Unknown source type gets 0.5 base confidence."""
        confidence = compute_confidence("unknown_agent", duration_ms=5000)
        assert confidence == 0.5

    def test_confidence_clamped_to_zero_one(self) -> None:
        """Confidence is always between 0.0 and 1.0."""
        c = compute_confidence("manual_observation", duration_ms=10000)
        assert 0.0 <= c <= 1.0


class TestBrightnessClassification:
    """Tests for brightness tier classification."""

    def test_dark_below_04(self) -> None:
        assert classify_brightness(0.3) == "dark"

    def test_dim_between_04_07(self) -> None:
        assert classify_brightness(0.5) == "dim"

    def test_bright_above_07(self) -> None:
        assert classify_brightness(0.8) == "bright"

    def test_boundary_04_is_dim(self) -> None:
        assert classify_brightness(0.4) == "dim"

    def test_boundary_07_is_bright(self) -> None:
        assert classify_brightness(0.7) == "bright"


# ============================================================
# Dataclass tests
# ============================================================


class TestDesktopCapture:
    """Tests for DesktopCapture dataclass."""

    def test_auto_generates_capture_id(self) -> None:
        capture = DesktopCapture()
        assert len(capture.capture_id) == 36

    def test_default_action_type(self) -> None:
        capture = DesktopCapture()
        assert capture.action_type == "app_switch"


class TestGapItem:
    """Tests for GapItem dataclass."""

    def test_to_dict_all_fields(self) -> None:
        gap = GapItem(
            user_id="user-1",
            gap_duration_seconds=900,
            desktop_event_count=3,
            preceding_system_event="Submit",
            following_system_event="Approve",
            recommended_action="Review desktop actions",
        )
        d = gap.to_dict()
        assert d["user_id"] == "user-1"
        assert d["gap_duration_seconds"] == 900
        assert d["desktop_event_count"] == 3
        assert "gap_start" in d
        assert "gap_end" in d

    def test_auto_generates_gap_id(self) -> None:
        gap = GapItem()
        assert len(gap.gap_id) == 36


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_default_empty_result(self) -> None:
        result = PipelineResult()
        assert result.total_captures == 0
        assert result.total_activities == 0
        assert result.errors == []
