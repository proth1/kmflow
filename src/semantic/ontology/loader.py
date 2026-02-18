"""Ontology loader for the KMFlow knowledge graph.

Loads the YAML ontology schema and provides typed accessors that replace
the hardcoded frozenset/dict constants previously in graph.py, builder.py,
and pipeline.py. The schema is loaded once at module import time and cached.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

_ONTOLOGY_PATH = Path(__file__).parent / "kmflow_ontology.yaml"


@functools.cache
def _load_ontology() -> dict[str, Any]:
    """Load and cache the YAML ontology schema."""
    with open(_ONTOLOGY_PATH) as f:
        return yaml.safe_load(f)


def get_ontology() -> dict[str, Any]:
    """Return the full ontology dict (cached after first load)."""
    return _load_ontology()


def get_valid_node_labels() -> frozenset[str]:
    """Return the set of valid node labels for the knowledge graph.

    Replaces the hardcoded ``VALID_NODE_LABELS`` frozenset that was in
    ``src.semantic.graph``.
    """
    ontology = _load_ontology()
    return frozenset(ontology["node_types"].keys())


def get_valid_relationship_types() -> frozenset[str]:
    """Return the set of valid relationship types.

    Replaces the hardcoded ``VALID_RELATIONSHIP_TYPES`` frozenset that was
    in ``src.semantic.graph``.
    """
    ontology = _load_ontology()
    return frozenset(ontology["relationship_types"].keys())


def get_extractable_types() -> dict[str, str]:
    """Return node types that can be extracted from evidence text.

    Returns:
        Dict mapping ``entity_type`` value (e.g. ``"activity"``) to the
        Neo4j node label (e.g. ``"Activity"``).
    """
    ontology = _load_ontology()
    result: dict[str, str] = {}
    for label, defn in ontology["node_types"].items():
        if defn.get("extractable"):
            result[defn["entity_type"]] = label
    return result


def get_entity_type_to_label() -> dict[str, str]:
    """Return mapping from EntityType enum values to Neo4j node labels.

    Replaces the hardcoded ``_ENTITY_TYPE_TO_LABEL`` dicts in
    ``src.semantic.builder`` and ``src.evidence.pipeline``.
    """
    return get_extractable_types()


def get_node_type_definition(label: str) -> dict[str, Any] | None:
    """Return the full definition for a node type, or None."""
    ontology = _load_ontology()
    return ontology["node_types"].get(label)


def get_relationship_definition(rel_type: str) -> dict[str, Any] | None:
    """Return the full definition for a relationship type, or None."""
    ontology = _load_ontology()
    return ontology["relationship_types"].get(rel_type)


def get_valid_endpoints(rel_type: str) -> tuple[list[str], list[str]] | None:
    """Return (valid_from, valid_to) for a relationship type.

    Returns:
        Tuple of (from_labels, to_labels) or None if type is unknown.
    """
    defn = get_relationship_definition(rel_type)
    if defn is None:
        return None
    return defn.get("valid_from", []), defn.get("valid_to", [])
