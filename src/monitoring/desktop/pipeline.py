"""Desktop task mining pipeline (Story #355).

Transforms raw desktop capture data from Soroco Scout and KM4Work into
CanonicalActivityEvent items. Maps application switching patterns to
process activities using telemetric epistemic frames, tags with evidence
category 7 (Domain Communications), and supports incremental ingestion.
"""

from __future__ import annotations

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class SourceType(enum.StrEnum):
    """Desktop monitoring agent source types."""

    SOROCO_SCOUT = "soroco_scout"
    KM4WORK = "km4work"
    MANUAL_OBSERVATION = "manual_observation"


class Brightness(enum.StrEnum):
    """Confidence-based brightness classification tiers."""

    DARK = "dark"
    DIM = "dim"
    BRIGHT = "bright"


# Evidence taxonomy category for desktop captures
EVIDENCE_CATEGORY_DESKTOP = 7

# Telemetric epistemic frame confidence coefficients
# Source type -> base confidence weight
TELEMETRIC_CONFIDENCE: dict[str, float] = {
    "soroco_scout": 0.75,
    "km4work": 0.70,
    "manual_observation": 0.90,
}

# Application category -> process activity mapping patterns
APP_CATEGORY_MAPPINGS: dict[str, str] = {
    "email": "Communication",
    "browser": "Research",
    "spreadsheet": "Data Analysis",
    "word_processor": "Documentation",
    "erp": "System Transaction",
    "crm": "Client Management",
    "bpm_tool": "Process Modeling",
    "chat": "Collaboration",
    "ide": "Development",
    "file_manager": "File Management",
}


@dataclass
class DesktopCapture:
    """Raw desktop capture data from a monitoring agent.

    Attributes:
        capture_id: Unique capture identifier.
        source_type: Agent type (soroco_scout, km4work).
        session_id: User session identifier.
        user_id: User who generated the capture.
        engagement_id: Engagement this capture belongs to.
        application_name: Name of the active application.
        window_title: Title of the active window. Upstream connectors
            (Soroco Scout, KM4Work) MUST filter PII before populating
            this field. See macOS Agent L2 PII filter for patterns.
        app_category: Categorized application type.
        action_type: Type of action (app_switch, navigation, input, idle).
        timestamp: When the action occurred.
        duration_ms: Duration of the action in milliseconds.
        metadata: Additional capture-specific data.
    """

    capture_id: str = ""
    source_type: str = ""
    session_id: str = ""
    user_id: str = ""
    engagement_id: str = ""
    application_name: str = ""
    window_title: str = ""
    app_category: str = ""
    action_type: str = "app_switch"
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.capture_id:
            self.capture_id = str(uuid.uuid4())


@dataclass
class ProcessedActivity:
    """A desktop capture transformed into a canonical activity event.

    Attributes:
        event_id: Unique event identifier.
        case_id: Case identifier (session-based).
        activity_name: Mapped process activity name.
        performer_role_ref: User/role performing the activity.
        timestamp_utc: ISO 8601 UTC timestamp.
        confidence_score: Telemetric confidence (0.0-1.0).
        brightness: Confidence tier (bright/dim/dark).
        evidence_category: Evidence taxonomy category (always 7).
        evidence_refs: Related evidence artifact IDs.
        source_type: Origin monitoring agent.
        source_capture_id: Original capture ID.
        is_workaround: Whether this was flagged as a workaround.
        metadata: Additional processed data.
    """

    event_id: str = ""
    case_id: str = ""
    activity_name: str = ""
    performer_role_ref: str = ""
    timestamp_utc: str = ""
    confidence_score: float = 0.0
    brightness: str = "dim"
    evidence_category: int = EVIDENCE_CATEGORY_DESKTOP
    evidence_refs: list[str] = field(default_factory=list)
    source_type: str = ""
    source_capture_id: str = ""
    is_workaround: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())

    def to_canonical_event_dict(self, engagement_id: str = "") -> dict[str, Any]:
        """Convert to CanonicalActivityEvent-compatible dict.

        Field names align with the CanonicalActivityEvent ORM model.
        Callers must convert ``id`` to UUID and ``timestamp_utc`` to
        a timezone-aware datetime before ORM persistence.

        Args:
            engagement_id: Engagement UUID string (required for DB persistence).
        """
        return {
            "id": self.event_id,
            "case_id": self.case_id,
            "activity_name": self.activity_name,
            "performer_role_ref": self.performer_role_ref,
            "timestamp_utc": self.timestamp_utc,
            "confidence_score": self.confidence_score,
            "brightness": self.brightness,
            "evidence_refs": self.evidence_refs,
            "mapping_status": "mapped",
            "source_system": self.source_type,
            "engagement_id": engagement_id,
        }


@dataclass
class PipelineResult:
    """Result of processing a batch of desktop captures.

    Attributes:
        engagement_id: Engagement processed.
        activities: Generated canonical activity events.
        workarounds: Activities flagged as process workarounds.
        total_captures: Number of input captures.
        total_activities: Number of output activities.
        total_workarounds: Number of workarounds detected.
        errors: Processing errors encountered.
    """

    engagement_id: str = ""
    activities: list[ProcessedActivity] = field(default_factory=list)
    workarounds: list[ProcessedActivity] = field(default_factory=list)
    total_captures: int = 0
    total_activities: int = 0
    total_workarounds: int = 0
    errors: list[str] = field(default_factory=list)


def compute_confidence(
    source_type: str,
    duration_ms: int = 0,
    has_window_title: bool = True,
) -> float:
    """Compute telemetric confidence score for a desktop capture.

    Confidence is based on:
    - Source type base weight (from TELEMETRIC_CONFIDENCE)
    - Duration penalty for very short actions (<500ms)
    - Bonus for captures with window title context

    Args:
        source_type: The monitoring agent source type.
        duration_ms: Action duration in milliseconds.
        has_window_title: Whether the capture has a window title.

    Returns:
        Confidence score between 0.0 and 1.0.
    """
    base = TELEMETRIC_CONFIDENCE.get(source_type, 0.5)

    if source_type not in TELEMETRIC_CONFIDENCE:
        logger.warning("Unknown source_type %r — using default confidence 0.5", source_type)

    # Short actions are less reliable
    if duration_ms > 0 and duration_ms < 500:
        base *= 0.8

    # Missing window title reduces confidence
    if not has_window_title:
        base *= 0.9

    return min(1.0, max(0.0, base))


def classify_brightness(confidence: float) -> str:
    """Classify confidence into brightness tier.

    Args:
        confidence: Score between 0.0 and 1.0.

    Returns:
        Brightness.DARK if < 0.4, Brightness.DIM if < 0.7,
        Brightness.BRIGHT otherwise.
    """
    if confidence < 0.4:
        return Brightness.DARK
    if confidence < 0.7:
        return Brightness.DIM
    return Brightness.BRIGHT


def map_to_activity(capture: DesktopCapture) -> str:
    """Map a desktop capture to a process activity name.

    Uses the app_category to find a matching process activity.
    Falls back to the application_name if no category mapping exists.

    Args:
        capture: Desktop capture to map.

    Returns:
        Mapped activity name.
    """
    if capture.app_category and capture.app_category in APP_CATEGORY_MAPPINGS:
        return APP_CATEGORY_MAPPINGS[capture.app_category]

    # Fall back to application name
    return capture.application_name or "Unknown Activity"


def detect_workaround(
    capture: DesktopCapture,
    documented_paths: set[str] | None = None,
) -> bool:
    """Detect if a desktop capture represents a process workaround.

    A workaround is an activity that deviates from documented process paths.
    Detection checks:
    - Activity maps to a category not in documented paths
    - Application is not in the expected tool set for the process

    Args:
        capture: Desktop capture to evaluate.
        documented_paths: Set of expected activity names for the process.

    Returns:
        True if the capture appears to be a workaround.
    """
    if documented_paths is None:
        return False

    activity = map_to_activity(capture)
    return activity not in documented_paths


def process_capture(
    capture: DesktopCapture,
    documented_paths: set[str] | None = None,
) -> ProcessedActivity:
    """Transform a single desktop capture into a processed activity.

    Args:
        capture: Raw desktop capture.
        documented_paths: Expected activity names for workaround detection.

    Returns:
        ProcessedActivity ready for canonical event creation.
    """
    activity_name = map_to_activity(capture)
    confidence = compute_confidence(
        source_type=capture.source_type,
        duration_ms=capture.duration_ms,
        has_window_title=bool(capture.window_title),
    )
    brightness = classify_brightness(confidence)
    is_workaround = detect_workaround(capture, documented_paths)

    ts = capture.timestamp
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

    return ProcessedActivity(
        case_id=capture.session_id,
        activity_name=activity_name,
        performer_role_ref=capture.user_id,
        timestamp_utc=ts_str,
        confidence_score=confidence,
        brightness=brightness,
        evidence_category=EVIDENCE_CATEGORY_DESKTOP,
        source_type=capture.source_type,
        source_capture_id=capture.capture_id,
        is_workaround=is_workaround,
    )


def process_batch(
    captures: list[DesktopCapture],
    documented_paths: set[str] | None = None,
) -> PipelineResult:
    """Process a batch of desktop captures through the mining pipeline.

    Transforms raw captures into canonical activity events, detects
    workarounds, and produces a pipeline result with metrics.

    Args:
        captures: List of raw desktop captures.
        documented_paths: Expected activity names for workaround detection.

    Returns:
        PipelineResult with processed activities and metrics.
    """
    if not captures:
        return PipelineResult()

    engagement_id = captures[0].engagement_id

    result = PipelineResult(
        engagement_id=engagement_id,
        total_captures=len(captures),
    )

    for capture in captures:
        try:
            activity = process_capture(capture, documented_paths)
            result.activities.append(activity)

            if activity.is_workaround:
                result.workarounds.append(activity)

        except Exception as exc:
            result.errors.append(f"Error processing capture {capture.capture_id}: {exc}")
            logger.warning("Failed to process capture %s: %s", capture.capture_id, exc)

    result.total_activities = len(result.activities)
    result.total_workarounds = len(result.workarounds)

    logger.info(
        "Desktop mining pipeline: %d captures -> %d activities (%d workarounds) for %s",
        result.total_captures,
        result.total_activities,
        result.total_workarounds,
        engagement_id,
    )

    return result
