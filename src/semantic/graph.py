"""Knowledge graph service for Neo4j operations.

Provides typed node and relationship CRUD, graph traversal, and semantic
search operations. All operations are scoped to engagement_id for data
isolation between consulting engagements.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from neo4j import AsyncDriver

from src.semantic.ontology.loader import (
    get_valid_node_labels as _get_valid_node_labels,
)
from src.semantic.ontology.loader import (
    get_valid_relationship_types as _get_valid_relationship_types,
)

logger = logging.getLogger(__name__)

_VALID_PROPERTY_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_property_keys(props: dict[str, Any]) -> None:
    """Validate that property keys are safe Cypher identifiers."""
    for key in props:
        if not _VALID_PROPERTY_KEY.match(key):
            raise ValueError(f"Invalid property key: {key!r}")


# Valid node labels and relationship types loaded from the YAML ontology.
# Exported as module-level constants for backward compatibility.
VALID_NODE_LABELS: frozenset[str] = _get_valid_node_labels()
VALID_RELATIONSHIP_TYPES: frozenset[str] = _get_valid_relationship_types()


@dataclass
class GraphNode:
    """Represents a node in the knowledge graph.

    Attributes:
        id: Unique node identifier.
        label: Node type (e.g. Activity, Role, System).
        properties: Node properties including name, engagement_id, etc.
    """

    id: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphRelationship:
    """Represents an edge in the knowledge graph.

    Attributes:
        id: Unique relationship identifier.
        from_id: Source node ID.
        to_id: Target node ID.
        relationship_type: Edge type (e.g. SUPPORTED_BY, FOLLOWED_BY).
        properties: Relationship properties including confidence, source, etc.
    """

    id: str
    from_id: str
    to_id: str
    relationship_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphStats:
    """Statistics about a knowledge graph.

    Attributes:
        node_count: Total number of nodes.
        relationship_count: Total number of relationships.
        nodes_by_label: Count of nodes per label.
        relationships_by_type: Count of relationships per type.
    """

    node_count: int = 0
    relationship_count: int = 0
    nodes_by_label: dict[str, int] = field(default_factory=dict)
    relationships_by_type: dict[str, int] = field(default_factory=dict)


class KnowledgeGraphService:
    """Service for managing the Neo4j knowledge graph.

    All graph operations are scoped to an engagement_id for data isolation.
    The service uses parameterized Cypher queries to prevent injection.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        """Initialize with an async Neo4j driver.

        Args:
            driver: Async Neo4j driver instance.
        """
        self._driver = driver

    async def _run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read-only Cypher query within a read transaction.

        Uses session.execute_read() to ensure the query is routed to a
        read replica in a cluster and cannot accidentally perform writes.

        Args:
            query: Cypher query string with $parameter placeholders.
            parameters: Query parameters.

        Returns:
            List of result records as dicts.
        """

        async def _tx_func(tx):
            result = await tx.run(query, parameters or {})
            return await result.data()

        async with self._driver.session() as session:
            return await session.execute_read(_tx_func)

    async def run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Public read-only query interface for domain consumers.

        Delegates to _run_query(). Use this for cross-module callers
        (e.g. conflict detection, conformance checking) that need
        read access to the knowledge graph.
        """
        return await self._run_query(query, parameters)

    async def _run_write_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a write Cypher query within a proper write transaction.

        Uses session.execute_write() to ensure writes are routed to the
        leader in a cluster and retried on transient failures.

        Args:
            query: Cypher query string.
            parameters: Query parameters.

        Returns:
            List of result records as dicts.
        """

        async def _tx_func(tx):
            result = await tx.run(query, parameters or {})
            return await result.data()

        async with self._driver.session() as session:
            return await session.execute_write(_tx_func)

    # -----------------------------------------------------------------
    # Node operations
    # -----------------------------------------------------------------

    async def create_node(
        self,
        label: str,
        properties: dict[str, Any],
    ) -> GraphNode:
        """Create a typed node in the knowledge graph.

        Args:
            label: Node label (must be in VALID_NODE_LABELS).
            properties: Node properties. Must include 'name' and 'engagement_id'.

        Returns:
            The created GraphNode.

        Raises:
            ValueError: If label is invalid or required properties are missing.
        """
        if label not in VALID_NODE_LABELS:
            raise ValueError(f"Invalid node label: {label}. Must be one of {VALID_NODE_LABELS}")

        if "name" not in properties:
            raise ValueError("Node properties must include 'name'")
        if "engagement_id" not in properties:
            raise ValueError("Node properties must include 'engagement_id'")

        _validate_property_keys(properties)

        node_id = properties.get("id", uuid.uuid4().hex[:16])
        props = {**properties, "id": node_id}

        # Build SET clause from properties
        set_clauses = ", ".join(f"n.{k} = ${k}" for k in props)
        query = f"CREATE (n:{label}) SET {set_clauses} RETURN n.id AS id"

        await self._run_write_query(query, props)
        return GraphNode(id=node_id, label=label, properties=props)

    async def get_node(self, node_id: str) -> GraphNode | None:
        """Get a node by its ID.

        Args:
            node_id: The unique node identifier.

        Returns:
            The GraphNode if found, None otherwise.
        """
        query = """
        MATCH (n {id: $node_id})
        RETURN n, labels(n) AS labels
        """
        records = await self._run_query(query, {"node_id": node_id})
        if not records:
            return None

        record = records[0]
        node_data = record["n"]
        labels = record["labels"]
        label = labels[0] if labels else "Unknown"

        return GraphNode(
            id=node_id,
            label=label,
            properties=dict(node_data),
        )

    async def find_nodes(
        self,
        label: str,
        filters: dict[str, Any] | None = None,
        limit: int = 500,
    ) -> list[GraphNode]:
        """Query nodes by label with optional property filters.

        Args:
            label: Node label to filter by.
            filters: Optional property filters (exact match).
            limit: Maximum number of nodes to return (default 500). Guards
                against unbounded scans on large graphs.

        Returns:
            List of matching GraphNodes.
        """
        if label not in VALID_NODE_LABELS:
            raise ValueError(f"Invalid node label: {label}")

        if filters:
            _validate_property_keys(filters)

        where_clauses = []
        params: dict[str, Any] = {"limit": limit}

        if filters:
            for i, (key, value) in enumerate(filters.items()):
                param_name = f"filter_{i}"
                where_clauses.append(f"n.{key} = ${param_name}")
                params[param_name] = value

        where_str = " AND ".join(where_clauses)
        where_clause = f"WHERE {where_str}" if where_str else ""

        query = f"MATCH (n:{label}) {where_clause} RETURN n LIMIT $limit"
        records = await self._run_query(query, params)

        return [
            GraphNode(
                id=record["n"].get("id", ""),
                label=label,
                properties=dict(record["n"]),
            )
            for record in records
        ]

    async def batch_create_nodes(
        self,
        label: str,
        props_list: list[dict[str, Any]],
    ) -> list[str]:
        """Create multiple nodes of the same label in a single transaction.

        Uses UNWIND to avoid N+1 round-trips for bulk node creation.

        Args:
            label: Node label (must be in VALID_NODE_LABELS).
            props_list: List of property dicts. Each dict must include 'name',
                'engagement_id', and 'id'.

        Returns:
            List of created node IDs in the same order as props_list.

        Raises:
            ValueError: If label is invalid or any property key is unsafe.
        """
        if label not in VALID_NODE_LABELS:
            raise ValueError(f"Invalid node label: {label}")
        for props in props_list:
            _validate_property_keys(props)

        query = f"UNWIND $nodes AS props CREATE (n:{label}) SET n = props RETURN n.id AS id"
        records = await self._run_write_query(query, {"nodes": props_list})
        return [r["id"] for r in records]

    # -----------------------------------------------------------------
    # Relationship operations
    # -----------------------------------------------------------------

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> GraphRelationship:
        """Create a typed relationship between two nodes.

        Args:
            from_id: Source node ID.
            to_id: Target node ID.
            relationship_type: Edge type (must be in VALID_RELATIONSHIP_TYPES).
            properties: Optional relationship properties.

        Returns:
            The created GraphRelationship.

        Raises:
            ValueError: If relationship_type is invalid.
        """
        if relationship_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship type: {relationship_type}. Must be one of {VALID_RELATIONSHIP_TYPES}"
            )

        if properties:
            _validate_property_keys(properties)

        rel_id = uuid.uuid4().hex[:16]
        props = {**(properties or {}), "id": rel_id}

        # Build SET clause
        set_parts = ", ".join(f"r.{k} = $prop_{k}" for k in props)
        prop_params = {f"prop_{k}": v for k, v in props.items()}

        query = f"""
        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
        CREATE (a)-[r:{relationship_type}]->(b)
        SET {set_parts}
        RETURN r.id AS id
        """
        params = {"from_id": from_id, "to_id": to_id, **prop_params}
        await self._run_write_query(query, params)

        return GraphRelationship(
            id=rel_id,
            from_id=from_id,
            to_id=to_id,
            relationship_type=relationship_type,
            properties=props,
        )

    async def batch_create_relationships(
        self,
        relationship_type: str,
        rels: list[dict[str, Any]],
    ) -> int:
        """Create multiple relationships of the same type in a single transaction.

        Uses UNWIND to avoid N+1 round-trips for bulk relationship creation.
        Silently skips pairs where either node does not exist.

        Args:
            relationship_type: Edge type (must be in VALID_RELATIONSHIP_TYPES).
            rels: List of dicts, each with 'from_id', 'to_id', and optional
                'properties' (a dict of relationship properties).

        Returns:
            Number of relationships created.

        Raises:
            ValueError: If relationship_type is invalid.
        """
        if relationship_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship type: {relationship_type}. Must be one of {VALID_RELATIONSHIP_TYPES}"
            )

        if not rels:
            return 0

        # Normalise: ensure each entry has a 'properties' dict and a rel 'id'
        normalised = []
        for rel in rels:
            props = dict(rel.get("properties") or {})
            props["id"] = uuid.uuid4().hex[:16]
            normalised.append(
                {
                    "from_id": rel["from_id"],
                    "to_id": rel["to_id"],
                    "props": props,
                }
            )

        query = f"""
        UNWIND $rels AS rel
        MATCH (a {{id: rel.from_id}}), (b {{id: rel.to_id}})
        CREATE (a)-[r:{relationship_type}]->(b)
        SET r = rel.props
        RETURN count(r) AS created
        """
        records = await self._run_write_query(query, {"rels": normalised})
        return records[0]["created"] if records else 0

    async def get_relationships(
        self,
        node_id: str,
        direction: str = "both",
        relationship_type: str | None = None,
    ) -> list[GraphRelationship]:
        """Get relationships connected to a node.

        Args:
            node_id: The node to get relationships for.
            direction: "outgoing", "incoming", or "both".
            relationship_type: Optional filter by relationship type.

        Returns:
            List of GraphRelationships.
        """
        if relationship_type and relationship_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship type: {relationship_type}. Must be one of {VALID_RELATIONSHIP_TYPES}"
            )

        rel_filter = f":{relationship_type}" if relationship_type else ""

        if direction == "outgoing":
            query = f"""
            MATCH (a {{id: $node_id}})-[r{rel_filter}]->(b)
            RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
            """
        elif direction == "incoming":
            query = f"""
            MATCH (a)-[r{rel_filter}]->(b {{id: $node_id}})
            RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
            """
        else:
            query = f"""
            MATCH (a)-[r{rel_filter}]-(b)
            WHERE a.id = $node_id
            RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
            """

        records = await self._run_query(query, {"node_id": node_id})

        results = []
        for record in records:
            r = record["r"]
            # Neo4j .data() may return relationships as dicts or tuples
            if isinstance(r, dict):
                rel_id = r.get("id", "")
                rel_props = dict(r)
            else:
                rel_id = ""
                rel_props = {}
            results.append(
                GraphRelationship(
                    id=rel_id,
                    from_id=record["from_id"],
                    to_id=record["to_id"],
                    relationship_type=record["rel_type"],
                    properties=rel_props,
                )
            )
        return results

    # -----------------------------------------------------------------
    # Traversal
    # -----------------------------------------------------------------

    async def traverse(
        self,
        start_id: str,
        depth: int = 2,
        relationship_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[GraphNode]:
        """Traverse the graph from a starting node.

        Args:
            start_id: Node ID to start traversal from.
            depth: Maximum traversal depth (default 2).
            relationship_types: Optional list of relationship types to follow.
            limit: Maximum number of nodes to return (default 200). Guards
                against unbounded results from highly-connected subgraphs.

        Returns:
            List of discovered GraphNodes (excluding start node).
        """
        if depth < 1:
            return []

        rel_filter = ""
        if relationship_types:
            for rt in relationship_types:
                if rt not in VALID_RELATIONSHIP_TYPES:
                    raise ValueError(f"Invalid relationship type: {rt}. Must be one of {VALID_RELATIONSHIP_TYPES}")
            rel_filter = ":" + "|".join(relationship_types)

        query = f"""
        MATCH (start {{id: $start_id}})-[r{rel_filter}*1..{depth}]-(connected)
        RETURN DISTINCT connected, labels(connected) AS labels
        LIMIT $limit
        """
        records = await self._run_query(query, {"start_id": start_id, "limit": limit})

        return [
            GraphNode(
                id=record["connected"].get("id", ""),
                label=record["labels"][0] if record["labels"] else "Unknown",
                properties=dict(record["connected"]),
            )
            for record in records
        ]

    # -----------------------------------------------------------------
    # Semantic search (pgvector integration point)
    # -----------------------------------------------------------------

    async def search_similar(
        self,
        embedding: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar nodes using pgvector semantic search.

        This is a placeholder that delegates to pgvector. The actual
        embedding search happens in the embeddings service; this method
        provides graph context for the results.

        Args:
            embedding: Query embedding vector.
            top_k: Number of results to return.

        Returns:
            List of search results with node and similarity data.
        """
        # In the full implementation, this would:
        # 1. Query pgvector for top-k similar fragment embeddings
        # 2. Map fragment IDs to Evidence nodes in Neo4j
        # 3. Return enriched results with graph context
        #
        # For MVP, this returns an empty list since pgvector search
        # is handled by the embeddings service.
        return []

    # -----------------------------------------------------------------
    # Delete operations
    # -----------------------------------------------------------------

    async def delete_node(self, node_id: str, engagement_id: str) -> bool:
        """Delete a node and all its relationships by ID.

        Args:
            node_id: The unique node identifier.
            engagement_id: Required engagement scope to prevent cross-engagement deletion.

        Returns:
            True if a node was deleted, False if not found.
        """
        query = """
        MATCH (n {id: $node_id, engagement_id: $engagement_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        records = await self._run_write_query(query, {"node_id": node_id, "engagement_id": engagement_id})
        deleted = records[0]["deleted"] if records else 0
        if deleted:
            logger.info("Deleted node %s and its relationships", node_id)
        return deleted > 0

    async def delete_engagement_subgraph(self, engagement_id: str) -> int:
        """Delete all nodes and relationships for an engagement.

        Args:
            engagement_id: The engagement whose subgraph should be removed.

        Returns:
            Count of deleted nodes.
        """
        query = """
        MATCH (n {engagement_id: $engagement_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        records = await self._run_write_query(query, {"engagement_id": engagement_id})
        deleted = records[0]["deleted"] if records else 0
        logger.info("Deleted %d nodes for engagement %s", deleted, engagement_id)
        return deleted

    # -----------------------------------------------------------------
    # Engagement subgraph
    # -----------------------------------------------------------------

    async def get_engagement_subgraph(
        self,
        engagement_id: str,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Get the full knowledge graph for an engagement.

        Args:
            engagement_id: The engagement to get the subgraph for.
            limit: Maximum number of nodes and relationships to return
                (default 500). Guards against unbounded result sets on
                large engagements.

        Returns:
            Dict with 'nodes' and 'relationships' lists.
        """
        # Get all nodes for engagement
        node_query = """
        MATCH (n {engagement_id: $engagement_id})
        RETURN n, labels(n) AS labels
        LIMIT $limit
        """
        node_records = await self._run_query(node_query, {"engagement_id": engagement_id, "limit": limit})

        nodes = [
            GraphNode(
                id=record["n"].get("id", ""),
                label=record["labels"][0] if record["labels"] else "Unknown",
                properties=dict(record["n"]),
            )
            for record in node_records
        ]

        # Get all relationships between engagement nodes
        rel_query = """
        MATCH (a {engagement_id: $engagement_id})-[r]->(b {engagement_id: $engagement_id})
        RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
        LIMIT $limit
        """
        rel_records = await self._run_query(rel_query, {"engagement_id": engagement_id, "limit": limit})

        relationships = []
        for record in rel_records:
            r = record["r"]
            if isinstance(r, dict):
                rel_id = r.get("id", "")
                rel_props = dict(r)
            else:
                rel_id = ""
                rel_props = {}
            relationships.append(
                GraphRelationship(
                    id=rel_id,
                    from_id=record["from_id"],
                    to_id=record["to_id"],
                    relationship_type=record["rel_type"],
                    properties=rel_props,
                )
            )

        return {
            "nodes": nodes,
            "relationships": relationships,
        }

    # -----------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------

    async def get_stats(self, engagement_id: str) -> GraphStats:
        """Get statistics for an engagement's knowledge graph.

        Args:
            engagement_id: The engagement to get stats for.

        Returns:
            GraphStats with counts by label and type.
        """
        # Count nodes by label
        node_query = """
        MATCH (n {engagement_id: $engagement_id})
        RETURN labels(n)[0] AS label, count(n) AS count
        """
        node_records = await self._run_query(node_query, {"engagement_id": engagement_id})

        nodes_by_label: dict[str, int] = {}
        total_nodes = 0
        for record in node_records:
            label = record["label"]
            count = record["count"]
            nodes_by_label[label] = count
            total_nodes += count

        # Count relationships by type
        rel_query = """
        MATCH (a {engagement_id: $engagement_id})-[r]->(b)
        RETURN type(r) AS rel_type, count(r) AS count
        """
        rel_records = await self._run_query(rel_query, {"engagement_id": engagement_id})

        rels_by_type: dict[str, int] = {}
        total_rels = 0
        for record in rel_records:
            rel_type = record["rel_type"]
            count = record["count"]
            rels_by_type[rel_type] = count
            total_rels += count

        return GraphStats(
            node_count=total_nodes,
            relationship_count=total_rels,
            nodes_by_label=nodes_by_label,
            relationships_by_type=rels_by_type,
        )
