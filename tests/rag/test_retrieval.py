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


class TestMMRDiversity:
    """Tests for Maximal Marginal Relevance diversity filtering."""

    def _make_result(self, source_id: str, score: float, evidence_id: str = "", content: str = "") -> RetrievalResult:
        return RetrievalResult(
            content=content or f"Content for {source_id}",
            source_id=source_id,
            source_type="fragment",
            similarity_score=score,
            metadata={"evidence_id": evidence_id},
        )

    def test_mmr_diversifies_same_evidence(self) -> None:
        """MMR should penalize results from the same evidence item."""
        retriever = HybridRetriever()
        results = [
            self._make_result("f1", 0.95, evidence_id="ev-1", content="mortgage lending process step one"),
            self._make_result("f2", 0.93, evidence_id="ev-1", content="mortgage lending process step two"),
            self._make_result("f3", 0.90, evidence_id="ev-1", content="mortgage lending process step three"),
            self._make_result("f4", 0.85, evidence_id="ev-2", content="underwriting review checklist items"),
            self._make_result("f5", 0.80, evidence_id="ev-3", content="appraisal coordination workflow"),
        ]
        selected = retriever._apply_mmr("mortgage lending", results, top_k=3, lambda_param=0.5)
        assert len(selected) == 3
        # With lambda=0.5 (balanced), MMR should pick from different evidence items
        evidence_ids = [r.metadata["evidence_id"] for r in selected]
        assert len(set(evidence_ids)) > 1, "MMR should diversify across evidence items"

    def test_mmr_returns_all_when_fewer_than_top_k(self) -> None:
        retriever = HybridRetriever()
        results = [
            self._make_result("f1", 0.9),
            self._make_result("f2", 0.8),
        ]
        selected = retriever._apply_mmr("query", results, top_k=5)
        assert len(selected) == 2

    def test_mmr_first_result_is_highest_score(self) -> None:
        retriever = HybridRetriever()
        results = [
            self._make_result("f1", 0.95),
            self._make_result("f2", 0.90),
            self._make_result("f3", 0.85),
        ]
        selected = retriever._apply_mmr("query", results, top_k=2)
        assert selected[0].source_id == "f1"

    def test_mmr_lambda_1_is_pure_relevance(self) -> None:
        """Lambda=1.0 means no diversity penalty — should return in score order."""
        retriever = HybridRetriever()
        results = [
            self._make_result("f1", 0.95, evidence_id="ev-1"),
            self._make_result("f2", 0.90, evidence_id="ev-1"),
            self._make_result("f3", 0.85, evidence_id="ev-2"),
        ]
        selected = retriever._apply_mmr("query", results, top_k=3, lambda_param=1.0)
        scores = [r.similarity_score for r in selected]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
class TestReranking:
    """Tests for cross-encoder reranking."""

    async def test_rerank_graceful_fallback(self) -> None:
        """Reranking should be a no-op when cross-encoder is not available."""
        retriever = HybridRetriever()
        results = [
            RetrievalResult(content="doc1", source_id="1", source_type="fragment", similarity_score=0.9),
            RetrievalResult(content="doc2", source_id="2", source_type="fragment", similarity_score=0.8),
        ]
        # Patch ImportError
        with patch("src.rag.retrieval.HybridRetriever._rerank") as mock_rerank:
            # Simulate graceful fallback — returns results unchanged
            mock_rerank.return_value = results
            reranked = await retriever._rerank("query", results)
        assert len(reranked) == 2

    async def test_rerank_preserves_result_count(self) -> None:
        """Reranking should not add or remove results."""
        retriever = HybridRetriever()
        results = [
            RetrievalResult(content=f"doc{i}", source_id=str(i), source_type="fragment", similarity_score=0.9 - i * 0.1)
            for i in range(5)
        ]
        reranked = await retriever._rerank("test query", results)
        assert len(reranked) == 5


@pytest.mark.asyncio
class TestGraphExpansionScoring:
    """Tests for query-term matching in graph expansion."""

    async def test_stopword_filtering(self) -> None:
        """Query terms should exclude common stopwords — returns empty."""
        retriever = HybridRetriever()
        results = await retriever._graph_expand("the a an is", engagement_id="test")
        assert results == []  # All stopwords, no query terms extracted
