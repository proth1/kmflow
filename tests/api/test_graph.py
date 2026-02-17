"""Tests for the knowledge graph API routes.

Tests cover: build endpoint, query endpoint, traverse endpoint,
search endpoint, stats endpoint, subgraph endpoint, and error handling.
All graph and database operations are mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.semantic.builder import BuildResult
from src.semantic.graph import GraphNode, GraphRelationship, GraphStats

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_graph_service(return_value=None):  # noqa: ANN001, ANN202
    """Create a mock graph service with configurable return values."""
    service = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# Build endpoint
# ---------------------------------------------------------------------------


class TestBuildGraph:
    """POST /api/v1/graph/build"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphBuilder")
    @patch("src.api.routes.graph.KnowledgeGraphService")
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_build_graph_success(
        self,
        mock_emb_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_builder_cls: MagicMock,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Should trigger graph build and return statistics."""
        engagement_id = str(uuid.uuid4())

        mock_builder = AsyncMock()
        mock_builder.build_knowledge_graph = AsyncMock(
            return_value=BuildResult(
                engagement_id=engagement_id,
                node_count=10,
                relationship_count=15,
                nodes_by_label={"Activity": 5, "Role": 3, "System": 2},
                relationships_by_type={"SUPPORTED_BY": 8, "CO_OCCURS_WITH": 7},
                fragments_processed=3,
                entities_extracted=12,
                entities_resolved=10,
            )
        )
        mock_builder_cls.return_value = mock_builder

        response = await client.post(
            "/api/v1/graph/build",
            json={"engagement_id": engagement_id},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["engagement_id"] == engagement_id
        assert data["node_count"] == 10
        assert data["relationship_count"] == 15
        assert data["fragments_processed"] == 3
        assert data["entities_extracted"] == 12
        assert data["entities_resolved"] == 10
        assert "Activity" in data["nodes_by_label"]

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphBuilder")
    @patch("src.api.routes.graph.KnowledgeGraphService")
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_build_graph_incremental(
        self,
        mock_emb_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_builder_cls: MagicMock,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Should support incremental build mode."""
        engagement_id = str(uuid.uuid4())

        mock_builder = AsyncMock()
        mock_builder.build_knowledge_graph = AsyncMock(return_value=BuildResult(engagement_id=engagement_id))
        mock_builder_cls.return_value = mock_builder

        response = await client.post(
            "/api/v1/graph/build",
            json={"engagement_id": engagement_id, "incremental": True},
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphBuilder")
    @patch("src.api.routes.graph.KnowledgeGraphService")
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_build_graph_failure(
        self,
        mock_emb_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_builder_cls: MagicMock,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Should return 500 on build failure."""
        mock_builder = AsyncMock()
        mock_builder.build_knowledge_graph = AsyncMock(side_effect=RuntimeError("Neo4j connection lost"))
        mock_builder_cls.return_value = mock_builder

        response = await client.post(
            "/api/v1/graph/build",
            json={"engagement_id": str(uuid.uuid4())},
        )
        assert response.status_code == 500
        assert "Graph build failed" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------


class TestExecuteQuery:
    """POST /api/v1/graph/query"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_query_success(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should execute a read-only Cypher query."""
        mock_service = AsyncMock()
        mock_service._run_query = AsyncMock(return_value=[{"name": "Test Activity"}])
        mock_graph_cls.return_value = mock_service

        response = await client.post(
            "/api/v1/graph/query",
            json={
                "query": "MATCH (n:Activity) RETURN n.name AS name LIMIT 10",
                "parameters": {},
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_rejects_write_operations(self, client: AsyncClient) -> None:
        """Should reject queries with write operations."""
        write_queries = [
            "CREATE (n:Activity {name: 'test'})",
            "MATCH (n) DELETE n",
            "MATCH (n) SET n.name = 'test'",
            "MATCH (n) DETACH DELETE n",
            "MATCH (n) REMOVE n.name",
            "MERGE (n:Activity {name: 'test'})",
            "DROP CONSTRAINT foo",
        ]
        for query in write_queries:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": query},
            )
            assert response.status_code == 400, f"Should reject: {query}"

    @pytest.mark.asyncio
    async def test_query_empty_body(self, client: AsyncClient) -> None:
        """Should reject empty query."""
        response = await client.post(
            "/api/v1/graph/query",
            json={"query": ""},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Traverse endpoint
# ---------------------------------------------------------------------------


class TestTraverseGraph:
    """GET /api/v1/graph/traverse/{node_id}"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_traverse_success(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return connected nodes."""
        mock_service = AsyncMock()
        mock_service.traverse = AsyncMock(
            return_value=[
                GraphNode(id="n2", label="Activity", properties={"name": "Task B"}),
                GraphNode(id="n3", label="Role", properties={"name": "Manager"}),
            ]
        )
        mock_graph_cls.return_value = mock_service

        response = await client.get("/api/v1/graph/traverse/n1?depth=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "n2"

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_traverse_with_relationship_types(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should pass relationship types filter."""
        mock_service = AsyncMock()
        mock_service.traverse = AsyncMock(return_value=[])
        mock_graph_cls.return_value = mock_service

        response = await client.get("/api/v1/graph/traverse/n1?relationship_types=FOLLOWED_BY,USES")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_traverse_invalid_depth(self, client: AsyncClient) -> None:
        """Should reject depth outside 1-5 range."""
        response = await client.get("/api/v1/graph/traverse/n1?depth=0")
        assert response.status_code == 400

        response = await client.get("/api/v1/graph/traverse/n1?depth=10")
        assert response.status_code == 400

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_traverse_empty_result(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return empty list for isolated nodes."""
        mock_service = AsyncMock()
        mock_service.traverse = AsyncMock(return_value=[])
        mock_graph_cls.return_value = mock_service

        response = await client.get("/api/v1/graph/traverse/isolated")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    """GET /api/v1/graph/search"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.EmbeddingService")
    async def test_search_success(
        self,
        mock_emb_cls: MagicMock,
        client: AsyncClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Should return search results."""
        mock_service = MagicMock()
        mock_service.search_by_text = AsyncMock(
            return_value=[
                {
                    "fragment_id": "frag-1",
                    "content": "Purchase order processing",
                    "evidence_id": "ev-1",
                    "similarity_score": 0.95,
                }
            ]
        )
        mock_emb_cls.return_value = mock_service

        response = await client.get("/api/v1/graph/search?query=purchase+order&top_k=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["similarity_score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_missing_query(self, client: AsyncClient) -> None:
        """Should reject missing query parameter."""
        response = await client.get("/api/v1/graph/search")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_invalid_top_k(self, client: AsyncClient) -> None:
        """Should reject invalid top_k values."""
        response = await client.get("/api/v1/graph/search?query=test&top_k=0")
        assert response.status_code == 400

        response = await client.get("/api/v1/graph/search?query=test&top_k=200")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------


class TestGraphStats:
    """GET /api/v1/graph/{engagement_id}/stats"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_get_stats(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return graph statistics."""
        mock_service = AsyncMock()
        mock_service.get_stats = AsyncMock(
            return_value=GraphStats(
                node_count=15,
                relationship_count=22,
                nodes_by_label={"Activity": 8, "Role": 4, "System": 3},
                relationships_by_type={"SUPPORTED_BY": 12, "USES": 10},
            )
        )
        mock_graph_cls.return_value = mock_service

        engagement_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/graph/{engagement_id}/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["node_count"] == 15
        assert data["relationship_count"] == 22
        assert data["nodes_by_label"]["Activity"] == 8

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_get_stats_empty_graph(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return zero counts for empty graph."""
        mock_service = AsyncMock()
        mock_service.get_stats = AsyncMock(return_value=GraphStats())
        mock_graph_cls.return_value = mock_service

        engagement_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/graph/{engagement_id}/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["node_count"] == 0


# ---------------------------------------------------------------------------
# Subgraph endpoint
# ---------------------------------------------------------------------------


class TestEngagementSubgraph:
    """GET /api/v1/graph/{engagement_id}/subgraph"""

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_get_subgraph(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return nodes and relationships."""
        mock_service = AsyncMock()
        mock_service.get_engagement_subgraph = AsyncMock(
            return_value={
                "nodes": [
                    GraphNode(id="n1", label="Activity", properties={"name": "Task A"}),
                    GraphNode(id="n2", label="Role", properties={"name": "Manager"}),
                ],
                "relationships": [
                    GraphRelationship(
                        id="r1",
                        from_id="n1",
                        to_id="n2",
                        relationship_type="OWNED_BY",
                        properties={},
                    )
                ],
            }
        )
        mock_graph_cls.return_value = mock_service

        engagement_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/graph/{engagement_id}/subgraph")
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 2
        assert len(data["relationships"]) == 1
        assert data["relationships"][0]["relationship_type"] == "OWNED_BY"

    @pytest.mark.asyncio
    @patch("src.api.routes.graph.KnowledgeGraphService")
    async def test_get_subgraph_empty(
        self,
        mock_graph_cls: MagicMock,
        client: AsyncClient,
        mock_neo4j_driver: MagicMock,
    ) -> None:
        """Should return empty lists for engagement with no graph."""
        mock_service = AsyncMock()
        mock_service.get_engagement_subgraph = AsyncMock(
            return_value={
                "nodes": [],
                "relationships": [],
            }
        )
        mock_graph_cls.return_value = mock_service

        engagement_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/graph/{engagement_id}/subgraph")
        assert response.status_code == 200
        data = response.json()
        assert data["nodes"] == []
        assert data["relationships"] == []
