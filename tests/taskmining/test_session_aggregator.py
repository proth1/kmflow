"""Tests for the session aggregation engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.taskmining.aggregation.session import SessionAggregator


def _ts(minutes: int = 0, seconds: int = 0) -> str:
    """Helper: generate ISO timestamp offset from a base time."""
    base = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
    return (base + timedelta(minutes=minutes, seconds=seconds)).isoformat()


def _event(event_type: str, app: str, minutes: int = 0, seconds: int = 0, **kwargs) -> dict:
    """Helper: build an event dict."""
    return {
        "event_type": event_type,
        "application_name": app,
        "timestamp": _ts(minutes, seconds),
        "session_id": "test-session",
        "engagement_id": "test-engagement",
        **kwargs,
    }


class TestSessionGrouping:
    """Scenario: Events grouped into sessions by app context."""

    def test_single_app_session(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=1),
            _event("keyboard_action", "Excel", minutes=2),
            _event("mouse_click", "Excel", minutes=3),
            _event("app_switch", "Outlook", minutes=8),  # Switch ends Excel session
        ]
        sessions = agg.process_events(events)
        assert len(sessions) == 1
        assert sessions[0].app_bundle_id == "Excel"
        assert sessions[0].keyboard_event_count == 2
        assert sessions[0].mouse_event_count == 1
        assert sessions[0].total_event_count == 3  # excludes app_switch events

    def test_multiple_app_sessions(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=4),
            _event("app_switch", "Outlook", minutes=8),
            _event("keyboard_action", "Outlook", minutes=9),
            _event("app_switch", "Excel", minutes=10),  # Return to Excel
        ]
        sessions = agg.process_events(events)
        assert len(sessions) == 2
        assert sessions[0].app_bundle_id == "Excel"
        assert sessions[1].app_bundle_id == "Outlook"

    def test_session_has_duration(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=5),
            _event("app_switch", "Outlook", minutes=8),
        ]
        sessions = agg.process_events(events)
        assert len(sessions) == 1
        assert sessions[0].duration_ms == 8 * 60 * 1000  # 8 minutes

    def test_session_records_window_title(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=1, window_title="Budget.xlsx"),
            _event("keyboard_action", "Excel", minutes=2, window_title="Revenue.xlsx"),
            _event("app_switch", "Other", minutes=3),
        ]
        sessions = agg.process_events(events)
        # First non-null title is used
        assert sessions[0].window_title_sample == "Budget.xlsx"

    def test_session_records_engagement_id(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("app_switch", "Other", minutes=5),
        ]
        sessions = agg.process_events(events)
        assert sessions[0].engagement_id == "test-engagement"
        assert sessions[0].session_id == "test-session"


class TestIdleHandling:
    """Scenario: IDLE_START and IDLE_END correctly bound session duration."""

    def test_idle_excluded_from_active_duration(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=2),
            _event("idle_start", "Excel", minutes=5),
            _event("idle_end", "Excel", minutes=25),  # 20 min idle
            _event("keyboard_action", "Excel", minutes=26),
            _event("app_switch", "Outlook", minutes=30),
        ]
        sessions = agg.process_events(events)
        assert len(sessions) == 1
        session = sessions[0]
        assert session.idle_duration_ms == 20 * 60 * 1000  # 20 minutes
        assert session.duration_ms == 30 * 60 * 1000  # 30 minutes total
        assert session.active_duration_ms == 10 * 60 * 1000  # 10 minutes active

    def test_idle_without_end_ignored(self):
        """IDLE_START with no IDLE_END — idle not counted."""
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("idle_start", "Excel", minutes=5),
            _event("app_switch", "Other", minutes=10),
        ]
        sessions = agg.process_events(events)
        assert sessions[0].idle_duration_ms == 0


class TestFlush:
    """Test force-completing the active session."""

    def test_flush_completes_active_session(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "Excel", minutes=0),
            _event("keyboard_action", "Excel", minutes=5),
        ]
        agg.process_events(events)
        sessions = agg.flush()
        assert len(sessions) == 1
        assert sessions[0].app_bundle_id == "Excel"
        assert sessions[0].is_complete

    def test_flush_empty_returns_nothing(self):
        agg = SessionAggregator()
        sessions = agg.flush()
        assert len(sessions) == 0


class TestEventCounting:
    """Test that all event types are counted correctly."""

    def test_all_event_types_counted(self):
        agg = SessionAggregator()
        events = [
            _event("app_switch", "App", minutes=0),
            _event("keyboard_action", "App", minutes=1),
            _event("keyboard_shortcut", "App", minutes=1, seconds=10),
            _event("mouse_click", "App", minutes=2),
            _event("mouse_double_click", "App", minutes=2, seconds=10),
            _event("mouse_drag", "App", minutes=2, seconds=20),
            _event("copy_paste", "App", minutes=3),
            _event("scroll", "App", minutes=4),
            _event("file_open", "App", minutes=5),
            _event("file_save", "App", minutes=6),
            _event("url_navigation", "App", minutes=7),
            _event("app_switch", "Other", minutes=10),
        ]
        sessions = agg.process_events(events)
        s = sessions[0]
        assert s.keyboard_event_count == 2
        assert s.mouse_event_count == 3
        assert s.copy_paste_count == 1
        assert s.scroll_count == 1
        assert s.file_operation_count == 2
        assert s.url_navigation_count == 1
        assert s.total_event_count == 10

    def test_empty_event_stream(self):
        agg = SessionAggregator()
        sessions = agg.process_events([])
        assert len(sessions) == 0

    def test_events_without_timestamp_skipped(self):
        agg = SessionAggregator()
        events = [
            {"event_type": "keyboard_action", "application_name": "App"},  # No timestamp
            _event("app_switch", "App", minutes=0),
            _event("app_switch", "Other", minutes=5),
        ]
        sessions = agg.process_events(events)
        assert len(sessions) == 1
