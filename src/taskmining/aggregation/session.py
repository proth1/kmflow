"""App session aggregation: groups raw events into bounded application sessions.

A session is a continuous period of activity within a single application+window
context. Sessions are bounded by app switches, idle periods, or configurable
time windows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.models.taskmining import DesktopEventType

logger = logging.getLogger(__name__)

# Events that contribute to interaction counts
_KEYBOARD_EVENTS = {DesktopEventType.KEYBOARD_ACTION, DesktopEventType.KEYBOARD_SHORTCUT}
_MOUSE_EVENTS = {
    DesktopEventType.MOUSE_CLICK,
    DesktopEventType.MOUSE_DOUBLE_CLICK,
    DesktopEventType.MOUSE_DRAG,
}
_FILE_EVENTS = {DesktopEventType.FILE_OPEN, DesktopEventType.FILE_SAVE}


@dataclass
class AggregatedSession:
    """A bounded application session with interaction counts."""

    app_bundle_id: str
    window_title_sample: str | None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int = 0
    active_duration_ms: int = 0
    idle_duration_ms: int = 0
    keyboard_event_count: int = 0
    mouse_event_count: int = 0
    copy_paste_count: int = 0
    scroll_count: int = 0
    file_operation_count: int = 0
    url_navigation_count: int = 0
    total_event_count: int = 0
    session_id: str | None = None
    engagement_id: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.ended_at is not None

    def compute_duration(self) -> None:
        """Compute final duration fields from timestamps."""
        if self.ended_at and self.started_at:
            total = int((self.ended_at - self.started_at).total_seconds() * 1000)
            self.duration_ms = total
            self.active_duration_ms = total - self.idle_duration_ms


class SessionAggregator:
    """Groups raw desktop events into bounded application sessions.

    Events are processed in timestamp order. A new session starts when:
    - An APP_SWITCH event arrives with a different app
    - The idle threshold is exceeded
    - No active session exists
    """

    def __init__(self, idle_threshold_seconds: int = 300) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self._active_session: AggregatedSession | None = None
        self._completed_sessions: list[AggregatedSession] = []
        self._idle_start: datetime | None = None

    @property
    def completed_sessions(self) -> list[AggregatedSession]:
        return list(self._completed_sessions)

    def process_events(self, events: list[dict[str, Any]]) -> list[AggregatedSession]:
        """Process a batch of events and return completed sessions.

        Events should be sorted by timestamp. Returns sessions that were
        completed during this batch.
        """
        initial_count = len(self._completed_sessions)

        for event in events:
            self._process_single_event(event)

        # Return only the sessions completed during this batch
        return self._completed_sessions[initial_count:]

    def flush(self) -> list[AggregatedSession]:
        """Force-complete any active session and return all completed sessions."""
        if self._active_session:
            self._close_session(datetime.now(timezone.utc))
        result = list(self._completed_sessions)
        self._completed_sessions.clear()
        return result

    def _process_single_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event_type", "")
        timestamp_str = event.get("timestamp")
        if not timestamp_str:
            return
        timestamp = _parse_timestamp(timestamp_str)
        app_name = event.get("application_name", "")
        bundle_id = app_name  # Use app name as bundle proxy when bundle_id not in event
        window_title = event.get("window_title")
        session_id = event.get("session_id")
        engagement_id = event.get("engagement_id")

        # Handle idle events
        if event_type == DesktopEventType.IDLE_START:
            self._idle_start = timestamp
            return

        if event_type == DesktopEventType.IDLE_END:
            if self._idle_start and self._active_session:
                idle_ms = int((timestamp - self._idle_start).total_seconds() * 1000)
                self._active_session.idle_duration_ms += idle_ms
            self._idle_start = None
            return

        # Handle app switch: close current session, start new one
        if event_type == DesktopEventType.APP_SWITCH:
            if self._active_session and self._active_session.app_bundle_id != app_name:
                self._close_session(timestamp)
            if app_name:
                self._start_session(app_name, window_title, timestamp, session_id, engagement_id)
            return

        # For all other events: ensure a session exists, then count
        if not self._active_session:
            if app_name:
                self._start_session(app_name, window_title, timestamp, session_id, engagement_id)
            else:
                return

        session = self._active_session
        if session is None:
            return
        session.total_event_count += 1

        # Update window title sample if not set
        if window_title and not session.window_title_sample:
            session.window_title_sample = window_title

        # Count by event type
        if event_type in _KEYBOARD_EVENTS:
            session.keyboard_event_count += 1
        elif event_type in _MOUSE_EVENTS:
            session.mouse_event_count += 1
        elif event_type == DesktopEventType.COPY_PASTE:
            session.copy_paste_count += 1
        elif event_type == DesktopEventType.SCROLL:
            session.scroll_count += 1
        elif event_type in _FILE_EVENTS:
            session.file_operation_count += 1
        elif event_type == DesktopEventType.URL_NAVIGATION:
            session.url_navigation_count += 1

    def _start_session(
        self,
        app_name: str,
        window_title: str | None,
        timestamp: datetime,
        session_id: str | None = None,
        engagement_id: str | None = None,
    ) -> None:
        self._active_session = AggregatedSession(
            app_bundle_id=app_name,
            window_title_sample=window_title,
            started_at=timestamp,
            session_id=session_id,
            engagement_id=engagement_id,
        )

    def _close_session(self, end_time: datetime) -> None:
        if self._active_session:
            self._active_session.ended_at = end_time
            self._active_session.compute_duration()
            self._completed_sessions.append(self._active_session)
            self._active_session = None
            self._idle_start = None


def _parse_timestamp(ts: str | datetime) -> datetime:
    """Parse an ISO 8601 timestamp string or return a datetime as-is."""
    if isinstance(ts, datetime):
        return ts
    # Handle Z suffix
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)
