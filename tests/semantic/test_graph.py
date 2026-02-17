"""Tests for the knowledge graph service.

Tests cover: node CRUD, relationship CRUD, traversal, subgraph retrieval,
stats, validation, and error handling. All tests use a mock Neo4j driver.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.semantic.graph import (
    VALID_NODE_LABELS,
    VALID_RELATIONSHIP_TYPES,
    GraphNode,
    GraphRelationship,
    GraphStats,
    KnowledgeGraphService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_driver() -> MagicMock:
    """Create a mock Neo4j driver with a session that returns configurable results."""
    driver = MagicMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=[])

    mock_session.run = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    driver.session = MagicMock(return_value=mock_session)
    return driver


@pytest.fixture
def mock_driver() -> MagicMock:
    """Provide a mock Neo4j driver."""
    return _make_mock_driver()


@pytest.fixture
def graph_service(mock_driver: MagicMock) -> KnowledgeGraphService:
    """Provide a KnowledgeGraphService with a mock driver."""
    return KnowledgeGraphService(mock_driver)


def _set_query_result(mock_driver: MagicMock, data: list[dict]) -> None:
    """Configure the mock driver session to return specific data."""
    mock_result = AsyncMock()
    mock_result.data = AsyncMock(return_value=data)
    mock_session = mock_driver.session.return_value
    mock_session.run = AsyncMock(return_value=mock_result)


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


class TestCreateNode:
    """Test node creation."""

    @pytest.mark.asyncio
    async def test_create_node_returns_graph_node(self, graph_service: KnowledgeGraphService) -> None:
        """Should return a GraphNode with the correct label and properties."""
        node = await graph_service.create_node(
            "Activity",
            {"name": "Create Order", "engagement_id": "eng-1"},
        )
        assert isinstance(node, GraphNode)
        assert node.label == "Activity"
        assert node.properties["name"] == "Create Order"
        assert node.properties["engagement_id"] == "eng-1"

    @pytest.mark.asyncio
    async def test_create_node_generates_id(self, graph_service: KnowledgeGraphService) -> None:
        """Should generate an ID if not provided."""
        node = await graph_service.create_node(
            "Role",
            {"name": "Manager", "engagement_id": "eng-1"},
        )
        assert node.id is not None
        assert len(node.id) > 0

    @pytest.mark.asyncio
    async def test_create_node_uses_provided_id(self, graph_service: KnowledgeGraphService) -> None:
        """Should use the provided ID if given."""
        node = await graph_service.create_node(
            "System",
            {"id": "custom-id", "name": "SAP", "engagement_id": "eng-1"},
        )
        assert node.id == "custom-id"

    @pytest.mark.asyncio
    async def test_create_node_invalid_label(self, graph_service: KnowledgeGraphService) -> None:
        """Should raise ValueError for invalid labels."""
        with pytest.raises(ValueError, match="Invalid node label"):
            await graph_service.create_node(
                "InvalidLabel",
                {"name": "Test", "engagement_id": "eng-1"},
            )

    @pytest.mark.asyncio
    async def test_create_node_missing_name(self, graph_service: KnowledgeGraphService) -> None:
        """Should raise ValueError when name is missing."""
        with pytest.raises(ValueError, match="must include 'name'"):
            await graph_service.create_node("Activity", {"engagement_id": "eng-1"})

    @pytest.mark.asyncio
    async def test_create_node_missing_engagement_id(self, graph_service: KnowledgeGraphService) -> None:
        """Should raise ValueError when engagement_id is missing."""
        with pytest.raises(ValueError, match="must include 'engagement_id'"):
            await graph_service.create_node("Activity", {"name": "Test"})

    @pytest.mark.asyncio
    async def test_create_node_executes_cypher(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should execute a CREATE Cypher query."""
        await graph_service.create_node(
            "Evidence",
            {"name": "Test Doc", "engagement_id": "eng-1"},
        )
        mock_session = mock_driver.session.return_value
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        assert "CREATE" in call_args[0][0]
        assert "Evidence" in call_args[0][0]


class TestGetNode:
    """Test node retrieval."""

    @pytest.mark.asyncio
    async def test_get_node_found(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return a GraphNode when found."""
        _set_query_result(mock_driver, [{"n": {"id": "node-1", "name": "Test"}, "labels": ["Activity"]}])
        node = await graph_service.get_node("node-1")
        assert node is not None
        assert node.id == "node-1"
        assert node.label == "Activity"
        assert node.properties["name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_node_not_found(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return None when node is not found."""
        _set_query_result(mock_driver, [])
        node = await graph_service.get_node("nonexistent")
        assert node is None


class TestFindNodes:
    """Test node querying with filters."""

    @pytest.mark.asyncio
    async def test_find_nodes_by_label(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should find nodes matching a label."""
        _set_query_result(
            mock_driver,
            [
                {"n": {"id": "n1", "name": "Order"}},
                {"n": {"id": "n2", "name": "Invoice"}},
            ],
        )
        nodes = await graph_service.find_nodes("Activity")
        assert len(nodes) == 2
        assert nodes[0].label == "Activity"

    @pytest.mark.asyncio
    async def test_find_nodes_with_filters(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should pass filters to the query."""
        _set_query_result(
            mock_driver,
            [
                {"n": {"id": "n1", "name": "Order", "engagement_id": "eng-1"}},
            ],
        )
        nodes = await graph_service.find_nodes("Activity", filters={"engagement_id": "eng-1"})
        assert len(nodes) == 1
        # Verify the query included WHERE clause
        mock_session = mock_driver.session.return_value
        query = mock_session.run.call_args[0][0]
        assert "WHERE" in query

    @pytest.mark.asyncio
    async def test_find_nodes_invalid_label(self, graph_service: KnowledgeGraphService) -> None:
        """Should raise ValueError for invalid labels."""
        with pytest.raises(ValueError, match="Invalid node label"):
            await graph_service.find_nodes("BadLabel")

    @pytest.mark.asyncio
    async def test_find_nodes_empty_result(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return empty list when no nodes match."""
        _set_query_result(mock_driver, [])
        nodes = await graph_service.find_nodes("Role")
        assert nodes == []


# ---------------------------------------------------------------------------
# Relationship operations
# ---------------------------------------------------------------------------


class TestCreateRelationship:
    """Test relationship creation."""

    @pytest.mark.asyncio
    async def test_create_relationship_returns_graph_rel(self, graph_service: KnowledgeGraphService) -> None:
        """Should return a GraphRelationship."""
        rel = await graph_service.create_relationship(
            from_id="node-1",
            to_id="node-2",
            relationship_type="SUPPORTED_BY",
            properties={"confidence": 0.9},
        )
        assert isinstance(rel, GraphRelationship)
        assert rel.from_id == "node-1"
        assert rel.to_id == "node-2"
        assert rel.relationship_type == "SUPPORTED_BY"
        assert rel.id is not None

    @pytest.mark.asyncio
    async def test_create_relationship_invalid_type(self, graph_service: KnowledgeGraphService) -> None:
        """Should raise ValueError for invalid relationship types."""
        with pytest.raises(ValueError, match="Invalid relationship type"):
            await graph_service.create_relationship(from_id="a", to_id="b", relationship_type="INVALID_TYPE")

    @pytest.mark.asyncio
    async def test_create_relationship_executes_cypher(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should execute a CREATE Cypher query with relationship type."""
        await graph_service.create_relationship(from_id="n1", to_id="n2", relationship_type="FOLLOWED_BY")
        mock_session = mock_driver.session.return_value
        query = mock_session.run.call_args[0][0]
        assert "FOLLOWED_BY" in query
        assert "CREATE" in query


class TestGetRelationships:
    """Test relationship retrieval."""

    @pytest.mark.asyncio
    async def test_get_relationships_outgoing(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should get outgoing relationships."""
        _set_query_result(
            mock_driver,
            [
                {
                    "r": {"id": "r1"},
                    "from_id": "n1",
                    "to_id": "n2",
                    "rel_type": "USES",
                }
            ],
        )
        rels = await graph_service.get_relationships("n1", direction="outgoing")
        assert len(rels) == 1
        assert rels[0].relationship_type == "USES"

    @pytest.mark.asyncio
    async def test_get_relationships_incoming(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should get incoming relationships."""
        _set_query_result(
            mock_driver,
            [
                {
                    "r": {"id": "r1"},
                    "from_id": "n2",
                    "to_id": "n1",
                    "rel_type": "OWNED_BY",
                }
            ],
        )
        rels = await graph_service.get_relationships("n1", direction="incoming")
        assert len(rels) == 1

    @pytest.mark.asyncio
    async def test_get_relationships_both_directions(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should get relationships in both directions."""
        _set_query_result(
            mock_driver,
            [
                {"r": {"id": "r1"}, "from_id": "n1", "to_id": "n2", "rel_type": "USES"},
                {"r": {"id": "r2"}, "from_id": "n3", "to_id": "n1", "rel_type": "OWNED_BY"},
            ],
        )
        rels = await graph_service.get_relationships("n1", direction="both")
        assert len(rels) == 2

    @pytest.mark.asyncio
    async def test_get_relationships_with_type_filter(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should filter by relationship type."""
        _set_query_result(mock_driver, [{"r": {"id": "r1"}, "from_id": "n1", "to_id": "n2", "rel_type": "USES"}])
        rels = await graph_service.get_relationships("n1", direction="outgoing", relationship_type="USES")
        assert len(rels) == 1
        mock_session = mock_driver.session.return_value
        query = mock_session.run.call_args[0][0]
        assert "USES" in query

    @pytest.mark.asyncio
    async def test_get_relationships_empty(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return empty list when no relationships found."""
        _set_query_result(mock_driver, [])
        rels = await graph_service.get_relationships("n1")
        assert rels == []


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------


class TestTraverse:
    """Test graph traversal."""

    @pytest.mark.asyncio
    async def test_traverse_returns_connected_nodes(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should return nodes connected within depth."""
        _set_query_result(
            mock_driver,
            [
                {"connected": {"id": "n2", "name": "Task B"}, "labels": ["Activity"]},
                {"connected": {"id": "n3", "name": "Manager"}, "labels": ["Role"]},
            ],
        )
        nodes = await graph_service.traverse("n1", depth=2)
        assert len(nodes) == 2
        assert nodes[0].id == "n2"

    @pytest.mark.asyncio
    async def test_traverse_with_relationship_filter(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should filter by relationship types."""
        _set_query_result(mock_driver, [{"connected": {"id": "n2"}, "labels": ["Activity"]}])
        await graph_service.traverse("n1", depth=1, relationship_types=["FOLLOWED_BY", "USES"])
        mock_session = mock_driver.session.return_value
        query = mock_session.run.call_args[0][0]
        assert "FOLLOWED_BY" in query
        assert "USES" in query

    @pytest.mark.asyncio
    async def test_traverse_zero_depth(self, graph_service: KnowledgeGraphService) -> None:
        """Should return empty list for zero depth."""
        nodes = await graph_service.traverse("n1", depth=0)
        assert nodes == []

    @pytest.mark.asyncio
    async def test_traverse_empty_result(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return empty list when no connected nodes."""
        _set_query_result(mock_driver, [])
        nodes = await graph_service.traverse("isolated-node", depth=3)
        assert nodes == []


# ---------------------------------------------------------------------------
# Engagement subgraph
# ---------------------------------------------------------------------------


class TestEngagementSubgraph:
    """Test engagement subgraph retrieval."""

    @pytest.mark.asyncio
    async def test_get_engagement_subgraph(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return nodes and relationships for an engagement."""
        # First call returns nodes, second returns relationships
        mock_session = mock_driver.session.return_value

        node_result = AsyncMock()
        node_result.data = AsyncMock(
            return_value=[
                {"n": {"id": "n1", "name": "Activity 1"}, "labels": ["Activity"]},
                {"n": {"id": "n2", "name": "Role 1"}, "labels": ["Role"]},
            ]
        )

        rel_result = AsyncMock()
        rel_result.data = AsyncMock(
            return_value=[
                {
                    "r": {"id": "r1"},
                    "from_id": "n1",
                    "to_id": "n2",
                    "rel_type": "OWNED_BY",
                }
            ]
        )

        mock_session.run = AsyncMock(side_effect=[node_result, rel_result])

        subgraph = await graph_service.get_engagement_subgraph("eng-1")
        assert len(subgraph["nodes"]) == 2
        assert len(subgraph["relationships"]) == 1
        assert subgraph["relationships"][0].relationship_type == "OWNED_BY"

    @pytest.mark.asyncio
    async def test_get_engagement_subgraph_empty(
        self, mock_driver: MagicMock, graph_service: KnowledgeGraphService
    ) -> None:
        """Should return empty lists for engagement with no graph."""
        mock_session = mock_driver.session.return_value

        empty_result = AsyncMock()
        empty_result.data = AsyncMock(return_value=[])
        mock_session.run = AsyncMock(return_value=empty_result)

        subgraph = await graph_service.get_engagement_subgraph("eng-empty")
        assert subgraph["nodes"] == []
        assert subgraph["relationships"] == []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestGetStats:
    """Test graph statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return correct counts by label and type."""
        mock_session = mock_driver.session.return_value

        node_stats = AsyncMock()
        node_stats.data = AsyncMock(
            return_value=[
                {"label": "Activity", "count": 5},
                {"label": "Role", "count": 3},
            ]
        )

        rel_stats = AsyncMock()
        rel_stats.data = AsyncMock(
            return_value=[
                {"rel_type": "SUPPORTED_BY", "count": 8},
                {"rel_type": "OWNED_BY", "count": 4},
            ]
        )

        mock_session.run = AsyncMock(side_effect=[node_stats, rel_stats])

        stats = await graph_service.get_stats("eng-1")
        assert isinstance(stats, GraphStats)
        assert stats.node_count == 8
        assert stats.relationship_count == 12
        assert stats.nodes_by_label == {"Activity": 5, "Role": 3}
        assert stats.relationships_by_type == {"SUPPORTED_BY": 8, "OWNED_BY": 4}

    @pytest.mark.asyncio
    async def test_get_stats_empty_graph(self, mock_driver: MagicMock, graph_service: KnowledgeGraphService) -> None:
        """Should return zero counts for empty graph."""
        mock_session = mock_driver.session.return_value
        empty = AsyncMock()
        empty.data = AsyncMock(return_value=[])
        mock_session.run = AsyncMock(return_value=empty)

        stats = await graph_service.get_stats("eng-empty")
        assert stats.node_count == 0
        assert stats.relationship_count == 0
        assert stats.nodes_by_label == {}
        assert stats.relationships_by_type == {}


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Test that graph constants are correctly defined."""

    def test_valid_node_labels(self) -> None:
        """Should include all expected node labels."""
        expected = {"Activity", "Decision", "Role", "System", "Evidence", "Document"}
        assert expected.issubset(VALID_NODE_LABELS)

    def test_valid_relationship_types(self) -> None:
        """Should include all PRD relationship types."""
        expected = {
            "SUPPORTED_BY",
            "GOVERNED_BY",
            "DEVIATES_FROM",
            "IMPLEMENTS",
            "CONTRADICTS",
            "MITIGATES",
            "REQUIRES",
            "FOLLOWED_BY",
            "OWNED_BY",
            "USES",
        }
        assert expected.issubset(VALID_RELATIONSHIP_TYPES)
