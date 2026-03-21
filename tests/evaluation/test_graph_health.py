"""Tests for graph health analysis in src.evaluation.graph_health.

The None-driver path is fully tested without any Neo4j connections.
The _UnionFind component-counting logic is tested directly.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.pipeline_quality import GraphHealthSnapshot
from src.evaluation.graph_health import (
    _UnionFind,
    analyze_graph_health,
)


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# _UnionFind unit tests
# ---------------------------------------------------------------------------


class TestUnionFind:
    def test_single_node_is_its_own_component(self) -> None:
        uf = _UnionFind()
        uf._ensure(1)
        components = list(uf.components())
        assert len(components) == 1
        root, members = components[0]
        assert members == [1]

    def test_two_connected_nodes_form_one_component(self) -> None:
        uf = _UnionFind()
        uf._ensure(1)
        uf._ensure(2)
        uf.union(1, 2)
        components = list(uf.components())
        assert len(components) == 1
        _, members = components[0]
        assert set(members) == {1, 2}

    def test_two_disconnected_nodes_form_two_components(self) -> None:
        uf = _UnionFind()
        uf._ensure(1)
        uf._ensure(2)
        components = list(uf.components())
        assert len(components) == 2

    def test_chain_of_nodes_forms_one_component(self) -> None:
        uf = _UnionFind()
        # 1-2-3-4
        for i in range(1, 5):
            uf._ensure(i)
        uf.union(1, 2)
        uf.union(2, 3)
        uf.union(3, 4)
        components = list(uf.components())
        assert len(components) == 1
        _, members = components[0]
        assert set(members) == {1, 2, 3, 4}

    def test_two_separate_clusters(self) -> None:
        uf = _UnionFind()
        # cluster A: 1-2
        uf._ensure(1)
        uf._ensure(2)
        uf.union(1, 2)
        # cluster B: 3-4
        uf._ensure(3)
        uf._ensure(4)
        uf.union(3, 4)
        components = list(uf.components())
        assert len(components) == 2
        sizes = sorted(len(m) for _, m in components)
        assert sizes == [2, 2]

    def test_find_with_path_compression(self) -> None:
        uf = _UnionFind()
        for i in range(1, 6):
            uf._ensure(i)
        # Chain: 1→2→3→4→5
        uf.union(1, 2)
        uf.union(2, 3)
        uf.union(3, 4)
        uf.union(4, 5)
        # All should have the same root after find
        root = uf.find(1)
        for i in range(2, 6):
            assert uf.find(i) == root

    def test_union_same_node_is_noop(self) -> None:
        uf = _UnionFind()
        uf._ensure(1)
        uf.union(1, 1)
        components = list(uf.components())
        assert len(components) == 1

    def test_empty_union_find_has_no_components(self) -> None:
        uf = _UnionFind()
        components = list(uf.components())
        assert components == []


# ---------------------------------------------------------------------------
# analyze_graph_health — None driver path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAnalyzeGraphHealthNoneDriver:
    async def test_none_driver_returns_zeroed_snapshot(self) -> None:
        session = _make_session()
        eid = str(uuid.uuid4())

        snapshot = await analyze_graph_health(
            neo4j_driver=None,
            session=session,
            engagement_id=eid,
        )

        assert isinstance(snapshot, GraphHealthSnapshot)
        assert snapshot.node_count == 0
        assert snapshot.relationship_count == 0
        assert snapshot.orphan_node_count == 0
        assert snapshot.connected_components == 0
        assert snapshot.largest_component_size == 0
        assert snapshot.avg_degree == 0.0
        assert snapshot.invalid_label_count == 0
        assert snapshot.invalid_rel_type_count == 0
        assert snapshot.missing_required_props == 0
        assert snapshot.nodes_by_label == {}
        assert snapshot.relationships_by_type == {}
        assert snapshot.entity_types_present == {}
        assert snapshot.entity_types_missing == {}
        assert snapshot.avg_confidence == 0.0
        assert snapshot.low_confidence_count == 0

    async def test_none_driver_adds_snapshot_to_session(self) -> None:
        session = _make_session()
        eid = str(uuid.uuid4())

        snapshot = await analyze_graph_health(
            neo4j_driver=None,
            session=session,
            engagement_id=eid,
        )

        session.add.assert_called_once_with(snapshot)

    async def test_none_driver_engagement_id_set_correctly(self) -> None:
        session = _make_session()
        eid = str(uuid.uuid4())

        snapshot = await analyze_graph_health(
            neo4j_driver=None,
            session=session,
            engagement_id=eid,
        )

        assert snapshot.engagement_id == uuid.UUID(eid)

    async def test_none_driver_analysis_duration_is_non_negative(self) -> None:
        session = _make_session()
        eid = str(uuid.uuid4())

        snapshot = await analyze_graph_health(
            neo4j_driver=None,
            session=session,
            engagement_id=eid,
        )

        assert snapshot.analysis_duration_ms >= 0.0
