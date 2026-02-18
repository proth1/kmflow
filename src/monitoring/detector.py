"""Deviation detection engine.

Analyzes process data against baselines to identify deviations
in sequence, timing, activities, roles, and controls.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.models import DeviationCategory
from src.monitoring.comparator import (
    detect_control_bypass,
    detect_frequency_changes,
    detect_role_changes,
    detect_sequence_changes,
    detect_timing_anomalies,
)

logger = logging.getLogger(__name__)


def detect_deviations(
    baseline_snapshot: dict[str, Any],
    current_data: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Run all deviation detection checks against a baseline.

    Args:
        baseline_snapshot: The reference baseline snapshot.
        current_data: Current process observation data.
        thresholds: Optional magnitude thresholds per category.

    Returns:
        List of detected deviations.
    """
    thresholds = thresholds or {}
    deviations: list[dict[str, Any]] = []

    # Structural deviations
    baseline_elements = set(baseline_snapshot.get("element_names", []))
    current_elements = set(current_data.get("element_names", []))

    for missing in baseline_elements - current_elements:
        deviations.append(
            {
                "category": DeviationCategory.MISSING_ACTIVITY,
                "description": f"Activity '{missing}' from baseline not found in current data",
                "affected_element": missing,
                "magnitude": 0.8,
            }
        )

    for new_elem in current_elements - baseline_elements:
        deviations.append(
            {
                "category": DeviationCategory.NEW_ACTIVITY,
                "description": f"New activity '{new_elem}' not in baseline",
                "affected_element": new_elem,
                "magnitude": 0.6,
            }
        )

    # Sequence deviations
    seq_devs = detect_sequence_changes(
        baseline_snapshot.get("connection_pairs", []),
        current_data.get("connection_pairs", []),
    )
    deviations.extend(seq_devs)

    # Timing anomalies
    timing_devs = detect_timing_anomalies(
        baseline_snapshot.get("timing_stats", {}),
        current_data.get("timing_stats", {}),
        threshold=thresholds.get("timing", 2.0),
    )
    deviations.extend(timing_devs)

    # Role changes
    role_devs = detect_role_changes(
        baseline_snapshot.get("role_assignments", {}),
        current_data.get("role_assignments", {}),
    )
    deviations.extend(role_devs)

    # Frequency changes
    freq_devs = detect_frequency_changes(
        baseline_snapshot.get("activity_frequencies", {}),
        current_data.get("activity_frequencies", {}),
        threshold=thresholds.get("frequency", 0.5),
    )
    deviations.extend(freq_devs)

    # Control bypass
    ctrl_devs = detect_control_bypass(
        baseline_snapshot.get("control_points", []),
        current_data.get("executed_controls", []),
    )
    deviations.extend(ctrl_devs)

    # Apply magnitude threshold filtering
    min_magnitude = thresholds.get("min_magnitude", 0.0)
    return [d for d in deviations if d.get("magnitude", 0) >= min_magnitude]
