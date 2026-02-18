"""Ontology validation CLI.

Validates the YAML ontology schema for internal consistency and optionally
checks that a live Neo4j instance conforms to the schema.

Usage::

    # Schema-only validation (no Neo4j required)
    python -m src.semantic.ontology.validate

    # Also check live Neo4j data
    python -m src.semantic.ontology.validate --neo4j bolt://localhost:7687
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.semantic.ontology.loader import (
    get_ontology,
    get_valid_node_labels,
    get_valid_relationship_types,
)


def validate_schema() -> list[str]:
    """Validate the ontology YAML for internal consistency.

    Returns:
        List of error messages (empty = valid).
    """
    errors: list[str] = []
    ontology = get_ontology()

    # Check required top-level keys
    for key in ("version", "node_types", "relationship_types"):
        if key not in ontology:
            errors.append(f"Missing required top-level key: {key}")

    if errors:
        return errors

    node_labels = set(ontology["node_types"].keys())
    rel_types = set(ontology["relationship_types"].keys())

    # Validate node types
    for label, defn in ontology["node_types"].items():
        if "description" not in defn:
            errors.append(f"Node type '{label}' missing 'description'")

        if defn.get("extractable") and "entity_type" not in defn:
            errors.append(f"Extractable node type '{label}' missing 'entity_type'")

        req_props = defn.get("required_properties", [])
        if "name" not in req_props:
            errors.append(f"Node type '{label}' should require 'name' property")
        if "engagement_id" not in req_props:
            errors.append(f"Node type '{label}' should require 'engagement_id' property")

    # Validate relationship types
    for rel_type, defn in ontology["relationship_types"].items():
        if "description" not in defn:
            errors.append(f"Relationship type '{rel_type}' missing 'description'")

        # Check valid_from / valid_to reference existing node types
        for endpoint_key in ("valid_from", "valid_to"):
            endpoints = defn.get(endpoint_key, [])
            for ep_label in endpoints:
                if ep_label not in node_labels:
                    errors.append(
                        f"Relationship '{rel_type}' {endpoint_key} references "
                        f"unknown node type '{ep_label}'"
                    )

    # Check expected counts (from PRD: 13 node types, 12 relationship types)
    if len(node_labels) != 13:
        errors.append(
            f"Expected 13 node types, found {len(node_labels)}: {sorted(node_labels)}"
        )
    if len(rel_types) != 12:
        errors.append(
            f"Expected 12 relationship types, found {len(rel_types)}: {sorted(rel_types)}"
        )

    # Check extractable types cover the 5 EntityType enum values
    extractable = {
        defn["entity_type"]
        for defn in ontology["node_types"].values()
        if defn.get("extractable")
    }
    expected_extractable = {"activity", "decision", "role", "system", "document"}
    if extractable != expected_extractable:
        missing = expected_extractable - extractable
        extra = extractable - expected_extractable
        if missing:
            errors.append(f"Missing extractable entity types: {missing}")
        if extra:
            errors.append(f"Unexpected extractable entity types: {extra}")

    return errors


async def validate_neo4j(uri: str, user: str = "neo4j", password: str = "password") -> list[str]:
    """Check that a live Neo4j database conforms to the ontology.

    Args:
        uri: Neo4j bolt URI.
        user: Neo4j username.
        password: Neo4j password.

    Returns:
        List of warning messages about schema drift.
    """
    warnings: list[str] = []

    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        warnings.append("neo4j driver not installed — skipping live validation")
        return warnings

    valid_labels = get_valid_node_labels()
    valid_rels = get_valid_relationship_types()

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            # Check for unknown node labels
            result = await session.run("CALL db.labels()")
            records = await result.data()
            for record in records:
                label = record.get("label", "")
                if label and label not in valid_labels:
                    warnings.append(f"Neo4j has unknown node label: '{label}'")

            # Check for unknown relationship types
            result = await session.run("CALL db.relationshipTypes()")
            records = await result.data()
            for record in records:
                rel_type = record.get("relationshipType", "")
                if rel_type and rel_type not in valid_rels:
                    warnings.append(f"Neo4j has unknown relationship type: '{rel_type}'")
    finally:
        await driver.close()

    return warnings


def main() -> None:
    """Run ontology validation from the command line."""
    parser = argparse.ArgumentParser(
        description="Validate KMFlow knowledge graph ontology schema"
    )
    parser.add_argument(
        "--neo4j",
        type=str,
        default=None,
        help="Neo4j bolt URI for live validation (e.g. bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default="password",
        help="Neo4j password (default: password)",
    )
    args = parser.parse_args()

    print("Validating KMFlow ontology schema...")
    print()

    # Schema validation
    errors = validate_schema()
    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    node_labels = get_valid_node_labels()
    rel_types = get_valid_relationship_types()
    print(f"Schema OK: {len(node_labels)} node types, {len(rel_types)} relationship types")
    print(f"  Node types: {sorted(node_labels)}")
    print(f"  Relationship types: {sorted(rel_types)}")

    # Live Neo4j validation
    if args.neo4j:
        print()
        print(f"Checking Neo4j at {args.neo4j}...")
        warnings = asyncio.run(
            validate_neo4j(args.neo4j, args.neo4j_user, args.neo4j_password)
        )
        if warnings:
            print(f"  {len(warnings)} warning(s):")
            for w in warnings:
                print(f"    - {w}")
        else:
            print("  Neo4j schema matches ontology.")

    print()
    print("Validation complete.")


if __name__ == "__main__":
    main()
