"""Event protocol matching the Swift EventProtocol.swift definitions.

These dataclasses MUST stay in sync with agent/macos/Sources/IPC/EventProtocol.swift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DesktopEventType(StrEnum):
    """Mirrors src/core/models/taskmining.py DesktopEventType."""

    APP_SWITCH = "app_switch"
    WINDOW_FOCUS = "window_focus"
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_DRAG = "mouse_drag"
    KEYBOARD_ACTION = "keyboard_action"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    COPY_PASTE = "copy_paste"
    SCROLL = "scroll"
    TAB_SWITCH = "tab_switch"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    URL_NAVIGATION = "url_navigation"
    SCREEN_CAPTURE = "screen_capture"
    UI_ELEMENT_INTERACTION = "ui_element_interaction"
    IDLE_START = "idle_start"
    IDLE_END = "idle_end"


@dataclass
class CaptureEvent:
    """A single desktop event received from the Swift layer."""

    event_type: str
    timestamp: str
    sequence_number: int
    application_name: str | None = None
    bundle_identifier: str | None = None
    window_title: str | None = None
    event_data: dict[str, Any] | None = None
    idempotency_key: str | None = None


@dataclass
class IPCMessage:
    """Envelope wrapping a capture event with metadata."""

    version: int
    sequence_number: int
    timestamp_ns: int
    event: CaptureEvent
