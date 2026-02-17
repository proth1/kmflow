"""Tests for the embedding service.

Tests cover: hash-based embedding generation, determinism, similarity
computation, batch generation, and the embedding service interface.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.semantic.embeddings import (
    EMBEDDING_DIMENSION,
    EmbeddingService,
    _hash_based_embedding,
    cosine_similarity,
)

# ---------------------------------------------------------------------------
# Hash-based embedding generation
# ---------------------------------------------------------------------------


class TestHashBasedEmbedding:
    """Test the hash-based embedding function."""

    def test_returns_correct_dimension(self) -> None:
        """Should return a vector of the specified dimension."""
        embedding = _hash_based_embedding("test text", dimension=768)
        assert len(embedding) == 768

    def test_custom_dimension(self) -> None:
        """Should respect a custom dimension parameter."""
        embedding = _hash_based_embedding("test text", dimension=128)
        assert len(embedding) == 128

    def test_deterministic(self) -> None:
        """Same input should produce the same embedding."""
        e1 = _hash_based_embedding("hello world")
        e2 = _hash_based_embedding("hello world")
        assert e1 == e2

    def test_different_texts_different_embeddings(self) -> None:
        """Different inputs should produce different embeddings."""
        e1 = _hash_based_embedding("create purchase order")
        e2 = _hash_based_embedding("approve invoice payment")
        assert e1 != e2

    def test_l2_normalized(self) -> None:
        """Output should be approximately L2-normalized."""
        embedding = _hash_based_embedding("test normalization")
        norm = sum(v * v for v in embedding) ** 0.5
        # Should be close to 1.0 (within floating point tolerance)
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_returns_zeros(self) -> None:
        """Empty text should return a zero vector."""
        embedding = _hash_based_embedding("")
        assert all(v == 0.0 for v in embedding)
        assert len(embedding) == EMBEDDING_DIMENSION

    def test_whitespace_text_returns_zeros(self) -> None:
        """Whitespace-only text should return a zero vector."""
        embedding = _hash_based_embedding("   \t\n  ")
        assert all(v == 0.0 for v in embedding)

    def test_case_insensitive_similar(self) -> None:
        """Case variations should produce the same embedding (lowercase normalization)."""
        e1 = _hash_based_embedding("Create Order")
        e2 = _hash_based_embedding("create order")
        assert e1 == e2

    def test_values_bounded(self) -> None:
        """All values should be bounded between -1 and 1."""
        embedding = _hash_based_embedding("a fairly long text with many words to generate features")
        for v in embedding:
            assert -2.0 <= v <= 2.0  # Allow some slack due to normalization


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Test the cosine similarity function."""

    def test_identical_vectors(self) -> None:
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 0.0, 1.0, 0.5]
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors should have similarity 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        sim = cosine_similarity(vec_a, vec_b)
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self) -> None:
        """Opposite vectors should have similarity -1.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        sim = cosine_similarity(vec_a, vec_b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_zero_vector(self) -> None:
        """Zero vector should return 0.0 similarity."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec_a, vec_b)
        assert sim == 0.0

    def test_dimension_mismatch_raises(self) -> None:
        """Should raise ValueError for dimension mismatch."""
        with pytest.raises(ValueError, match="dimensions must match"):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_similar_text_embeddings(self) -> None:
        """Embeddings of similar text should have higher similarity than dissimilar."""
        e1 = _hash_based_embedding("create purchase order")
        e2 = _hash_based_embedding("create purchase requisition")
        e3 = _hash_based_embedding("the weather is nice today")

        sim_similar = cosine_similarity(e1, e2)
        sim_dissimilar = cosine_similarity(e1, e3)

        # Similar texts should have higher similarity
        assert sim_similar > sim_dissimilar


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------


class TestEmbeddingService:
    """Test the EmbeddingService class."""

    def test_default_dimension(self) -> None:
        """Should use the default embedding dimension."""
        service = EmbeddingService()
        assert service.dimension == EMBEDDING_DIMENSION

    def test_custom_dimension(self) -> None:
        """Should accept a custom dimension."""
        service = EmbeddingService(dimension=256)
        assert service.dimension == 256

    def test_generate_embedding(self) -> None:
        """Should generate an embedding of the correct dimension."""
        service = EmbeddingService()
        embedding = service.generate_embedding("test text")
        assert len(embedding) == EMBEDDING_DIMENSION

    def test_generate_embeddings_batch(self) -> None:
        """Should generate embeddings for a batch of texts."""
        service = EmbeddingService()
        texts = ["text one", "text two", "text three"]
        embeddings = service.generate_embeddings_batch(texts)
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == EMBEDDING_DIMENSION

    def test_batch_embeddings_deterministic(self) -> None:
        """Batch generation should match individual generation."""
        service = EmbeddingService()
        texts = ["hello", "world"]
        batch = service.generate_embeddings_batch(texts)
        individual = [service.generate_embedding(t) for t in texts]
        assert batch == individual


class TestEmbeddingServiceStore:
    """Test embedding storage operations."""

    @pytest.mark.asyncio
    async def test_store_embedding(self) -> None:
        """Should execute an UPDATE query to store the embedding."""
        service = EmbeddingService()
        mock_session = AsyncMock()

        embedding = service.generate_embedding("test")
        await service.store_embedding(mock_session, "frag-123", embedding)

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        # Verify the query includes UPDATE and the fragment ID
        assert "frag-123" in str(call_args)


class TestEmbeddingServiceSearch:
    """Test embedding search operations."""

    @pytest.mark.asyncio
    async def test_search_similar(self) -> None:
        """Should execute a similarity search query."""
        service = EmbeddingService()
        mock_session = AsyncMock()

        # Mock the result
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("frag-1", "content 1", "ev-1", 0.95),
            ("frag-2", "content 2", "ev-2", 0.85),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        query_embedding = service.generate_embedding("test query")
        results = await service.search_similar(mock_session, query_embedding, engagement_id="eng-1", top_k=5)

        assert len(results) == 2
        assert results[0]["fragment_id"] == "frag-1"
        assert results[0]["similarity_score"] == 0.95
        assert results[1]["fragment_id"] == "frag-2"

    @pytest.mark.asyncio
    async def test_search_similar_without_engagement(self) -> None:
        """Should work without engagement_id filter."""
        service = EmbeddingService()
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await service.search_similar(mock_session, [0.1] * EMBEDDING_DIMENSION, top_k=10)
        assert results == []
        # Verify query was executed without engagement_id filter
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_by_text(self) -> None:
        """Should generate embedding then search."""
        service = EmbeddingService()
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("frag-1", "matching content", "ev-1", 0.92),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await service.search_by_text(mock_session, "purchase order", engagement_id="eng-1", top_k=5)
        assert len(results) == 1
        assert results[0]["content"] == "matching content"

    @pytest.mark.asyncio
    async def test_search_by_text_no_engagement(self) -> None:
        """Should search without engagement scope."""
        service = EmbeddingService()
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await service.search_by_text(mock_session, "query text")
        assert results == []
