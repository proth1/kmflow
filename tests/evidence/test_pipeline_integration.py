"""Tests for intelligence pipeline integration in evidence processing."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import EvidenceFragment
from src.evidence.pipeline import (
    build_fragment_graph,
    extract_fragment_entities,
    generate_fragment_embeddings,
    run_intelligence_pipeline,
    run_semantic_bridges,
)


def _make_fragment(content: str, evidence_id: str | None = None) -> EvidenceFragment:
    """Create a mock EvidenceFragment with content."""
    frag = MagicMock(spec=EvidenceFragment)
    frag.id = uuid.uuid4()
    frag.content = content
    frag.evidence_id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    frag.metadata_json = None
    return frag


class TestExtractFragmentEntities:
    """Tests for entity extraction from fragments."""

    @pytest.mark.asyncio
    async def test_extracts_entities_from_fragments(self) -> None:
        """Should extract entities and store as fragment metadata."""
        frag = _make_fragment("The Procurement Manager uses SAP to Process Purchase Orders and Review Invoices")
        results = await extract_fragment_entities([frag], "eng-1")

        assert len(results) == 1
        assert results[0]["entity_count"] > 0

        # Metadata should be updated with entities
        meta = json.loads(frag.metadata_json)
        assert "entities" in meta
        assert meta["entity_count"] > 0

    @pytest.mark.asyncio
    async def test_empty_fragment_skipped(self) -> None:
        """Fragments with no content should be skipped."""
        frag = _make_fragment("")
        frag.content = ""
        results = await extract_fragment_entities([frag], "eng-1")
        assert all(r["entity_count"] == 0 for r in results)

    @pytest.mark.asyncio
    async def test_multiple_fragments(self) -> None:
        """Should process multiple fragments."""
        frags = [
            _make_fragment("Review Invoice in SAP system"),
            _make_fragment("Approve Purchase Order"),
        ]
        results = await extract_fragment_entities(frags, "eng-1")
        assert len(results) == 2


class TestBuildFragmentGraph:
    """Tests for knowledge graph building from fragments."""

    @pytest.mark.asyncio
    async def test_no_driver_returns_empty(self) -> None:
        """Without Neo4j driver, should return zeros."""
        frag = _make_fragment("Review Invoice")
        result = await build_fragment_graph([frag], "eng-1", neo4j_driver=None)
        assert result["node_count"] == 0
        assert result["relationship_count"] == 0

    @pytest.mark.asyncio
    async def test_builds_nodes_from_entity_metadata(self) -> None:
        """Should create graph nodes from fragment entity metadata."""
        frag = _make_fragment("Review Invoice in SAP")
        # Pre-populate entity metadata
        frag.metadata_json = json.dumps(
            {
                "entities": [
                    {"id": "e1", "type": "activity", "name": "Review Invoice", "confidence": 0.7},
                    {"id": "e2", "type": "system", "name": "SAP", "confidence": 0.9},
                ],
                "entity_count": 2,
            }
        )

        mock_driver = AsyncMock()
        mock_graph_service = AsyncMock()
        mock_graph_service.create_node = AsyncMock(side_effect=lambda label, props: MagicMock(id=props["id"]))
        mock_graph_service.create_relationship = AsyncMock()

        with patch("src.semantic.graph.KnowledgeGraphService", return_value=mock_graph_service):
            result = await build_fragment_graph([frag], "eng-1", neo4j_driver=mock_driver)

        assert result["node_count"] == 2
        assert mock_graph_service.create_node.call_count == 2


class TestGenerateFragmentEmbeddings:
    """Tests for fragment embedding generation."""

    @pytest.mark.asyncio
    async def test_empty_fragments(self) -> None:
        """Empty list should return 0."""
        session = AsyncMock()
        result = await generate_fragment_embeddings(session, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_generates_and_stores_embeddings(self) -> None:
        """Should generate embeddings and call store."""
        frag = _make_fragment("Process invoices and purchase orders")
        session = AsyncMock()

        with (
            patch("src.rag.embeddings.EmbeddingService") as mock_rag,
            patch("src.semantic.embeddings.EmbeddingService") as mock_semantic,
        ):
            mock_rag_instance = MagicMock()
            mock_rag_instance.generate_embeddings_async = AsyncMock(return_value=[[0.1] * 768])
            mock_rag.return_value = mock_rag_instance

            mock_sem_instance = MagicMock()
            mock_sem_instance.store_embedding = AsyncMock()
            mock_semantic.return_value = mock_sem_instance

            result = await generate_fragment_embeddings(session, [frag])

        assert result == 1
        mock_sem_instance.store_embedding.assert_called_once()


class TestRunSemanticBridges:
    """Tests for semantic bridge orchestration."""

    @pytest.mark.asyncio
    async def test_no_driver_returns_empty(self) -> None:
        """Without Neo4j driver, should skip."""
        result = await run_semantic_bridges("eng-1", neo4j_driver=None)
        assert result["relationships_created"] == 0

    @pytest.mark.asyncio
    async def test_runs_all_bridges(self) -> None:
        """Should run all 4 bridges."""
        mock_driver = AsyncMock()
        mock_bridge_result = MagicMock()
        mock_bridge_result.relationships_created = 2
        mock_bridge_result.errors = []

        with (
            patch("src.semantic.graph.KnowledgeGraphService"),
            patch("src.semantic.bridges.process_evidence.ProcessEvidenceBridge") as mock_pe,
            patch("src.semantic.bridges.evidence_policy.EvidencePolicyBridge") as mock_ep,
            patch("src.semantic.bridges.process_tom.ProcessTOMBridge") as mock_pt,
            patch("src.semantic.bridges.communication_deviation.CommunicationDeviationBridge") as mock_cd,
        ):
            for mock_cls in [mock_pe, mock_ep, mock_pt, mock_cd]:
                instance = AsyncMock()
                instance.run = AsyncMock(return_value=mock_bridge_result)
                mock_cls.return_value = instance

            result = await run_semantic_bridges("eng-1", neo4j_driver=mock_driver)

        # 4 bridges * 2 relationships each = 8
        assert result["relationships_created"] == 8
        assert len(result["errors"]) == 0


class TestRunIntelligencePipeline:
    """Tests for the full intelligence pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_empty_fragments_returns_zeros(self) -> None:
        """Empty fragment list should return all zeros."""
        session = AsyncMock()
        result = await run_intelligence_pipeline(session, [], "eng-1")
        assert result["entities_extracted"] == 0
        assert result["graph_nodes"] == 0
        assert result["embeddings_stored"] == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_runs_all_steps(self) -> None:
        """Should run extraction, graph, embeddings, and bridges."""
        frag = _make_fragment("The Procurement Manager uses SAP to Process Purchase Orders")
        session = AsyncMock()

        with (
            patch("src.evidence.pipeline.extract_fragment_entities") as mock_extract,
            patch("src.evidence.pipeline.build_fragment_graph") as mock_graph,
            patch("src.evidence.pipeline.generate_fragment_embeddings") as mock_embed,
            patch("src.evidence.pipeline.run_semantic_bridges") as mock_bridges,
        ):
            mock_extract.return_value = [{"fragment_id": "f1", "entity_count": 3, "entities": []}]
            mock_graph.return_value = {"node_count": 3, "relationship_count": 2, "errors": []}
            mock_embed.return_value = 1
            mock_bridges.return_value = {"relationships_created": 5, "errors": []}

            result = await run_intelligence_pipeline(session, [frag], "eng-1")

        assert result["entities_extracted"] == 3
        assert result["graph_nodes"] == 3
        assert result["embeddings_stored"] == 1
        assert result["bridge_relationships"] == 5
        mock_extract.assert_called_once()
        mock_graph.assert_called_once()
        mock_embed.assert_called_once()
        mock_bridges.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_handles_step_failure_gracefully(self) -> None:
        """Individual step failures should not crash the pipeline."""
        frag = _make_fragment("Test content")
        session = AsyncMock()

        with (
            patch("src.evidence.pipeline.extract_fragment_entities", side_effect=RuntimeError("boom")),
            patch("src.evidence.pipeline.build_fragment_graph") as mock_graph,
            patch("src.evidence.pipeline.generate_fragment_embeddings") as mock_embed,
            patch("src.evidence.pipeline.run_semantic_bridges") as mock_bridges,
        ):
            mock_graph.return_value = {"node_count": 0, "relationship_count": 0, "errors": []}
            mock_embed.return_value = 0
            mock_bridges.return_value = {"relationships_created": 0, "errors": []}

            result = await run_intelligence_pipeline(session, [frag], "eng-1")

        # Entity extraction failed but others should still run
        assert "Entity extraction: boom" in result["errors"]
        mock_graph.assert_called_once()
        mock_embed.assert_called_once()
