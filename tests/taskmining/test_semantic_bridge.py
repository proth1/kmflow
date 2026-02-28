"""Tests for task mining semantic bridge (Story #227)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.semantic.graph import GraphNode, GraphRelationship
from src.taskmining.semantic_bridge import (
    _cosine_similarity,
    run_semantic_bridge,
)


def _make_node(node_id: str, label: str, name: str) -> GraphNode:
    return GraphNode(id=node_id, label=label, properties={"name": name})


@pytest.fixture
def mock_graph_service():
    service = AsyncMock()
    service.find_nodes = AsyncMock(return_value=[])
    service.create_relationship = AsyncMock(
        return_value=GraphRelationship(
            id="r1",
            from_id="a",
            to_id="b",
            relationship_type="SUPPORTS",
            properties={},
        )
    )
    return service


@pytest.fixture
def mock_embedding_service():
    service = AsyncMock()
    return service


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0


class TestSupportsRelationships:
    @pytest.mark.asyncio
    async def test_confirmed_link_above_threshold(self, mock_graph_service, mock_embedding_service):
        ua = _make_node("ua-1", "UserAction", "Edited customer record in Salesforce")
        act = _make_node("act-1", "Activity", "Update Customer Data")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],  # UserActions
                [act],  # Activities
                [],  # Applications
                [],  # Systems
            ]
        )
        # Embeddings with high similarity (0.95)
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],  # UA embeddings
                [[0.95, 0.31, 0.0]],  # Activity embeddings (cos sim ≈ 0.95)
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_confirmed == 1
        assert result.supports_suggested == 0
        mock_graph_service.create_relationship.assert_called_once()
        call_kwargs = mock_graph_service.create_relationship.call_args
        assert call_kwargs.kwargs["relationship_type"] == "SUPPORTS"
        assert call_kwargs.kwargs["properties"]["link_type"] == "confirmed"

    @pytest.mark.asyncio
    async def test_suggested_link_in_ambiguous_range(self, mock_graph_service, mock_embedding_service):
        ua = _make_node("ua-1", "UserAction", "Browsed Salesforce")
        act = _make_node("act-1", "Activity", "Update Customer Data")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        # Embeddings with moderate similarity (0.62)
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],
                [[0.62, 0.78, 0.0]],  # cos sim ≈ 0.62
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_confirmed == 0
        assert result.supports_suggested == 1
        call_kwargs = mock_graph_service.create_relationship.call_args
        assert call_kwargs.kwargs["properties"]["link_type"] == "suggested"

    @pytest.mark.asyncio
    async def test_no_link_below_threshold(self, mock_graph_service, mock_embedding_service):
        ua = _make_node("ua-1", "UserAction", "Opened calculator")
        act = _make_node("act-1", "Activity", "Process loan application")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        # Very low similarity (0.1)
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],
                [[0.1, 0.99, 0.0]],
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_confirmed == 0
        assert result.supports_suggested == 0
        mock_graph_service.create_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_boundary_at_0_50(self, mock_graph_service, mock_embedding_service):
        """Similarity exactly at 0.50 should be 'suggested'."""
        ua = _make_node("ua-1", "UserAction", "Action X")
        act = _make_node("act-1", "Activity", "Activity Y")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        # Vector with exact 0.5 cosine similarity
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.5, 0.866]],  # cos sim = 0.5
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_suggested == 1
        assert result.supports_confirmed == 0

    @pytest.mark.asyncio
    async def test_boundary_at_0_49(self, mock_graph_service, mock_embedding_service):
        """Similarity at 0.49 should create no link."""
        ua = _make_node("ua-1", "UserAction", "Action X")
        act = _make_node("act-1", "Activity", "Activity Y")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.49, 0.8717]],  # cos sim ≈ 0.49
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_suggested == 0
        assert result.supports_confirmed == 0

    @pytest.mark.asyncio
    async def test_boundary_at_0_70(self, mock_graph_service, mock_embedding_service):
        """Similarity exactly at 0.70 should be 'confirmed'."""
        ua = _make_node("ua-1", "UserAction", "Action X")
        act = _make_node("act-1", "Activity", "Activity Y")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.7, 0.7141]],  # cos sim ≈ 0.70
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_confirmed == 1


class TestMapsToRelationships:
    @pytest.mark.asyncio
    async def test_app_maps_to_system(self, mock_graph_service, mock_embedding_service):
        app = _make_node("app-1", "Application", "Salesforce")
        sys = _make_node("sys-1", "System", "Salesforce CRM")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [],  # UserActions
                [],  # Activities
                [app],  # Applications
                [sys],  # Systems
            ]
        )
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],  # App embeddings
                [[0.95, 0.31, 0.0]],  # System embeddings (high similarity)
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.maps_to_created == 1
        call_kwargs = mock_graph_service.create_relationship.call_args
        assert call_kwargs.kwargs["relationship_type"] == "MAPS_TO"
        assert "similarity_score" in call_kwargs.kwargs["properties"]

    @pytest.mark.asyncio
    async def test_app_below_threshold_no_maps_to(self, mock_graph_service, mock_embedding_service):
        app = _make_node("app-1", "Application", "Calculator")
        sys = _make_node("sys-1", "System", "Salesforce CRM")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [],
                [],
                [app],
                [sys],
            ]
        )
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.1, 0.99]],
            ]
        )

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.maps_to_created == 0


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_nodes_returns_empty_result(self, mock_graph_service, mock_embedding_service):
        mock_graph_service.find_nodes = AsyncMock(return_value=[])

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert result.supports_confirmed == 0
        assert result.supports_suggested == 0
        assert result.maps_to_created == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_relationship_error_captured(self, mock_graph_service, mock_embedding_service):
        ua = _make_node("ua-1", "UserAction", "Action")
        act = _make_node("act-1", "Activity", "Activity")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [ua],
                [act],
                [],
                [],
            ]
        )
        mock_embedding_service.embed_texts_async = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.95, 0.31]],
            ]
        )
        mock_graph_service.create_relationship = AsyncMock(side_effect=RuntimeError("Neo4j unavailable"))

        result = await run_semantic_bridge(mock_graph_service, mock_embedding_service, "eng-1")

        assert len(result.errors) == 1
        assert "SUPPORTS link failed" in result.errors[0]
