"""Scenario simulation adapter (Story #380).

Integrates the simulation engine with scenario modifications to compute:
- Cycle time delta from task removals
- Staffing impact (FTE delta) from role reassignments
- Confidence overlay on modified elements (Bright/Dim/Dark classification)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.models.simulation import ModificationType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ElementImpact:
    """Impact assessment for a single modified element."""

    element_id: str
    element_name: str
    modification_type: str
    cycle_time_delta_hrs: float
    fte_delta: float
    confidence_classification: str  # BRIGHT, DIM, DARK

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_name": self.element_name,
            "modification_type": self.modification_type,
            "cycle_time_delta_hrs": round(self.cycle_time_delta_hrs, 2),
            "fte_delta": round(self.fte_delta, 2),
            "confidence_classification": self.confidence_classification,
        }


@dataclass(frozen=True)
class SimulationOutput:
    """Aggregate simulation output for a scenario."""

    cycle_time_delta_pct: float
    total_fte_delta: float
    per_element_results: list[ElementImpact]
    execution_time_ms: int
    baseline_cycle_time_hrs: float
    modified_cycle_time_hrs: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_time_delta_pct": round(self.cycle_time_delta_pct, 2),
            "total_fte_delta": round(self.total_fte_delta, 2),
            "per_element_results": [e.to_dict() for e in self.per_element_results],
            "execution_time_ms": self.execution_time_ms,
            "baseline_cycle_time_hrs": round(self.baseline_cycle_time_hrs, 2),
            "modified_cycle_time_hrs": round(self.modified_cycle_time_hrs, 2),
        }


@dataclass
class ScenarioSimulationAdapter:
    """Applies scenario modifications to compute operational impact.

    Attributes:
        baseline_cycle_time_hrs: Baseline process cycle time in hours.
        task_durations: Map of element_id -> estimated hours per task.
        fte_per_activity: FTE cost for human-to-system reassignment (configurable).
    """

    baseline_cycle_time_hrs: float = 100.0
    task_durations: dict[str, float] = field(default_factory=dict)
    fte_per_activity: float = 1.0

    def simulate(self, modifications: list[dict[str, Any]]) -> SimulationOutput:
        """Run simulation over a set of scenario modifications.

        Args:
            modifications: List of dicts with keys: modification_type,
                element_id, element_name, change_data (optional).

        Returns:
            SimulationOutput with cycle time and staffing impact.
        """
        start_ms = _now_ms()

        element_impacts: list[ElementImpact] = []
        total_cycle_delta = 0.0
        total_fte_delta = 0.0

        for mod in modifications:
            mod_type = mod["modification_type"]
            element_id = mod["element_id"]
            element_name = mod.get("element_name", element_id)
            change_data = mod.get("change_data") or {}

            cycle_delta = 0.0
            fte_delta = 0.0
            confidence = "DIM"  # default for modified elements

            if mod_type == ModificationType.TASK_REMOVE:
                # Removing a task reduces cycle time
                duration = self.task_durations.get(element_id, _default_task_duration(change_data))
                cycle_delta = -duration
                confidence = _confidence_for_removal(change_data)

            elif mod_type == ModificationType.TASK_ADD:
                # Adding a task increases cycle time
                duration = change_data.get("estimated_hours", 4.0)
                cycle_delta = duration
                confidence = "DARK"  # new task has no evidence

            elif mod_type == ModificationType.ROLE_REASSIGN:
                # Human-to-system reassignment = FTE reduction
                from_role = change_data.get("from_role", "")
                to_role = change_data.get("to_role", "")
                if _is_human_to_system(from_role, to_role):
                    fte_delta = -self.fte_per_activity
                elif _is_system_to_human(from_role, to_role):
                    fte_delta = self.fte_per_activity
                confidence = "DIM"  # reassignment reduces confidence

            elif mod_type == ModificationType.TASK_MODIFY:
                # Modification may affect cycle time
                time_change = change_data.get("cycle_time_delta_hrs", 0.0)
                cycle_delta = time_change
                confidence = "DIM"

            elif mod_type == ModificationType.GATEWAY_RESTRUCTURE:
                # Gateway changes affect routing, estimate cycle impact
                cycle_delta = change_data.get("cycle_time_delta_hrs", 0.0)
                confidence = "DARK"  # structural changes are uncertain

            elif mod_type in (ModificationType.CONTROL_ADD, ModificationType.CONTROL_REMOVE):
                # Controls affect compliance, minimal cycle impact
                cycle_delta = change_data.get("cycle_time_delta_hrs", 0.0)
                confidence = "DIM" if mod_type == ModificationType.CONTROL_ADD else "DARK"

            else:
                logger.warning("Unrecognized modification_type: %s for element %s", mod_type, element_id)

            total_cycle_delta += cycle_delta
            total_fte_delta += fte_delta

            element_impacts.append(ElementImpact(
                element_id=element_id,
                element_name=element_name,
                modification_type=mod_type,
                cycle_time_delta_hrs=cycle_delta,
                fte_delta=fte_delta,
                confidence_classification=confidence,
            ))

        modified_cycle = self.baseline_cycle_time_hrs + total_cycle_delta
        # Prevent negative cycle time
        modified_cycle = max(modified_cycle, 0.0)

        if self.baseline_cycle_time_hrs > 0:
            delta_pct = (
                (self.baseline_cycle_time_hrs - modified_cycle)
                / self.baseline_cycle_time_hrs
                * 100
            )
        else:
            delta_pct = 0.0

        elapsed = _now_ms() - start_ms

        return SimulationOutput(
            cycle_time_delta_pct=delta_pct,
            total_fte_delta=total_fte_delta,
            per_element_results=element_impacts,
            execution_time_ms=elapsed,
            baseline_cycle_time_hrs=self.baseline_cycle_time_hrs,
            modified_cycle_time_hrs=modified_cycle,
        )


def apply_confidence_overlay(
    per_element_results: list[ElementImpact],
    existing_confidence: dict[str, str],
) -> list[dict[str, Any]]:
    """Apply 3D confidence overlay to modified elements.

    For each modified element, compute the updated Bright/Dim/Dark
    classification reflecting the confidence impact of the modification.

    Args:
        per_element_results: Per-element simulation impacts.
        existing_confidence: Map of element_id -> current classification
            (BRIGHT/DIM/DARK) from the base POV model.

    Returns:
        List of dicts with element_id, original and modified classifications.
    """
    overlays: list[dict[str, Any]] = []
    for impact in per_element_results:
        original = existing_confidence.get(impact.element_id, "DIM")
        modified = impact.confidence_classification

        # Removing a well-evidenced (BRIGHT) element reduces scenario confidence
        if impact.modification_type == ModificationType.TASK_REMOVE and original == "BRIGHT":
            modified = "DARK"

        overlays.append({
            "element_id": impact.element_id,
            "element_name": impact.element_name,
            "original_classification": original,
            "modified_classification": modified,
            "confidence_changed": original != modified,
        })

    return overlays


# -- Helpers -------------------------------------------------------------------


def _default_task_duration(change_data: dict[str, Any]) -> float:
    """Estimate task duration from change_data or use default."""
    return float(change_data.get("estimated_hours", 4.0))


def _confidence_for_removal(change_data: dict[str, Any]) -> str:
    """Determine confidence classification when removing a task."""
    # If the task had high confidence, removing it is risky
    original_confidence = change_data.get("original_confidence", "DIM")
    if original_confidence == "BRIGHT":
        return "DARK"  # losing well-evidenced work
    return "DIM"


def _is_human_to_system(from_role: str, to_role: str) -> bool:
    """Check if reassignment is from human to automated system."""
    system_indicators = {"system", "automated", "bot", "rpa", "api"}
    to_lower = to_role.lower()
    from_lower = from_role.lower()
    return (
        any(ind in to_lower for ind in system_indicators)
        and not any(ind in from_lower for ind in system_indicators)
    )


def _is_system_to_human(from_role: str, to_role: str) -> bool:
    """Check if reassignment is from system to human."""
    return _is_human_to_system(to_role, from_role)


def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.monotonic() * 1000)
