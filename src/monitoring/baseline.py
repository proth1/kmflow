"""Baseline snapshot creation for process models.

Creates frozen snapshots of process model state that can be used
for comparison when detecting deviations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_baseline_snapshot(
    process_model_data: dict[str, Any],
) -> dict[str, Any]:
    """Create a baseline snapshot from process model data.

    Args:
        process_model_data: The process model to snapshot, including
            elements, connections, and metadata.

    Returns:
        Snapshot dict with element_count and process_hash.
    """
    elements = process_model_data.get("elements", [])
    connections = process_model_data.get("connections", [])

    snapshot = {
        "elements": elements,
        "connections": connections,
        "element_names": sorted([e.get("name", "") for e in elements]),
        "element_types": {e.get("name", ""): e.get("type", "") for e in elements},
        "connection_pairs": [(c.get("source", ""), c.get("target", "")) for c in connections],
    }

    return snapshot


def compute_process_hash(snapshot_data: dict[str, Any]) -> str:
    """Compute a deterministic hash of a process snapshot.

    Args:
        snapshot_data: The snapshot to hash.

    Returns:
        SHA-256 hex digest of the snapshot.
    """
    canonical = json.dumps(snapshot_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def compare_baselines(
    baseline_snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Compare two process snapshots and identify differences.

    Args:
        baseline_snapshot: The reference baseline.
        current_snapshot: The current state to compare.

    Returns:
        Dict with added/removed/modified elements and connections.
    """
    baseline_names = set(baseline_snapshot.get("element_names", []))
    current_names = set(current_snapshot.get("element_names", []))

    added = current_names - baseline_names
    removed = baseline_names - current_names
    common = baseline_names & current_names

    baseline_types = baseline_snapshot.get("element_types", {})
    current_types = current_snapshot.get("element_types", {})

    modified = []
    for name in common:
        if baseline_types.get(name) != current_types.get(name):
            modified.append(
                {
                    "name": name,
                    "baseline_type": baseline_types.get(name),
                    "current_type": current_types.get(name),
                }
            )

    baseline_conns = set(tuple(p) for p in baseline_snapshot.get("connection_pairs", []))
    current_conns = set(tuple(p) for p in current_snapshot.get("connection_pairs", []))

    return {
        "added_elements": sorted(added),
        "removed_elements": sorted(removed),
        "modified_elements": modified,
        "added_connections": sorted(current_conns - baseline_conns),
        "removed_connections": sorted(baseline_conns - current_conns),
        "has_changes": bool(added or removed or modified or (current_conns != baseline_conns)),
    }
