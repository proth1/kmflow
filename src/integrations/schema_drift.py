"""Schema drift detection and alerting pipeline.

Compares incoming data schemas against expected connector schemas to
detect field additions, removals, type changes, and naming shifts.
Generates alerts when drift exceeds configurable thresholds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class DriftSeverity(StrEnum):
    """Severity level for schema drift events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class SchemaDriftEvent:
    """A detected schema drift between expected and observed schemas."""

    connector_type: str
    engagement_id: str
    drift_type: str  # "field_added", "field_removed", "type_changed"
    field_name: str
    expected: str | None = None
    observed: str | None = None
    severity: DriftSeverity = DriftSeverity.WARNING
    detected_at: str = ""

    def __post_init__(self) -> None:
        if not self.detected_at:
            self.detected_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_type": self.connector_type,
            "engagement_id": self.engagement_id,
            "drift_type": self.drift_type,
            "field_name": self.field_name,
            "expected": self.expected,
            "observed": self.observed,
            "severity": self.severity.value,
            "detected_at": self.detected_at,
        }


@dataclass
class SchemaDriftReport:
    """Summary of schema drift analysis for a connector sync."""

    connector_type: str
    engagement_id: str
    events: list[SchemaDriftEvent] = field(default_factory=list)
    analyzed_at: str = ""
    is_compatible: bool = True

    def __post_init__(self) -> None:
        if not self.analyzed_at:
            self.analyzed_at = datetime.now(UTC).isoformat()

    @property
    def has_breaking_changes(self) -> bool:
        return any(e.severity == DriftSeverity.ERROR for e in self.events)

    @property
    def drift_count(self) -> int:
        return len(self.events)


class SchemaDriftDetector:
    """Detects schema drift between expected and observed data schemas.

    Compares field sets and types to identify additions, removals,
    and type changes. Generates severity-ranked drift events.
    """

    def __init__(
        self,
        *,
        removed_field_severity: DriftSeverity = DriftSeverity.ERROR,
        added_field_severity: DriftSeverity = DriftSeverity.INFO,
        type_change_severity: DriftSeverity = DriftSeverity.WARNING,
    ) -> None:
        self._removed_severity = removed_field_severity
        self._added_severity = added_field_severity
        self._type_change_severity = type_change_severity

    def detect(
        self,
        connector_type: str,
        engagement_id: str,
        expected_fields: dict[str, str],
        observed_fields: dict[str, str],
    ) -> SchemaDriftReport:
        """Compare expected vs observed schemas and generate drift report.

        Args:
            connector_type: Connector identifier.
            engagement_id: Engagement being synced.
            expected_fields: Expected schema as {field_name: field_type}.
            observed_fields: Observed schema from incoming data.

        Returns:
            SchemaDriftReport with any detected drift events.
        """
        report = SchemaDriftReport(
            connector_type=connector_type,
            engagement_id=engagement_id,
        )

        expected_keys = set(expected_fields.keys())
        observed_keys = set(observed_fields.keys())

        # Detect removed fields (in expected but not observed)
        for field_name in sorted(expected_keys - observed_keys):
            report.events.append(
                SchemaDriftEvent(
                    connector_type=connector_type,
                    engagement_id=engagement_id,
                    drift_type="field_removed",
                    field_name=field_name,
                    expected=expected_fields[field_name],
                    severity=self._removed_severity,
                )
            )

        # Detect added fields (in observed but not expected)
        for field_name in sorted(observed_keys - expected_keys):
            report.events.append(
                SchemaDriftEvent(
                    connector_type=connector_type,
                    engagement_id=engagement_id,
                    drift_type="field_added",
                    field_name=field_name,
                    observed=observed_fields[field_name],
                    severity=self._added_severity,
                )
            )

        # Detect type changes (same field, different type)
        for field_name in sorted(expected_keys & observed_keys):
            if expected_fields[field_name] != observed_fields[field_name]:
                report.events.append(
                    SchemaDriftEvent(
                        connector_type=connector_type,
                        engagement_id=engagement_id,
                        drift_type="type_changed",
                        field_name=field_name,
                        expected=expected_fields[field_name],
                        observed=observed_fields[field_name],
                        severity=self._type_change_severity,
                    )
                )

        report.is_compatible = not report.has_breaking_changes

        if report.events:
            logger.info(
                "Schema drift detected for %s/%s: %d events (%s)",
                connector_type,
                engagement_id,
                report.drift_count,
                "BREAKING" if report.has_breaking_changes else "compatible",
            )

        return report

    def infer_schema(self, records: list[dict[str, Any]]) -> dict[str, str]:
        """Infer schema from a list of data records.

        Examines the first N records to determine field names and types.

        Args:
            records: Sample data records.

        Returns:
            Dict mapping field names to inferred type strings.
        """
        if not records:
            return {}

        schema: dict[str, str] = {}
        sample = records[:min(100, len(records))]

        for record in sample:
            for key, value in record.items():
                inferred = type(value).__name__ if value is not None else "null"
                if key not in schema:
                    schema[key] = inferred
                elif schema[key] != inferred and inferred != "null":
                    # Type conflict across records
                    schema[key] = f"mixed({schema[key]},{inferred})"

        return schema
