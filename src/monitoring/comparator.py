"""Baseline-to-current comparison utilities.

Provides specific comparison functions for different deviation categories:
sequence changes, timing anomalies, role changes, frequency shifts,
and control bypasses.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.models import DeviationCategory

logger = logging.getLogger(__name__)


def detect_sequence_changes(
    baseline_connections: list[tuple[str, str] | list[str]],
    current_connections: list[tuple[str, str] | list[str]],
) -> list[dict[str, Any]]:
    """Detect changes in process flow sequences."""
    baseline_set = {(c[0], c[1]) for c in baseline_connections if len(c) >= 2}
    current_set = {(c[0], c[1]) for c in current_connections if len(c) >= 2}

    deviations: list[dict[str, Any]] = []

    for removed in baseline_set - current_set:
        deviations.append({
            "category": DeviationCategory.SEQUENCE_CHANGE,
            "description": f"Sequence flow removed: {removed[0]} -> {removed[1]}",
            "affected_element": f"{removed[0]}->{removed[1]}",
            "magnitude": 0.7,
            "details": {"change_type": "removed", "source": removed[0], "target": removed[1]},
        })

    for added in current_set - baseline_set:
        deviations.append({
            "category": DeviationCategory.SEQUENCE_CHANGE,
            "description": f"New sequence flow: {added[0]} -> {added[1]}",
            "affected_element": f"{added[0]}->{added[1]}",
            "magnitude": 0.5,
            "details": {"change_type": "added", "source": added[0], "target": added[1]},
        })

    return deviations


def detect_timing_anomalies(
    baseline_timing: dict[str, dict[str, float]],
    current_timing: dict[str, dict[str, float]],
    threshold: float = 2.0,
) -> list[dict[str, Any]]:
    """Detect timing anomalies using z-score comparison.

    Args:
        baseline_timing: Baseline timing stats per activity {name: {mean, stddev}}.
        current_timing: Current observed timing {name: {mean, stddev}}.
        threshold: Z-score threshold for anomaly detection.
    """
    deviations: list[dict[str, Any]] = []

    for activity, baseline_stats in baseline_timing.items():
        if activity not in current_timing:
            continue

        b_mean = baseline_stats.get("mean", 0)
        b_std = baseline_stats.get("stddev", 1)
        c_mean = current_timing[activity].get("mean", 0)

        if b_std == 0:
            b_std = 1

        z_score = abs(c_mean - b_mean) / b_std
        if z_score >= threshold:
            magnitude = min(z_score / 5.0, 1.0)
            deviations.append({
                "category": DeviationCategory.TIMING_ANOMALY,
                "description": (
                    f"Timing anomaly for '{activity}': "
                    f"baseline mean={b_mean:.1f}, current mean={c_mean:.1f}, z={z_score:.2f}"
                ),
                "affected_element": activity,
                "magnitude": magnitude,
                "details": {
                    "baseline_mean": b_mean,
                    "baseline_stddev": b_std,
                    "current_mean": c_mean,
                    "z_score": round(z_score, 2),
                },
            })

    return deviations


def detect_role_changes(
    baseline_roles: dict[str, str],
    current_roles: dict[str, str],
) -> list[dict[str, Any]]:
    """Detect changes in activity-to-role assignments."""
    deviations: list[dict[str, Any]] = []

    for activity, baseline_role in baseline_roles.items():
        current_role = current_roles.get(activity)
        if current_role and current_role != baseline_role:
            deviations.append({
                "category": DeviationCategory.ROLE_CHANGE,
                "description": (
                    f"Role change for '{activity}': "
                    f"was '{baseline_role}', now '{current_role}'"
                ),
                "affected_element": activity,
                "magnitude": 0.6,
                "details": {
                    "baseline_role": baseline_role,
                    "current_role": current_role,
                },
            })

    return deviations


def detect_frequency_changes(
    baseline_freq: dict[str, float],
    current_freq: dict[str, float],
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Detect significant changes in activity execution frequency.

    Args:
        baseline_freq: Baseline frequency per activity.
        current_freq: Current frequency per activity.
        threshold: Relative change threshold (0.5 = 50%).
    """
    deviations: list[dict[str, Any]] = []

    for activity, b_freq in baseline_freq.items():
        c_freq = current_freq.get(activity, 0)
        if b_freq == 0:
            continue

        relative_change = abs(c_freq - b_freq) / b_freq
        if relative_change >= threshold:
            magnitude = min(relative_change, 1.0)
            deviations.append({
                "category": DeviationCategory.FREQUENCY_CHANGE,
                "description": (
                    f"Frequency change for '{activity}': "
                    f"baseline={b_freq:.1f}, current={c_freq:.1f} "
                    f"({relative_change:.0%} change)"
                ),
                "affected_element": activity,
                "magnitude": magnitude,
                "details": {
                    "baseline_frequency": b_freq,
                    "current_frequency": c_freq,
                    "relative_change": round(relative_change, 3),
                },
            })

    return deviations


def detect_control_bypass(
    required_controls: list[str],
    executed_controls: list[str],
) -> list[dict[str, Any]]:
    """Detect controls that should have been executed but weren't."""
    deviations: list[dict[str, Any]] = []
    executed_set = set(executed_controls)

    for control in required_controls:
        if control not in executed_set:
            deviations.append({
                "category": DeviationCategory.CONTROL_BYPASS,
                "description": f"Control '{control}' was not executed",
                "affected_element": control,
                "magnitude": 0.9,
                "details": {"control_name": control, "bypass_type": "not_executed"},
            })

    return deviations
