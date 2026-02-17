"""Scenario definition and validation for simulations.

Validates scenario parameters based on simulation type and
process model structure.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.models import SimulationType

logger = logging.getLogger(__name__)


def validate_scenario(
    simulation_type: SimulationType,
    parameters: dict[str, Any],
    process_elements: list[str] | None = None,
) -> list[str]:
    """Validate scenario parameters.

    Args:
        simulation_type: Type of simulation.
        parameters: Scenario parameters to validate.
        process_elements: Available process element names.

    Returns:
        List of validation errors (empty if valid).
    """
    errors: list[str] = []
    process_elements = process_elements or []

    if simulation_type == SimulationType.WHAT_IF:
        changes = parameters.get("element_changes", {})
        if not changes:
            errors.append("what_if simulation requires 'element_changes'")
        for name in changes:
            if process_elements and name not in process_elements:
                errors.append(f"Element '{name}' not found in process model")

    elif simulation_type == SimulationType.CAPACITY:
        scale = parameters.get("capacity_scale")
        if scale is None:
            errors.append("capacity simulation requires 'capacity_scale'")
        elif not isinstance(scale, (int, float)) or scale <= 0:
            errors.append("capacity_scale must be a positive number")

    elif simulation_type == SimulationType.PROCESS_CHANGE:
        remove = parameters.get("remove_elements", [])
        add = parameters.get("add_elements", [])
        if not remove and not add:
            errors.append("process_change requires 'remove_elements' or 'add_elements'")

    elif simulation_type == SimulationType.CONTROL_REMOVAL:
        controls = parameters.get("remove_controls", [])
        if not controls:
            errors.append("control_removal requires 'remove_controls'")

    return errors
