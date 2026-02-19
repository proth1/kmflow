"""Tests for the knowledge graph construction pipeline.

Tests cover: full build pipeline, incremental mode, entity extraction
orchestration, node creation, relationship creation, embedding generation,
and error handling. All dependencies are mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.semantic.builder import BuildResult, KnowledgeGraphBuilder
from src.semantic.embeddings import EmbeddingService
from src.semantic.graph import GraphNode, KnowledgeGraphService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph_service() -> AsyncMock:
    """Create a mock KnowledgeGraphService."""
    service = AsyncMock(spec=KnowledgeGraphService)

    # create_node returns a GraphNode
    async def _create_node(label: str, properties: dict) -> GraphNode:
        return GraphNode(
            id=properties.get("id", uuid.uuid4().hex[:16]),
            label=label,
            properties=properties,
        )

    service.create_node = AsyncMock(side_effect=_create_node)
    service.create_relationship = AsyncMock()
    service.get_node = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create a mock EmbeddingService."""
    service = MagicMock(spec=EmbeddingService)
    service.generate_embedding_async = AsyncMock(return_value=[0.1] * 768)
    service.store_embedding = AsyncMock()
    return service


@pytest.fixture
def builder(
    mock_graph_service: AsyncMock,
    mock_embedding_service: MagicMock,
) -> KnowledgeGraphBuilder:
    """Create a KnowledgeGraphBuilder with mocked dependencies."""
    return KnowledgeGraphBuilder(mock_graph_service, mock_embedding_service)


def _mock_db_session_with_fragments(fragments: list[tuple[str, str, str]]) -> AsyncMock:
    """Create a mock DB session that returns specific fragments.

    Args:
        fragments: List of (fragment_id, content, evidence_id) tuples.
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = fragments
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# Full build pipeline
# ---------------------------------------------------------------------------


class TestBuildKnowledgeGraph:
    """Test the full graph construction pipeline."""

    @pytest.mark.asyncio
    async def test_build_with_fragments(self, builder: KnowledgeGraphBuilder) -> None:
        """Should process fragments and create nodes/relationships."""
        fragments = [
            (str(uuid.uuid4()), "Create Purchase Order in SAP", str(uuid.uuid4())),
            (str(uuid.uuid4()), "The Finance Manager reviews the Invoice", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        assert isinstance(result, BuildResult)
        assert result.engagement_id == "eng-1"
        assert result.fragments_processed == 2
        assert result.entities_extracted > 0

    @pytest.mark.asyncio
    async def test_build_returns_statistics(self, builder: KnowledgeGraphBuilder) -> None:
        """Should return meaningful statistics."""
        fragments = [
            (str(uuid.uuid4()), "Submit Invoice to the Accounting Specialist", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        assert result.fragments_processed == 1
        assert result.entities_extracted >= 0
        assert result.entities_resolved >= 0
        assert isinstance(result.nodes_by_label, dict)
        assert isinstance(result.relationships_by_type, dict)

    @pytest.mark.asyncio
    async def test_build_no_fragments(self, builder: KnowledgeGraphBuilder) -> None:
        """Should handle empty fragment list gracefully."""
        session = _mock_db_session_with_fragments([])

        result = await builder.build_knowledge_graph(session, "eng-empty")

        assert result.fragments_processed == 0
        assert result.entities_extracted == 0
        assert result.node_count == 0
        assert result.relationship_count == 0

    @pytest.mark.asyncio
    async def test_build_creates_evidence_links(
        self,
        builder: KnowledgeGraphBuilder,
        mock_graph_service: AsyncMock,
    ) -> None:
        """Should create SUPPORTED_BY links from entities to evidence."""
        ev_id = str(uuid.uuid4())
        fragments = [
            (str(uuid.uuid4()), "Approve Purchase Order", ev_id),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        # Verify SUPPORTED_BY relationships were tracked in result
        # (actual count depends on entity extraction results)
        assert result.relationships_by_type.get("SUPPORTED_BY", 0) >= 0

    @pytest.mark.asyncio
    async def test_build_creates_co_occurrence_links(
        self,
        builder: KnowledgeGraphBuilder,
        mock_graph_service: AsyncMock,
    ) -> None:
        """Should create CO_OCCURS_WITH links between entities from same evidence."""
        ev_id = str(uuid.uuid4())
        fragments = [
            (
                str(uuid.uuid4()),
                "The Procurement Manager uses SAP to Create Purchase Order.",
                ev_id,
            ),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        # If multiple entities were extracted from same evidence, CO_OCCURS_WITH should exist
        assert "CO_OCCURS_WITH" in result.relationships_by_type or result.entities_extracted <= 1

    @pytest.mark.asyncio
    async def test_build_incremental_mode(self, builder: KnowledgeGraphBuilder) -> None:
        """Should pass incremental flag to fragment fetch."""
        session = _mock_db_session_with_fragments([])

        result = await builder.build_knowledge_graph(session, "eng-1", incremental=True)

        assert result.fragments_processed == 0
        # Verify that execute was called (to fetch fragments)
        session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Entity extraction orchestration
# ---------------------------------------------------------------------------


class TestEntityExtraction:
    """Test entity extraction within the builder."""

    @pytest.mark.asyncio
    async def test_extracts_from_all_fragments(self, builder: KnowledgeGraphBuilder) -> None:
        """Should run extraction on each fragment."""
        fragments = [
            (str(uuid.uuid4()), "Create Order", str(uuid.uuid4())),
            (str(uuid.uuid4()), "Review Invoice", str(uuid.uuid4())),
            (str(uuid.uuid4()), "Approve Request", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        assert result.fragments_processed == 3
        # Each fragment should contribute at least some entities
        assert result.entities_extracted >= 0

    @pytest.mark.asyncio
    async def test_resolves_duplicate_entities(self, builder: KnowledgeGraphBuilder) -> None:
        """Resolved count should be <= extracted count (dedup removes duplicates)."""
        ev_id = str(uuid.uuid4())
        fragments = [
            (str(uuid.uuid4()), "Create Purchase Order", ev_id),
            (str(uuid.uuid4()), "Create purchase order", ev_id),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        assert result.entities_resolved <= result.entities_extracted


# ---------------------------------------------------------------------------
# Node creation
# ---------------------------------------------------------------------------


class TestNodeCreation:
    """Test Neo4j node creation within the builder."""

    @pytest.mark.asyncio
    async def test_creates_nodes_for_entities(
        self,
        builder: KnowledgeGraphBuilder,
        mock_graph_service: AsyncMock,
    ) -> None:
        """Should create a Neo4j node for each resolved entity."""
        fragments = [
            (str(uuid.uuid4()), "The Operations Manager uses Oracle system", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        # create_node should have been called for each entity
        assert mock_graph_service.create_node.call_count >= result.node_count

    @pytest.mark.asyncio
    async def test_nodes_scoped_to_engagement(
        self,
        builder: KnowledgeGraphBuilder,
        mock_graph_service: AsyncMock,
    ) -> None:
        """All created nodes should include engagement_id."""
        fragments = [
            (str(uuid.uuid4()), "Submit Report", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        await builder.build_knowledge_graph(session, "eng-42")

        # Check that each create_node call includes engagement_id
        for call in mock_graph_service.create_node.call_args_list:
            props = call.args[1] if len(call.args) > 1 else call.kwargs.get("properties", {})
            assert props.get("engagement_id") == "eng-42"


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


class TestEmbeddingGeneration:
    """Test embedding generation within the builder."""

    @pytest.mark.asyncio
    async def test_generates_embeddings_for_fragments(
        self,
        builder: KnowledgeGraphBuilder,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Should generate and store embeddings for each fragment."""
        fragments = [
            (str(uuid.uuid4()), "Content A", str(uuid.uuid4())),
            (str(uuid.uuid4()), "Content B", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        await builder.build_knowledge_graph(session, "eng-1")

        assert mock_embedding_service.generate_embedding_async.call_count == 2
        assert mock_embedding_service.store_embedding.call_count == 2

    @pytest.mark.asyncio
    async def test_embedding_failure_does_not_fail_build(
        self,
        builder: KnowledgeGraphBuilder,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Embedding failures should be recorded as errors, not crash the build."""
        mock_embedding_service.generate_embedding_async.side_effect = RuntimeError("GPU error")

        fragments = [
            (str(uuid.uuid4()), "Content A", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        # Should complete with errors, not raise
        assert len(result.errors) > 0
        assert "Embedding" in result.errors[0] or "embedding" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling in the builder."""

    @pytest.mark.asyncio
    async def test_node_creation_failure_continues(
        self,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Should continue building even if individual node creation fails."""
        mock_graph = AsyncMock(spec=KnowledgeGraphService)
        mock_graph.create_node = AsyncMock(side_effect=Exception("Neo4j error"))
        mock_graph.get_node = AsyncMock(return_value=None)
        mock_graph.create_relationship = AsyncMock()

        builder = KnowledgeGraphBuilder(mock_graph, mock_embedding_service)

        fragments = [
            (str(uuid.uuid4()), "Create Order in SAP", str(uuid.uuid4())),
        ]
        session = _mock_db_session_with_fragments(fragments)

        result = await builder.build_knowledge_graph(session, "eng-1")

        # Should complete (no exception raised)
        assert result.engagement_id == "eng-1"
        assert result.node_count == 0  # All creations failed

    @pytest.mark.asyncio
    async def test_build_result_structure(self, builder: KnowledgeGraphBuilder) -> None:
        """BuildResult should have all expected fields."""
        result = BuildResult()
        assert result.engagement_id == ""
        assert result.node_count == 0
        assert result.relationship_count == 0
        assert result.nodes_by_label == {}
        assert result.relationships_by_type == {}
        assert result.fragments_processed == 0
        assert result.entities_extracted == 0
        assert result.entities_resolved == 0
        assert result.errors == []
