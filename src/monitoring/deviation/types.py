"""Deviation type definitions for the process deviation detection engine.

Extends the base DeviationCategory with severity classification and
structured deviation records that carry telemetry references, importance
scores, and severity classifications.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


class DeviationType(enum.StrEnum):
    """Specific deviation types detected by the engine."""

    SKIPPED_ACTIVITY = "skipped_activity"
    TIMING_ANOMALY = "timing_anomaly"
    UNDOCUMENTED_ACTIVITY = "undocumented_activity"
    ROLE_REASSIGNMENT = "role_reassignment"
    MISSING_EXPECTED_ACTIVITY = "missing_expected_activity"
    SEQUENCE_CHANGE = "sequence_change"


class DeviationSeverity(enum.StrEnum):
    """Severity classification for deviations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# Severity thresholds based on computed severity score
SEVERITY_THRESHOLDS: list[tuple[DeviationSeverity, float]] = [
    (DeviationSeverity.CRITICAL, 0.90),
    (DeviationSeverity.HIGH, 0.70),
    (DeviationSeverity.MEDIUM, 0.40),
    (DeviationSeverity.LOW, 0.20),
    (DeviationSeverity.INFO, 0.0),
]

# Default magnitude coefficients per deviation type
DEFAULT_MAGNITUDE_COEFFICIENTS: dict[str, float] = {
    DeviationType.SKIPPED_ACTIVITY: 1.0,
    DeviationType.TIMING_ANOMALY: 0.8,
    DeviationType.UNDOCUMENTED_ACTIVITY: 0.7,
    DeviationType.ROLE_REASSIGNMENT: 0.6,
    DeviationType.MISSING_EXPECTED_ACTIVITY: 0.9,
    DeviationType.SEQUENCE_CHANGE: 0.7,
}


@dataclass
class DeviationRecord:
    """A detected process deviation with full context.

    Attributes:
        id: Unique deviation identifier.
        deviation_type: The type of deviation detected.
        severity: Computed severity classification.
        severity_score: Raw severity score (0-1).
        process_element_id: ID of the affected process element in the POV.
        affected_element: Name of the affected process element.
        engagement_id: Engagement context.
        telemetry_ref: Reference to the telemetry event that triggered detection.
        description: Human-readable description of the deviation.
        details: Additional structured details specific to the deviation type.
        detected_at: When the deviation was detected.
    """

    id: str = ""
    deviation_type: DeviationType = DeviationType.SKIPPED_ACTIVITY
    severity: DeviationSeverity = DeviationSeverity.INFO
    severity_score: float = 0.0
    process_element_id: str | None = None
    affected_element: str = ""
    engagement_id: str = ""
    telemetry_ref: str | None = None
    description: str = ""
    details: dict = field(default_factory=dict)
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())


def classify_severity(score: float) -> DeviationSeverity:
    """Classify a severity score into a named severity level.

    Args:
        score: Severity score between 0 and 1.

    Returns:
        The severity classification.
    """
    for severity, threshold in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return severity
    return DeviationSeverity.INFO
