"""Single-case timeline replay service (Story #337).

Builds replay frames from canonical activity events in the event spine.
Each frame exposes activity name, performer, timestamp, confidence score,
brightness classification, and evidence references. Frames are stored in
the replay task store for paginated retrieval.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Brightness thresholds (aligned with consensus confidence model)
_DARK_THRESHOLD = 0.4
_DIM_THRESHOLD = 0.7


@dataclass
class SingleCaseFrame:
    """A single frame in a single-case replay sequence.

    Attributes:
        frame_index: Zero-based position in the timeline.
        activity_name: Name of the process activity.
        performer: Role or user performing the activity.
        timestamp_utc: ISO 8601 UTC timestamp of the event.
        confidence_score: Confidence score (0.0-1.0).
        brightness: Classification (bright/dim/dark) based on confidence.
        evidence_refs: UUIDs of supporting evidence artifacts.
    """

    frame_index: int
    activity_name: str
    performer: str
    timestamp_utc: str
    confidence_score: float
    brightness: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize frame to dict for API response."""
        return {
            "frame_index": self.frame_index,
            "activity_name": self.activity_name,
            "performer": self.performer,
            "timestamp_utc": self.timestamp_utc,
            "confidence_score": self.confidence_score,
            "brightness": self.brightness,
            "evidence_refs": self.evidence_refs,
        }


@dataclass
class SingleCaseReplayResult:
    """Result of a single-case replay generation.

    Attributes:
        task_id: Unique replay task identifier.
        case_id: The case being replayed.
        status: Task status (pending/completed/failed).
        frames: Generated replay frames in chronological order.
        total_frames: Number of frames generated.
        created_at: ISO 8601 creation timestamp.
        error: Error message if generation failed.
    """

    task_id: str = ""
    case_id: str = ""
    status: str = "pending"
    frames: list[SingleCaseFrame] = field(default_factory=list)
    total_frames: int = 0
    created_at: str = ""
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(tz=UTC).isoformat()

    def to_status_dict(self) -> dict[str, Any]:
        """Serialize task status for polling endpoint."""
        return {
            "task_id": self.task_id,
            "replay_type": "single_case",
            "status": self.status,
            "progress_pct": 100 if self.status == "completed" else 0,
            "created_at": self.created_at,
        }


def classify_brightness(confidence_score: float) -> str:
    """Classify confidence score into brightness tier.

    Args:
        confidence_score: Value between 0.0 and 1.0.

    Returns:
        "dark" if < 0.4, "dim" if < 0.7, "bright" otherwise.
    """
    if confidence_score < _DARK_THRESHOLD:
        return "dark"
    if confidence_score < _DIM_THRESHOLD:
        return "dim"
    return "bright"


def build_frames_from_events(
    events: list[dict[str, Any]],
) -> list[SingleCaseFrame]:
    """Convert canonical activity events into replay frames.

    Events are expected to be pre-sorted in chronological order.
    Each event dict should contain keys matching CanonicalActivityEvent
    columns: activity_name, performer_role_ref, timestamp_utc,
    confidence_score, brightness, evidence_refs.

    Args:
        events: List of event dicts from the canonical event spine.

    Returns:
        List of SingleCaseFrame in chronological order.
    """
    frames: list[SingleCaseFrame] = []

    for i, event in enumerate(events):
        confidence = float(event.get("confidence_score", 0.0))

        # Use existing brightness or compute from confidence
        brightness = event.get("brightness") or classify_brightness(confidence)

        # Normalize evidence_refs to string UUIDs
        raw_refs = event.get("evidence_refs") or []
        evidence_refs = [str(ref) for ref in raw_refs]

        # Format timestamp
        ts = event.get("timestamp_utc", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()

        frame = SingleCaseFrame(
            frame_index=i,
            activity_name=event.get("activity_name", ""),
            performer=event.get("performer_role_ref", "") or "",
            timestamp_utc=str(ts),
            confidence_score=confidence,
            brightness=brightness,
            evidence_refs=evidence_refs,
        )
        frames.append(frame)

    return frames


def generate_single_case_replay(
    case_id: str,
    events: list[dict[str, Any]],
) -> SingleCaseReplayResult:
    """Generate a single-case timeline replay from canonical events.

    Creates replay frames from the canonical event spine for the given
    case. Each frame corresponds to one CanonicalActivityEvent, ordered
    chronologically. Dark segments (confidence < 0.4) are flagged in
    the brightness field.

    Args:
        case_id: The case identifier to replay.
        events: Canonical activity events for this case, sorted by
            timestamp_utc ascending.

    Returns:
        SingleCaseReplayResult with all frames and metadata.
    """
    result = SingleCaseReplayResult(
        case_id=case_id,
    )

    if not events:
        result.status = "completed"
        result.total_frames = 0
        return result

    frames = build_frames_from_events(events)
    result.frames = frames
    result.total_frames = len(frames)
    result.status = "completed"

    dark_count = sum(1 for f in frames if f.brightness == "dark")
    if dark_count > 0:
        logger.info(
            "Single-case replay for %s: %d frames, %d dark segments",
            case_id,
            len(frames),
            dark_count,
        )

    return result


def get_paginated_frames(
    result: SingleCaseReplayResult,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Get a paginated slice of replay frames.

    Args:
        result: The full replay result.
        limit: Maximum frames per page.
        offset: Starting frame index.

    Returns:
        Dict with frames, pagination metadata, and task info.
    """
    total = result.total_frames
    page = result.frames[offset : offset + limit]

    return {
        "task_id": result.task_id,
        "frames": [f.to_dict() for f in page],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }
