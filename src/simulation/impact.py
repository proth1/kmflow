"""Cascading effect calculation for simulation impacts.

Analyzes how changes propagate through a process graph to
affect downstream elements and metrics.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def calculate_cascading_impact(
    changed_elements: list[str],
    process_graph: dict[str, Any],
) -> dict[str, Any]:
    """Calculate the cascading impact of changes on downstream elements.

    Args:
        changed_elements: Names of elements that were modified.
        process_graph: The process model graph.

    Returns:
        Impact analysis with affected elements and severity.
    """
    connections = process_graph.get("connections", [])

    # Build forward adjacency
    forward: dict[str, list[str]] = {}
    for conn in connections:
        source = conn.get("source", "")
        target = conn.get("target", "")
        if source not in forward:
            forward[source] = []
        forward[source].append(target)

    # BFS to find all affected downstream elements
    affected: dict[str, int] = {}  # element -> distance from change
    queue: list[tuple[str, int]] = [(elem, 0) for elem in changed_elements]
    visited: set[str] = set(changed_elements)

    while queue:
        current, depth = queue.pop(0)
        for downstream in forward.get(current, []):
            if downstream not in visited:
                visited.add(downstream)
                affected[downstream] = depth + 1
                queue.append((downstream, depth + 1))

    # Calculate severity based on distance
    impact_items: list[dict[str, Any]] = []
    for element, distance in sorted(affected.items(), key=lambda x: x[1]):
        severity = max(0.1, 1.0 - (distance * 0.2))
        impact_items.append(
            {
                "element": element,
                "distance": distance,
                "severity": round(severity, 2),
                "impact_type": "direct" if distance == 1 else "cascading",
            }
        )

    return {
        "changed_elements": changed_elements,
        "total_affected": len(affected),
        "max_cascade_depth": max(affected.values()) if affected else 0,
        "impact_items": impact_items,
    }


def compare_simulation_results(
    baseline_metrics: dict[str, Any],
    simulation_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Compare baseline and simulation metrics to assess impact.

    Returns:
        Dict with metric deltas and overall assessment.
    """
    deltas: dict[str, Any] = {}

    for key in baseline_metrics:
        if key in simulation_metrics:
            base_val = baseline_metrics[key]
            sim_val = simulation_metrics[key]
            if isinstance(base_val, (int, float)) and isinstance(sim_val, (int, float)):
                delta = sim_val - base_val
                pct_change = (delta / base_val * 100) if base_val != 0 else 0
                deltas[key] = {
                    "baseline": base_val,
                    "simulated": sim_val,
                    "delta": round(delta, 3),
                    "pct_change": round(pct_change, 1),
                }

    # Overall assessment
    risk_delta = deltas.get("risk_score", {}).get("delta", 0)
    efficiency_delta = deltas.get("efficiency_score", {}).get("delta", 0)

    if risk_delta > 0.2:
        assessment = "high_risk_increase"
    elif risk_delta < -0.1 and efficiency_delta > 0:
        assessment = "improvement"
    elif efficiency_delta < -0.1:
        assessment = "efficiency_decrease"
    else:
        assessment = "neutral"

    return {
        "deltas": deltas,
        "assessment": assessment,
    }
