"""Tests for the IPC protocol dataclasses."""

from __future__ import annotations

from kmflow_agent.ipc.protocol import CaptureEvent, DesktopEventType


def test_all_event_types():
    assert len(DesktopEventType) == 17
    assert DesktopEventType.APP_SWITCH == "app_switch"
    assert DesktopEventType.IDLE_END == "idle_end"


def test_capture_event_creation():
    event = CaptureEvent(
        event_type="app_switch",
        timestamp="2026-02-25T12:00:00Z",
        sequence_number=1,
        application_name="Excel",
        bundle_identifier="com.microsoft.Excel",
        window_title="Budget.xlsx",
    )
    assert event.event_type == "app_switch"
    assert event.application_name == "Excel"
    assert event.sequence_number == 1


def test_capture_event_minimal():
    event = CaptureEvent(
        event_type="mouse_click",
        timestamp="2026-02-25T12:00:00Z",
        sequence_number=42,
    )
    assert event.application_name is None
    assert event.window_title is None
    assert event.event_data is None
