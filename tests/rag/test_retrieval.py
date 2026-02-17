"""Tests for RAG retrieval engine (src/rag/retrieval.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.embeddings import EmbeddingService
from src.rag.retrieval import HybridRetriever, RetrievalResult


class TestEmbeddingService:
    def test_embed_text_returns_list(self) -> None:
        service = EmbeddingService()
        result = service.embed_text("test query")
        assert isinstance(result, list)
        assert len(result) == 768

    def test_embed_texts_returns_lists(self) -> None:
        service = EmbeddingService()
        results = service.embed_texts(["query 1", "query 2"])
        assert len(results) == 2
        assert all(len(r) == 768 for r in results)

    def test_custom_dimension_fallback(self) -> None:
        """When the model is unavailable, dimension parameter controls output size."""
        service = EmbeddingService(dimension=384)
        service._model = None  # Force fallback
        with patch.object(service, "_get_model", return_value=None):
            result = service.embed_text("test")
        assert len(result) == 384


@pytest.mark.asyncio
class TestHybridRetriever:
    async def test_retrieve_empty_results(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        retriever = HybridRetriever()
        results = await retriever.retrieve(
            query="test",
            session=session,
            engagement_id="test-id",
        )
        assert isinstance(results, list)

    async def test_retrieval_result_dataclass(self) -> None:
        result = RetrievalResult(
            content="Test content",
            source_id="test-id",
            source_type="fragment",
            similarity_score=0.95,
            metadata={"evidence_id": "ev-1"},
        )
        assert result.content == "Test content"
        assert result.similarity_score == 0.95
        assert result.metadata["evidence_id"] == "ev-1"
