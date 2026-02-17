"""Graph-based process simulation execution engine.

Runs simulations by traversing process model graphs, applying
parameter modifications, and computing impact metrics.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def run_simulation(
    process_graph: dict[str, Any],
    parameters: dict[str, Any],
    simulation_type: str,
) -> dict[str, Any]:
    """Execute a process simulation.

    Args:
        process_graph: The process model graph structure.
        parameters: Simulation parameters/modifications.
        simulation_type: Type of simulation (what_if, capacity, etc.).

    Returns:
        Simulation results with metrics and impact analysis.
    """
    start = time.monotonic()

    elements = process_graph.get("elements", [])
    connections = process_graph.get("connections", [])

    # Build adjacency list
    adjacency: dict[str, list[str]] = {}
    for conn in connections:
        source = conn.get("source", "")
        target = conn.get("target", "")
        if source not in adjacency:
            adjacency[source] = []
        adjacency[source].append(target)

    # Apply parameter modifications
    modified_elements = _apply_parameters(elements, parameters, simulation_type)

    # Calculate metrics
    metrics = _calculate_metrics(modified_elements, adjacency, parameters)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "metrics": metrics,
        "execution_time_ms": elapsed_ms,
        "elements_analyzed": len(modified_elements),
        "connections_analyzed": len(connections),
    }


def _apply_parameters(
    elements: list[dict[str, Any]],
    parameters: dict[str, Any],
    simulation_type: str,
) -> list[dict[str, Any]]:
    """Apply simulation parameters to process elements."""
    modified = []
    for elem in elements:
        m = dict(elem)

        if simulation_type == "what_if":
            # Apply what-if changes
            changes = parameters.get("element_changes", {})
            if elem.get("name") in changes:
                m.update(changes[elem["name"]])
        elif simulation_type == "capacity":
            # Apply capacity scaling
            scale = parameters.get("capacity_scale", 1.0)
            if "throughput" in m:
                m["throughput"] = m["throughput"] * scale
        elif simulation_type == "process_change":
            # Remove/add elements
            removed = set(parameters.get("remove_elements", []))
            if elem.get("name") in removed:
                m["removed"] = True
        elif simulation_type == "control_removal":
            removed_controls = set(parameters.get("remove_controls", []))
            if elem.get("name") in removed_controls:
                m["control_active"] = False

        modified.append(m)

    return modified


def _calculate_metrics(
    elements: list[dict[str, Any]],
    adjacency: dict[str, list[str]],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Calculate simulation outcome metrics."""
    active_elements = [e for e in elements if not e.get("removed")]
    total_time = sum(e.get("duration", 0) for e in active_elements)
    active_controls = [e for e in active_elements if e.get("control_active", True) and e.get("type") == "control"]

    # Find critical path length (simple: longest chain)
    path_lengths: dict[str, int] = {}
    for elem in active_elements:
        name = elem.get("name", "")
        path_lengths[name] = 1

    for name in adjacency:
        for target in adjacency.get(name, []):
            if target in path_lengths:
                path_lengths[target] = max(
                    path_lengths.get(target, 0),
                    path_lengths.get(name, 0) + 1,
                )

    critical_path = max(path_lengths.values()) if path_lengths else 0

    return {
        "total_elements": len(active_elements),
        "total_estimated_time": total_time,
        "critical_path_length": critical_path,
        "active_controls": len(active_controls),
        "risk_score": _calculate_risk(active_elements, parameters),
        "efficiency_score": _calculate_efficiency(active_elements, total_time),
    }


def _calculate_risk(elements: list[dict[str, Any]], parameters: dict[str, Any]) -> float:
    """Calculate risk score (0.0 = low risk, 1.0 = high risk)."""
    total_controls = sum(1 for e in elements if e.get("type") == "control")
    active_controls = sum(
        1 for e in elements
        if e.get("type") == "control" and e.get("control_active", True)
    )

    if total_controls == 0:
        return 0.5

    control_coverage = active_controls / total_controls
    return round(1.0 - control_coverage, 3)


def _calculate_efficiency(elements: list[dict[str, Any]], total_time: float) -> float:
    """Calculate efficiency score (0.0 = inefficient, 1.0 = optimal)."""
    if not elements:
        return 0.0
    value_add = sum(1 for e in elements if e.get("value_add", True))
    ratio = value_add / len(elements) if elements else 0
    return round(ratio, 3)
