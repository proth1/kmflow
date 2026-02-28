"""In-between work gap detector (Story #355).

Compares desktop task mining data against system event logs to identify
discrepancies — periods where users were active on their desktops but
no system events were recorded. These gaps represent candidate "in-between
work" items that need evidence acquisition.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Minimum gap duration to consider as in-between work (seconds)
DEFAULT_MIN_GAP_SECONDS = 60

# Maximum gap to consider (avoid flagging multi-hour breaks)
DEFAULT_MAX_GAP_SECONDS = 7200  # 2 hours


@dataclass
class TimelineEvent:
    """An event on a timeline (from either desktop or system source).

    Attributes:
        event_id: Unique event identifier.
        source: Event source (desktop, system).
        timestamp: When the event occurred.
        end_timestamp: When the event ended (optional).
        activity_name: Name of the activity.
        user_id: User who generated the event.
        metadata: Additional event data.
    """

    event_id: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    end_timestamp: datetime | None = None
    activity_name: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class GapItem:
    """A detected gap representing candidate in-between work.

    Attributes:
        gap_id: Unique gap identifier.
        user_id: User who was active during the gap.
        gap_start: Start of the gap window.
        gap_end: End of the gap window.
        gap_duration_seconds: Duration of the gap in seconds.
        desktop_events_in_gap: Desktop events that occurred during the gap.
        desktop_event_count: Number of desktop events in the gap.
        preceding_system_event: The system event before the gap.
        following_system_event: The system event after the gap.
        recommended_action: Suggested evidence acquisition action.
    """

    gap_id: str = ""
    user_id: str = ""
    gap_start: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    gap_end: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    gap_duration_seconds: int = 0
    desktop_events_in_gap: list[TimelineEvent] = field(default_factory=list)
    desktop_event_count: int = 0
    preceding_system_event: str = ""
    following_system_event: str = ""
    recommended_action: str = ""

    def __post_init__(self) -> None:
        if not self.gap_id:
            self.gap_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """Serialize gap item for API response."""
        return {
            "gap_id": self.gap_id,
            "user_id": self.user_id,
            "gap_start": self.gap_start.isoformat(),
            "gap_end": self.gap_end.isoformat(),
            "gap_duration_seconds": self.gap_duration_seconds,
            "desktop_event_count": self.desktop_event_count,
            "preceding_system_event": self.preceding_system_event,
            "following_system_event": self.following_system_event,
            "recommended_action": self.recommended_action,
        }


@dataclass
class GapAnalysisResult:
    """Result of in-between work gap analysis.

    Attributes:
        user_id: User analyzed.
        analysis_window_start: Start of the analysis time window.
        analysis_window_end: End of the analysis time window.
        gaps: Detected gap items.
        total_gaps: Number of gaps found.
        total_gap_seconds: Total gap duration in seconds.
        total_desktop_events: Total desktop events in the analysis window.
        total_system_events: Total system events in the analysis window.
    """

    user_id: str = ""
    analysis_window_start: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    analysis_window_end: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    gaps: list[GapItem] = field(default_factory=list)
    total_gaps: int = 0
    total_gap_seconds: int = 0
    total_desktop_events: int = 0
    total_system_events: int = 0


def _sort_events_by_timestamp(
    events: list[TimelineEvent],
) -> list[TimelineEvent]:
    """Sort events chronologically by timestamp."""
    return sorted(events, key=lambda e: e.timestamp)


def _find_desktop_events_in_window(
    desktop_events: list[TimelineEvent],
    start: datetime,
    end: datetime,
) -> list[TimelineEvent]:
    """Find desktop events that fall within a time window.

    Args:
        desktop_events: Sorted desktop events.
        start: Window start (exclusive).
        end: Window end (exclusive).

    Returns:
        Desktop events within the window.
    """
    return [e for e in desktop_events if start < e.timestamp < end]


def _recommend_action(gap: GapItem) -> str:
    """Generate a recommended evidence acquisition action for a gap.

    Args:
        gap: The detected gap item.

    Returns:
        Recommended action string.
    """
    if gap.desktop_event_count == 0:
        return "Investigate idle period — no desktop activity detected"

    if gap.gap_duration_seconds > 1800:  # > 30 minutes
        return (
            f"Schedule SME interview — {gap.desktop_event_count} desktop actions "
            f"over {gap.gap_duration_seconds // 60} minutes with no system trace"
        )

    return f"Review {gap.desktop_event_count} desktop actions for undocumented process steps between system events"


def detect_gaps(
    desktop_events: list[TimelineEvent],
    system_events: list[TimelineEvent],
    user_id: str = "",
    min_gap_seconds: int = DEFAULT_MIN_GAP_SECONDS,
    max_gap_seconds: int = DEFAULT_MAX_GAP_SECONDS,
) -> GapAnalysisResult:
    """Detect in-between work gaps by comparing desktop and system timelines.

    Walks through consecutive system events and identifies windows where
    desktop activity exists but no system events were recorded.

    Args:
        desktop_events: Desktop capture events sorted chronologically.
        system_events: System log events sorted chronologically.
        user_id: User being analyzed.
        min_gap_seconds: Minimum gap duration to flag (default: 60s).
        max_gap_seconds: Maximum gap duration to consider (default: 7200s).

    Returns:
        GapAnalysisResult with detected gaps and metrics.
    """
    sorted_desktop = _sort_events_by_timestamp(desktop_events)
    sorted_system = _sort_events_by_timestamp(system_events)

    result = GapAnalysisResult(
        user_id=user_id,
        total_desktop_events=len(sorted_desktop),
        total_system_events=len(sorted_system),
    )

    if sorted_desktop:
        result.analysis_window_start = sorted_desktop[0].timestamp
        result.analysis_window_end = sorted_desktop[-1].timestamp

    if len(sorted_system) < 2:
        # Need at least 2 system events to find gaps between them
        return result

    # Walk through consecutive system event pairs
    for i in range(len(sorted_system) - 1):
        sys_before = sorted_system[i]
        sys_after = sorted_system[i + 1]

        gap_start = sys_before.timestamp
        gap_end = sys_after.timestamp
        gap_seconds = int((gap_end - gap_start).total_seconds())

        # Skip gaps that are too short or too long
        if gap_seconds < min_gap_seconds or gap_seconds > max_gap_seconds:
            continue

        # Find desktop events in this gap
        desktop_in_gap = _find_desktop_events_in_window(sorted_desktop, gap_start, gap_end)

        # Only flag as a gap if there IS desktop activity (user was working)
        if not desktop_in_gap:
            continue

        gap = GapItem(
            user_id=user_id,
            gap_start=gap_start,
            gap_end=gap_end,
            gap_duration_seconds=gap_seconds,
            desktop_events_in_gap=desktop_in_gap,
            desktop_event_count=len(desktop_in_gap),
            preceding_system_event=sys_before.activity_name,
            following_system_event=sys_after.activity_name,
        )
        gap.recommended_action = _recommend_action(gap)

        result.gaps.append(gap)

    result.total_gaps = len(result.gaps)
    result.total_gap_seconds = sum(g.gap_duration_seconds for g in result.gaps)

    logger.info(
        "Gap analysis for user %s: %d gaps (%d total seconds) from %d desktop + %d system events",
        user_id,
        result.total_gaps,
        result.total_gap_seconds,
        result.total_desktop_events,
        result.total_system_events,
    )

    return result
