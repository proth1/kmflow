"""Alert generation, deduplication, and severity classification.

Converts detected deviations into actionable alerts with severity
classification and deduplication logic.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from src.core.models import AlertSeverity, DeviationCategory

logger = logging.getLogger(__name__)

# Severity mapping based on deviation category and magnitude
CATEGORY_SEVERITY: dict[DeviationCategory, AlertSeverity] = {
    DeviationCategory.CONTROL_BYPASS: AlertSeverity.CRITICAL,
    DeviationCategory.MISSING_ACTIVITY: AlertSeverity.HIGH,
    DeviationCategory.SEQUENCE_CHANGE: AlertSeverity.MEDIUM,
    DeviationCategory.NEW_ACTIVITY: AlertSeverity.LOW,
    DeviationCategory.TIMING_ANOMALY: AlertSeverity.MEDIUM,
    DeviationCategory.ROLE_CHANGE: AlertSeverity.MEDIUM,
    DeviationCategory.FREQUENCY_CHANGE: AlertSeverity.LOW,
}


def classify_severity(
    category: DeviationCategory | str,
    magnitude: float,
) -> AlertSeverity:
    """Classify alert severity based on deviation category and magnitude.

    Args:
        category: Deviation category.
        magnitude: Deviation magnitude (0.0 - 1.0).

    Returns:
        Classified alert severity.
    """
    if isinstance(category, str):
        try:
            category = DeviationCategory(category)
        except ValueError:
            return AlertSeverity.INFO

    base_severity = CATEGORY_SEVERITY.get(category, AlertSeverity.INFO)

    # Upgrade severity for high magnitude
    if magnitude >= 0.9:
        if base_severity == AlertSeverity.LOW:
            return AlertSeverity.MEDIUM
        if base_severity == AlertSeverity.MEDIUM:
            return AlertSeverity.HIGH
        if base_severity == AlertSeverity.HIGH:
            return AlertSeverity.CRITICAL
    elif magnitude <= 0.2:
        if base_severity == AlertSeverity.HIGH:
            return AlertSeverity.MEDIUM
        if base_severity == AlertSeverity.MEDIUM:
            return AlertSeverity.LOW

    return base_severity


def generate_dedup_key(
    engagement_id: str,
    category: str,
    affected_element: str | None,
) -> str:
    """Generate a deduplication key for an alert.

    Alerts with the same dedup key within a window are considered duplicates.
    """
    parts = f"{engagement_id}:{category}:{affected_element or 'global'}"
    return hashlib.md5(parts.encode(), usedforsecurity=False).hexdigest()[:16]


def create_alert_from_deviations(
    engagement_id: str,
    monitoring_job_id: str,
    deviations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create alerts from a list of detected deviations.

    Groups related deviations and generates deduplicated alerts.

    Args:
        engagement_id: The engagement ID.
        monitoring_job_id: The monitoring job that detected the deviations.
        deviations: List of deviation dicts.

    Returns:
        List of alert dicts ready for persistence.
    """
    alerts: list[dict[str, Any]] = []
    seen_dedup_keys: set[str] = set()

    for dev in deviations:
        category = dev.get("category", "")
        cat_str = category.value if hasattr(category, "value") else str(category)
        magnitude = dev.get("magnitude", 0.0)
        affected = dev.get("affected_element")

        dedup_key = generate_dedup_key(engagement_id, cat_str, affected)
        if dedup_key in seen_dedup_keys:
            # Add deviation ID to existing alert
            for alert in alerts:
                if alert["dedup_key"] == dedup_key:
                    alert["deviation_ids"].append(dev.get("id", ""))
                    break
            continue

        seen_dedup_keys.add(dedup_key)
        severity = classify_severity(category, magnitude)

        title = f"{cat_str.replace('_', ' ').title()}"
        if affected:
            title += f": {affected}"

        alerts.append(
            {
                "engagement_id": engagement_id,
                "monitoring_job_id": monitoring_job_id,
                "severity": severity,
                "title": title,
                "description": dev.get("description", ""),
                "deviation_ids": [dev.get("id", "")],
                "dedup_key": dedup_key,
            }
        )

    return alerts
