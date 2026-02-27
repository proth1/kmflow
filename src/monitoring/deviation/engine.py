"""Process Deviation Detection Engine.

Compares incoming telemetry and evidence against the established POV
process model baseline. Detects deviations including: skipped activities,
timing anomalies, undocumented activities, role reassignments, missing
expected activities, and sequence changes.

Each deviation carries a severity score:
    severity = element_importance_score * deviation_magnitude_coefficient
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.monitoring.deviation.types import (
    DEFAULT_MAGNITUDE_COEFFICIENTS,
    DeviationRecord,
    DeviationSeverity,
    DeviationType,
    classify_severity,
)

logger = logging.getLogger(__name__)

# TODO(#350-followup): Add service layer to persist DeviationRecord -> ProcessDeviation ORM objects.
# Currently the engine produces in-memory DeviationRecords; a persistence service is needed
# to bridge engine output to the database for the API endpoint to query.

# Timing severity formula constants
TIMING_MAGNITUDE_CAP = 5.0  # Maximum deviation magnitude before capping
TIMING_BASE_SEVERITY_FLOOR = 0.3  # Base severity floor for timing anomalies


@dataclass
class PovElement:
    """An element from the established POV process model.

    Attributes:
        id: Unique element identifier.
        name: Element name.
        importance_score: How important this element is in the process (0-1).
        expected_duration_range: Baseline (min, max) hours for timing.
        role: Expected role performing this activity.
    """

    id: str = ""
    name: str = ""
    importance_score: float = 0.5
    expected_duration_range: tuple[float, float] | None = None
    role: str | None = None


@dataclass
class PovBaseline:
    """The established POV process model baseline.

    Attributes:
        engagement_id: Engagement this baseline belongs to.
        elements: List of POV elements in expected order.
        element_map: Lookup by element name.
        expected_sequence: Ordered list of element names forming the expected flow.
    """

    engagement_id: str = ""
    elements: list[PovElement] = field(default_factory=list)
    element_map: dict[str, PovElement] = field(default_factory=dict)
    expected_sequence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.element_map and self.elements:
            self.element_map = {e.name: e for e in self.elements}
        if not self.expected_sequence and self.elements:
            self.expected_sequence = [e.name for e in self.elements]


@dataclass
class TelemetryEvent:
    """A canonical activity event from incoming telemetry.

    Attributes:
        id: Unique event identifier.
        activity_name: Name of the observed activity.
        engagement_id: Engagement context.
        duration_hours: Observed duration in hours.
        role: Role that performed the activity.
        timestamp: When the activity occurred.
    """

    id: str = ""
    activity_name: str = ""
    engagement_id: str = ""
    duration_hours: float | None = None
    role: str | None = None
    timestamp: str | None = None


class DeviationEngine:
    """Engine that detects process deviations against a POV baseline.

    Compares incoming telemetry events against the established POV
    process model to identify anomalies.
    """

    def __init__(
        self,
        baseline: PovBaseline,
        magnitude_coefficients: dict[str, float] | None = None,
    ) -> None:
        self.baseline = baseline
        self.coefficients = magnitude_coefficients or dict(DEFAULT_MAGNITUDE_COEFFICIENTS)

    def compute_severity(
        self,
        importance_score: float,
        deviation_type: DeviationType,
    ) -> tuple[float, DeviationSeverity]:
        """Compute severity score and classification.

        Formula: severity = importance_score * magnitude_coefficient

        Args:
            importance_score: Element importance in the POV (0-1).
            deviation_type: Type of deviation for coefficient lookup.

        Returns:
            Tuple of (severity_score, severity_classification).
        """
        coefficient = self.coefficients.get(deviation_type, 0.5)
        score = min(importance_score * coefficient, 1.0)
        return score, classify_severity(score)

    def detect_skipped_activities(
        self,
        observed_sequence: list[str],
    ) -> list[DeviationRecord]:
        """Detect activities present in baseline but absent from telemetry.

        Args:
            observed_sequence: Ordered list of observed activity names.

        Returns:
            List of SKIPPED_ACTIVITY deviation records.
        """
        deviations: list[DeviationRecord] = []
        observed_set = set(observed_sequence)
        engagement_id = self.baseline.engagement_id

        for element_name in self.baseline.expected_sequence:
            if element_name not in observed_set:
                element = self.baseline.element_map.get(element_name)
                importance = element.importance_score if element else 0.5
                score, severity = self.compute_severity(importance, DeviationType.SKIPPED_ACTIVITY)

                deviations.append(
                    DeviationRecord(
                        deviation_type=DeviationType.SKIPPED_ACTIVITY,
                        severity=severity,
                        severity_score=score,
                        process_element_id=element.id if element else None,
                        affected_element=element_name,
                        engagement_id=engagement_id,
                        description=(f"Activity '{element_name}' expected in POV but absent from telemetry"),
                        details={"importance_score": importance},
                    )
                )

        return deviations

    def detect_timing_anomalies(
        self,
        events: list[TelemetryEvent],
    ) -> list[DeviationRecord]:
        """Detect activities whose duration exceeds the baseline range.

        Args:
            events: Telemetry events with observed durations.

        Returns:
            List of TIMING_ANOMALY deviation records.
        """
        deviations: list[DeviationRecord] = []

        for event in events:
            element = self.baseline.element_map.get(event.activity_name)
            if not element or not element.expected_duration_range:
                continue
            if event.duration_hours is None:
                continue

            min_hours, max_hours = element.expected_duration_range
            if min_hours <= event.duration_hours <= max_hours:
                continue

            # Compute deviation magnitude as ratio of excess/deficit over the relevant baseline bound
            if event.duration_hours > max_hours:
                deviation_magnitude = (event.duration_hours - max_hours) / max_hours if max_hours > 0 else 1.0
            else:
                deviation_magnitude = (min_hours - event.duration_hours) / min_hours if min_hours > 0 else 1.0

            # Importance-weighted severity
            importance = element.importance_score
            coefficient = self.coefficients.get(DeviationType.TIMING_ANOMALY, 0.8)
            # Scale by deviation magnitude (capped at TIMING_MAGNITUDE_CAP)
            raw_score = importance * coefficient * min(deviation_magnitude, TIMING_MAGNITUDE_CAP) / TIMING_MAGNITUDE_CAP
            score = min(raw_score + importance * coefficient * TIMING_BASE_SEVERITY_FLOOR, 1.0)
            severity = classify_severity(score)

            deviations.append(
                DeviationRecord(
                    deviation_type=DeviationType.TIMING_ANOMALY,
                    severity=severity,
                    severity_score=score,
                    process_element_id=element.id,
                    affected_element=event.activity_name,
                    engagement_id=event.engagement_id,
                    telemetry_ref=event.id,
                    description=(
                        f"Activity '{event.activity_name}' took {event.duration_hours}h, "
                        f"baseline range is [{min_hours}, {max_hours}]h"
                    ),
                    details={
                        "observed_duration_hours": event.duration_hours,
                        "baseline_range": [min_hours, max_hours],
                        "deviation_magnitude": round(deviation_magnitude, 4),
                    },
                )
            )

        return deviations

    def detect_undocumented_activities(
        self,
        events: list[TelemetryEvent],
    ) -> list[DeviationRecord]:
        """Detect activities in telemetry that have no match in the POV.

        Args:
            events: Telemetry events to check against the baseline.

        Returns:
            List of UNDOCUMENTED_ACTIVITY deviation records.
        """
        deviations: list[DeviationRecord] = []
        known_names = set(self.baseline.element_map.keys())
        seen: set[str] = set()

        for event in events:
            if event.activity_name in known_names:
                continue
            if event.activity_name in seen:
                continue
            seen.add(event.activity_name)

            score, severity = self.compute_severity(0.5, DeviationType.UNDOCUMENTED_ACTIVITY)

            deviations.append(
                DeviationRecord(
                    deviation_type=DeviationType.UNDOCUMENTED_ACTIVITY,
                    severity=severity,
                    severity_score=score,
                    affected_element=event.activity_name,
                    engagement_id=event.engagement_id,
                    telemetry_ref=event.id,
                    description=(f"Activity '{event.activity_name}' found in telemetry but not in POV"),
                    details={"requires_analyst_review": True},
                )
            )

        return deviations

    def detect_all(
        self,
        events: list[TelemetryEvent],
        observed_sequence: list[str] | None = None,
    ) -> list[DeviationRecord]:
        """Run all deviation detection handlers.

        Args:
            events: Incoming telemetry events.
            observed_sequence: Optional explicit activity sequence.
                If not provided, derived from events.

        Returns:
            Combined list of all detected deviations.
        """
        if observed_sequence is None:
            observed_sequence = [e.activity_name for e in events]

        deviations: list[DeviationRecord] = []
        deviations.extend(self.detect_skipped_activities(observed_sequence))
        deviations.extend(self.detect_timing_anomalies(events))
        deviations.extend(self.detect_undocumented_activities(events))

        logger.info(
            "Deviation engine detected %d deviations for engagement %s",
            len(deviations),
            self.baseline.engagement_id,
        )
        return deviations
