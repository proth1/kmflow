"""Controlled edge vocabulary and constraint validation for the knowledge graph.

Implements PRD v2.1 Section 6.2 controlled edge vocabulary with 12 typed
edge kinds, source/target type constraints, bidirectional edge creation,
and acyclicity enforcement within variants.
"""

from __future__ import annotations

import enum
import logging
from typing import Any

from neo4j import AsyncDriver

from src.semantic.ontology.loader import get_valid_endpoints

logger = logging.getLogger(__name__)


class EdgeVocabulary(enum.StrEnum):
    """The 12 controlled edge types from PRD v2.1 Section 6.2."""

    PRECEDES = "PRECEDES"
    TRIGGERS = "TRIGGERS"
    DEPENDS_ON = "DEPENDS_ON"
    CONSUMES = "CONSUMES"
    PRODUCES = "PRODUCES"
    GOVERNED_BY = "GOVERNED_BY"
    PERFORMED_BY = "PERFORMED_BY"
    EVIDENCED_BY = "EVIDENCED_BY"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    DECOMPOSES_INTO = "DECOMPOSES_INTO"
    VARIANT_OF = "VARIANT_OF"


# Edge types that require bidirectional edge creation
BIDIRECTIONAL_EDGES: frozenset[str] = frozenset({"CONTRADICTS", "VARIANT_OF"})

# Edge types that require acyclicity checks within a variant
ACYCLIC_EDGES: frozenset[str] = frozenset({"PRECEDES", "DEPENDS_ON"})


class EdgeValidationError(ValueError):
    """Raised when an edge violates source/target type constraints."""


class CycleDetectedError(ValueError):
    """Raised when creating an edge would introduce a cycle within a variant."""


class EdgeConstraintValidator:
    """Validates edge constraints before writes to Neo4j.

    Checks:
    - Source node label is in the edge type's valid_from list
    - Target node label is in the edge type's valid_to list
    - No cycles for PRECEDES/DEPENDS_ON within a variant_id scope
    - Bidirectional creation for CONTRADICTS/VARIANT_OF
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    def validate_endpoints(
        self,
        edge_type: str,
        source_label: str,
        target_label: str,
    ) -> None:
        """Validate source/target node labels against ontology constraints.

        Args:
            edge_type: The relationship type.
            source_label: Label of the source node.
            target_label: Label of the target node.

        Raises:
            EdgeValidationError: If the source or target label is not valid.
        """
        endpoints = get_valid_endpoints(edge_type)
        if endpoints is None:
            raise EdgeValidationError(f"Unknown edge type: {edge_type}")

        valid_from, valid_to = endpoints

        if valid_from and source_label not in valid_from:
            raise EdgeValidationError(f"{edge_type} source must be one of {valid_from}, got {source_label}")

        if valid_to and target_label not in valid_to:
            raise EdgeValidationError(f"{edge_type} target must be {', '.join(valid_to)}, got {target_label}")

    async def _get_node_label(self, node_id: str) -> str | None:
        """Look up the primary label of a node by ID.

        Args:
            node_id: The node identifier.

        Returns:
            The node's primary label, or None if not found.
        """

        async def _tx(tx):
            result = await tx.run(
                "MATCH (n {id: $nid}) RETURN labels(n) AS labels",
                {"nid": node_id},
            )
            data = await result.data()
            return data

        async with self._driver.session() as session:
            records = await session.execute_read(_tx)

        if not records:
            return None
        labels = records[0]["labels"]
        return labels[0] if labels else None

    async def _check_acyclicity(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
        variant_id: str | None,
    ) -> None:
        """Check that adding this edge won't create a cycle within the variant.

        Uses a reachability query: if to_id can already reach from_id via
        edges of the same type (filtered by variant_id), adding from_id→to_id
        would create a cycle.

        Args:
            edge_type: The relationship type.
            from_id: Source node ID.
            to_id: Target node ID.
            variant_id: Optional variant scope for the acyclicity check.

        Raises:
            CycleDetectedError: If a cycle would be created.
        """
        if variant_id:
            query = f"""
            MATCH path = (target {{id: $to_id}})-[:{edge_type}*1..50]->(source {{id: $from_id}})
            WHERE ALL(r IN relationships(path) WHERE r.variant_id = $variant_id)
            RETURN count(path) > 0 AS has_path
            """
            params: dict[str, Any] = {"from_id": from_id, "to_id": to_id, "variant_id": variant_id}
        else:
            query = f"""
            MATCH path = (target {{id: $to_id}})-[:{edge_type}*1..50]->(source {{id: $from_id}})
            RETURN count(path) > 0 AS has_path
            """
            params = {"from_id": from_id, "to_id": to_id}

        async def _tx(tx):
            result = await tx.run(query, params)
            return await result.data()

        async with self._driver.session() as session:
            records = await session.execute_read(_tx)

        if records and records[0]["has_path"]:
            raise CycleDetectedError(
                f"Creating {edge_type} edge {from_id}->{to_id} would create a cycle"
                + (f" within variant '{variant_id}'" if variant_id else "")
            )

    async def create_validated_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Create an edge with full constraint validation.

        Steps:
        1. Look up source and target node labels
        2. Validate against ontology endpoint constraints
        3. Check acyclicity for PRECEDES/DEPENDS_ON
        4. Create the edge (and reverse edge for bidirectional types)

        Args:
            from_id: Source node ID.
            to_id: Target node ID.
            edge_type: The relationship type (must be a valid ontology type).
            properties: Optional edge properties.

        Returns:
            List of created edge dicts with 'from_id', 'to_id', 'type' keys.

        Raises:
            EdgeValidationError: If endpoint constraints are violated.
            CycleDetectedError: If acyclicity would be violated.
            ValueError: If source or target node doesn't exist.
        """
        # Step 1: Look up node labels
        source_label = await self._get_node_label(from_id)
        if source_label is None:
            raise ValueError(f"Source node not found: {from_id}")

        target_label = await self._get_node_label(to_id)
        if target_label is None:
            raise ValueError(f"Target node not found: {to_id}")

        # Step 2: Validate endpoints
        self.validate_endpoints(edge_type, source_label, target_label)

        # Step 3: Acyclicity check
        if edge_type in ACYCLIC_EDGES:
            variant_id = (properties or {}).get("variant_id")
            await self._check_acyclicity(edge_type, from_id, to_id, variant_id)

        # Step 4: Create edge(s)
        props = properties or {}
        created: list[dict[str, str]] = []

        await self._write_edge(from_id, to_id, edge_type, props)
        created.append({"from_id": from_id, "to_id": to_id, "type": edge_type})

        # Bidirectional: create reverse edge
        if edge_type in BIDIRECTIONAL_EDGES:
            await self._write_edge(to_id, from_id, edge_type, props)
            created.append({"from_id": to_id, "to_id": from_id, "type": edge_type})

        logger.info(
            "Created %d %s edge(s): %s->%s",
            len(created),
            edge_type,
            from_id,
            to_id,
        )
        return created

    async def _write_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        properties: dict[str, Any],
    ) -> None:
        """Write a single edge to Neo4j within a write transaction."""
        import uuid

        edge_id = uuid.uuid4().hex[:16]
        props = {**properties, "id": edge_id}

        set_parts = ", ".join(f"r.{k} = $prop_{k}" for k in props)
        prop_params = {f"prop_{k}": v for k, v in props.items()}

        query = f"""
        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
        CREATE (a)-[r:{edge_type}]->(b)
        SET {set_parts}
        RETURN r.id AS id
        """
        params = {"from_id": from_id, "to_id": to_id, **prop_params}

        async def _tx(tx):
            result = await tx.run(query, params)
            return await result.data()

        async with self._driver.session() as session:
            await session.execute_write(_tx)
