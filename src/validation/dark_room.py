"""Dark-Room Shrink Rate computation and illumination timeline (Story #370).

Computes per-version dark segment reduction percentages and generates
alerts when the shrink rate falls below the configurable target threshold.
Also provides illumination timeline showing when specific segments moved
from dark to dim/bright across POV versions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default shrink rate target: >15% reduction per version
DEFAULT_SHRINK_RATE_TARGET = 15.0


@dataclass
class VersionShrinkData:
    """Per-version dark segment count and reduction percentage."""

    version_number: int
    pov_version_id: str
    dark_count: int
    dim_count: int
    bright_count: int
    total_elements: int
    reduction_pct: float | None = None  # None for first version
    snapshot_at: str = ""


@dataclass
class ShrinkRateAlert:
    """Alert when shrink rate falls below target."""

    severity: str  # "warning" or "info"
    message: str
    version_number: int
    actual_rate: float
    target_rate: float
    dark_segments: list[str] = field(default_factory=list)


@dataclass
class IlluminationEvent:
    """Records when a segment was illuminated (dark → dim/bright)."""

    element_name: str
    element_id: str
    from_classification: str  # "dark"
    to_classification: str  # "dim" or "bright"
    illuminated_in_version: int
    pov_version_id: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class DarkRoomDashboardData:
    """Complete dark room dashboard response."""

    engagement_id: str
    shrink_rate_target: float
    versions: list[VersionShrinkData]
    alerts: list[ShrinkRateAlert]
    illumination_timeline: list[IlluminationEvent]


def compute_shrink_rates(
    snapshots: list[dict[str, Any]],
) -> list[VersionShrinkData]:
    """Compute per-version shrink rates from ordered snapshots.

    Args:
        snapshots: List of snapshot dicts ordered by version_number ascending.
            Each dict must have: version_number, pov_version_id, dark_count,
            dim_count, bright_count, total_elements, snapshot_at.

    Returns:
        List of VersionShrinkData with computed reduction_pct.
    """
    results: list[VersionShrinkData] = []

    for i, snap in enumerate(snapshots):
        version_data = VersionShrinkData(
            version_number=snap["version_number"],
            pov_version_id=str(snap["pov_version_id"]),
            dark_count=snap["dark_count"],
            dim_count=snap["dim_count"],
            bright_count=snap["bright_count"],
            total_elements=snap["total_elements"],
            snapshot_at=str(snap.get("snapshot_at", "")),
        )

        if i > 0 and snapshots[i - 1]["dark_count"] > 0:
            prev_dark = snapshots[i - 1]["dark_count"]
            curr_dark = snap["dark_count"]
            version_data.reduction_pct = ((prev_dark - curr_dark) / prev_dark) * 100
        elif i > 0:
            # Previous version had 0 dark segments — no reduction possible
            version_data.reduction_pct = 0.0

        results.append(version_data)

    return results


def generate_alerts(
    versions: list[VersionShrinkData],
    target_rate: float = DEFAULT_SHRINK_RATE_TARGET,
    dark_segment_names: list[str] | None = None,
) -> list[ShrinkRateAlert]:
    """Generate alerts for versions where shrink rate is below target.

    Args:
        versions: Per-version shrink data (with reduction_pct computed).
        target_rate: Minimum acceptable shrink rate (default 15%).
        dark_segment_names: Names of dark segments to include in alert.

    Returns:
        List of ShrinkRateAlert for versions below target.
    """
    alerts: list[ShrinkRateAlert] = []

    for v in versions:
        if v.reduction_pct is None:
            continue
        if v.reduction_pct < target_rate:
            alerts.append(
                ShrinkRateAlert(
                    severity="warning",
                    message=(
                        f"Dark segment shrink rate ({v.reduction_pct:.1f}%) is below "
                        f"the {target_rate:.0f}% target for version {v.version_number}. "
                        "Recommend targeted evidence acquisition to illuminate remaining Dark areas."
                    ),
                    version_number=v.version_number,
                    actual_rate=v.reduction_pct,
                    target_rate=target_rate,
                    dark_segments=dark_segment_names or [],
                )
            )

    return alerts


def compute_illumination_timeline(
    version_elements: list[dict[str, Any]],
) -> list[IlluminationEvent]:
    """Compute when each element was illuminated across versions.

    Args:
        version_elements: List of dicts with:
            - element_name, element_id, brightness_classification,
              version_number, pov_version_id, evidence_ids

            Ordered by (element_name, version_number) ascending.

    Returns:
        List of IlluminationEvent for elements that moved from dark to dim/bright.
    """
    events: list[IlluminationEvent] = []

    # Group by element_name
    element_history: dict[str, list[dict[str, Any]]] = {}
    for el in version_elements:
        name = el["element_name"]
        if name not in element_history:
            element_history[name] = []
        element_history[name].append(el)

    for _name, history in element_history.items():
        # Sort by version_number
        history.sort(key=lambda x: x["version_number"])

        for i in range(1, len(history)):
            prev = history[i - 1]
            curr = history[i]

            if prev["brightness_classification"] == "dark" and curr[
                "brightness_classification"
            ] in ("dim", "bright"):
                events.append(
                    IlluminationEvent(
                        element_name=curr["element_name"],
                        element_id=str(curr["element_id"]),
                        from_classification="dark",
                        to_classification=curr["brightness_classification"],
                        illuminated_in_version=curr["version_number"],
                        pov_version_id=str(curr["pov_version_id"]),
                        evidence_ids=[
                            str(eid)
                            for eid in (curr.get("evidence_ids") or [])
                        ],
                    )
                )

    return events
