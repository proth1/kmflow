"""Knowledge graph health analysis.

Runs standard Cypher queries to assess graph connectivity, orphan nodes,
schema conformance, and entity type coverage — no GDS plugin required.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from typing import Any

from neo4j import AsyncDriver
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.pipeline_quality import GraphHealthSnapshot
from src.semantic.ontology.loader import get_entity_type_to_label, get_valid_node_labels, get_valid_relationship_types

logger = logging.getLogger(__name__)

# Relationship types that are always considered valid regardless of ontology.
_ALWAYS_VALID_REL_TYPES: frozenset[str] = frozenset(
    {
        "RELATED_TO",
        "MENTIONS",
        "CONTAINS",
        "REFERENCES",
        "LINKS_TO",
    }
)


# ---------------------------------------------------------------------------
# Union-find helpers
# ---------------------------------------------------------------------------


class _UnionFind:
    """Lightweight union-find (disjoint set union) for component counting."""

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}
        self._rank: dict[int, int] = {}

    def _ensure(self, x: int) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0

    def find(self, x: int) -> int:
        self._ensure(x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])  # path compression
        return self._parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Union by rank
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def components(self) -> Iterator[tuple[int, list[int]]]:
        """Yield (root, members) for every component."""
        groups: dict[int, list[int]] = {}
        for node in self._parent:
            root = self.find(node)
            groups.setdefault(root, []).append(node)
        yield from groups.items()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_components(
    neo4j_session: Any,
    engagement_id: str,
) -> tuple[int, int]:
    """Return (component_count, largest_component_size) using union-find.

    Fetches all edges within the engagement and processes them in Python so
    that no GDS plugin is required.  Orphan nodes (no edges) are each counted
    as their own single-node component.
    """
    uf = _UnionFind()

    # Collect all edges first (capped at 10 000 to avoid unbounded scans).
    edge_limit = 10_000
    edge_result = await neo4j_session.run(
        "MATCH (a {engagement_id: $eid})--(b {engagement_id: $eid}) RETURN id(a) AS a_id, id(b) AS b_id LIMIT $lim",
        eid=engagement_id,
        lim=edge_limit,
    )
    edge_count = 0
    async for record in edge_result:
        a_id: int = record["a_id"]
        b_id: int = record["b_id"]
        uf._ensure(a_id)
        uf._ensure(b_id)
        uf.union(a_id, b_id)
        edge_count += 1

    if edge_count >= edge_limit:
        logger.warning(
            "_count_components hit the %d-edge LIMIT for engagement %s; "
            "component counts may be approximate for large graphs.",
            edge_limit,
            engagement_id,
        )

    # Collect orphan nodes (they will not appear in edge results).
    orphan_result = await neo4j_session.run(
        "MATCH (n {engagement_id: $eid}) WHERE NOT (n)--() RETURN id(n) AS nid",
        eid=engagement_id,
    )
    async for record in orphan_result:
        uf._ensure(record["nid"])

    components = list(uf.components())
    if not components:
        return 0, 0

    largest = max(len(members) for _, members in components)
    return len(components), largest


async def _zero_snapshot(engagement_id: str, duration_ms: float) -> GraphHealthSnapshot:
    """Return a fully-zeroed snapshot for when the driver is unavailable."""
    return GraphHealthSnapshot(
        engagement_id=uuid.UUID(engagement_id),
        node_count=0,
        relationship_count=0,
        orphan_node_count=0,
        connected_components=0,
        largest_component_size=0,
        avg_degree=0.0,
        invalid_label_count=0,
        invalid_rel_type_count=0,
        missing_required_props=0,
        nodes_by_label={},
        relationships_by_type={},
        entity_types_present={},
        entity_types_missing={},
        avg_confidence=0.0,
        low_confidence_count=0,
        analysis_duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_graph_health(
    neo4j_driver: AsyncDriver | None,
    session: AsyncSession,
    engagement_id: str,
) -> GraphHealthSnapshot:
    """Run health queries against the knowledge graph and persist a snapshot.

    All Neo4j queries are scoped to ``engagement_id``.  If ``neo4j_driver``
    is ``None`` a zeroed snapshot is stored and returned immediately.

    Args:
        neo4j_driver: Async Neo4j driver.  May be ``None`` in test / offline
            environments.
        session: SQLAlchemy async session.  The caller is responsible for
            committing.
        engagement_id: Engagement UUID string used to scope all Cypher
            queries.

    Returns:
        The persisted :class:`GraphHealthSnapshot` (not yet committed).
    """
    t_start = time.perf_counter()

    if neo4j_driver is None:
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        snapshot = await _zero_snapshot(engagement_id, duration_ms)
        session.add(snapshot)
        return snapshot

    valid_labels = get_valid_node_labels()
    valid_rel_types = get_valid_relationship_types() | _ALWAYS_VALID_REL_TYPES
    entity_type_to_label = get_entity_type_to_label()  # e.g. {"activity": "Activity", ...}

    async with neo4j_driver.session() as neo4j_session:
        # 1. Node count
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid}) RETURN count(n) AS cnt",
            eid=engagement_id,
        )
        _rec = await res.single()
        node_count: int = _rec["cnt"] if _rec is not None else 0

        # 2. Relationship count (divide by 2 — each edge appears twice in
        #    undirected MATCH)
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid})-[r]-() RETURN count(r) / 2 AS cnt",
            eid=engagement_id,
        )
        _rec = await res.single()
        relationship_count: int = _rec["cnt"] if _rec is not None else 0

        # 3. Orphan nodes
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid}) WHERE NOT (n)--() RETURN count(n) AS cnt",
            eid=engagement_id,
        )
        _rec = await res.single()
        orphan_node_count: int = _rec["cnt"] if _rec is not None else 0

        # 4. Connected components via union-find (includes orphan collection)
        connected_components, largest_component_size = await _count_components(neo4j_session, engagement_id)

        # 5. Nodes by label
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid}) RETURN labels(n) AS lbls, count(n) AS cnt",
            eid=engagement_id,
        )
        nodes_by_label: dict[str, int] = {}
        invalid_label_count = 0
        async for record in res:
            for lbl in record["lbls"]:
                nodes_by_label[lbl] = nodes_by_label.get(lbl, 0) + record["cnt"]
                if lbl not in valid_labels:
                    invalid_label_count += 1

        # 6. Relationships by type
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid})-[r]->() RETURN type(r) AS rtype, count(r) AS cnt",
            eid=engagement_id,
        )
        relationships_by_type: dict[str, int] = {}
        invalid_rel_type_count = 0
        async for record in res:
            rtype: str = record["rtype"]
            relationships_by_type[rtype] = record["cnt"]
            if rtype not in valid_rel_types:
                invalid_rel_type_count += 1

        # 7. Average degree
        avg_degree: float = (relationship_count * 2) / node_count if node_count > 0 else 0.0

        # 8. Missing required properties (name or confidence NULL)
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid}) WHERE n.name IS NULL OR n.confidence IS NULL RETURN count(n) AS cnt",
            eid=engagement_id,
        )
        _rec = await res.single()
        missing_required_props: int = _rec["cnt"] if _rec is not None else 0

        # 9. Entity types present / missing
        #    entity_type_to_label maps e.g. "activity" -> "Activity"
        #    A type is "present" if its Neo4j label appears in nodes_by_label.
        entity_types_present: dict[str, int] = {}
        entity_types_missing: dict[str, int] = {}
        for entity_type, label in entity_type_to_label.items():
            count = nodes_by_label.get(label, 0)
            if count > 0:
                entity_types_present[entity_type] = count
            else:
                entity_types_missing[entity_type] = 0

        # 10. Confidence stats
        res = await neo4j_session.run(
            "MATCH (n {engagement_id: $eid}) WHERE n.confidence IS NOT NULL "
            "RETURN avg(n.confidence) AS avg_conf, "
            "sum(CASE WHEN n.confidence < 0.5 THEN 1 ELSE 0 END) AS low_conf",
            eid=engagement_id,
        )
        conf_record = await res.single()
        avg_confidence: float = (
            conf_record["avg_conf"] if conf_record is not None and conf_record["avg_conf"] is not None else 0.0
        )
        low_confidence_count: int = (
            conf_record["low_conf"] if conf_record is not None and conf_record["low_conf"] is not None else 0
        )

    duration_ms = (time.perf_counter() - t_start) * 1000.0

    snapshot = GraphHealthSnapshot(
        engagement_id=uuid.UUID(engagement_id),
        node_count=node_count,
        relationship_count=relationship_count,
        orphan_node_count=orphan_node_count,
        connected_components=connected_components,
        largest_component_size=largest_component_size,
        avg_degree=avg_degree,
        invalid_label_count=invalid_label_count,
        invalid_rel_type_count=invalid_rel_type_count,
        missing_required_props=missing_required_props,
        nodes_by_label=nodes_by_label,
        relationships_by_type=relationships_by_type,
        entity_types_present=entity_types_present,
        entity_types_missing=entity_types_missing,
        avg_confidence=avg_confidence,
        low_confidence_count=low_confidence_count,
        analysis_duration_ms=duration_ms,
    )
    session.add(snapshot)
    return snapshot


async def get_latest_snapshot(
    session: AsyncSession,
    engagement_id: str,
) -> GraphHealthSnapshot | None:
    """Return the most recent health snapshot for an engagement.

    Args:
        session: SQLAlchemy async session.
        engagement_id: Engagement UUID string.

    Returns:
        The latest :class:`GraphHealthSnapshot`, or ``None`` if none exist.
    """
    stmt = (
        select(GraphHealthSnapshot)
        .where(GraphHealthSnapshot.engagement_id == uuid.UUID(engagement_id))
        .order_by(desc(GraphHealthSnapshot.created_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_snapshot_trends(
    session: AsyncSession,
    engagement_id: str,
    limit: int = 30,
) -> list[GraphHealthSnapshot]:
    """Return a time-ordered series of health snapshots for an engagement.

    Args:
        session: SQLAlchemy async session.
        engagement_id: Engagement UUID string.
        limit: Maximum number of snapshots to return (newest first).

    Returns:
        List of :class:`GraphHealthSnapshot` ordered by ``created_at`` desc.
    """
    stmt = (
        select(GraphHealthSnapshot)
        .where(GraphHealthSnapshot.engagement_id == uuid.UUID(engagement_id))
        .order_by(desc(GraphHealthSnapshot.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
