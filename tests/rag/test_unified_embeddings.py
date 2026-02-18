"""Tests for the unified embedding service."""

from __future__ import annotations

from src.rag.embeddings import EMBEDDING_DIMENSION, EmbeddingService


class TestEmbeddingService:
    """Tests for the RAG embedding service."""

    def test_embed_text_returns_correct_dimension(self) -> None:
        """Embedding should have the expected dimensionality."""
        service = EmbeddingService()
        embedding = service.embed_text("hello world")
        assert len(embedding) == EMBEDDING_DIMENSION
        assert all(isinstance(v, float) for v in embedding)

    def test_embed_texts_batch(self) -> None:
        """Batch embedding should return one vector per text."""
        service = EmbeddingService()
        texts = ["hello", "world", "test"]
        embeddings = service.embed_texts(texts)
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == EMBEDDING_DIMENSION

    def test_generate_embeddings_batching(self) -> None:
        """generate_embeddings should handle batching correctly."""
        service = EmbeddingService()
        texts = [f"text {i}" for i in range(10)]
        embeddings = service.generate_embeddings(texts, batch_size=3)
        assert len(embeddings) == 10
        for emb in embeddings:
            assert len(emb) == EMBEDDING_DIMENSION

    def test_generate_embeddings_empty(self) -> None:
        """Empty input should return empty list."""
        service = EmbeddingService()
        embeddings = service.generate_embeddings([])
        assert embeddings == []

    def test_custom_dimension_stored(self) -> None:
        """Service should store custom dimension setting."""
        service = EmbeddingService(dimension=128)
        assert service.dimension == 128


class TestSemanticEmbeddingDelegation:
    """Tests that semantic embedding service delegates to RAG service."""

    def test_generate_embedding_delegates(self) -> None:
        """Semantic service should delegate generation to RAG service."""
        from src.semantic.embeddings import EmbeddingService as SemanticService

        service = SemanticService()
        embedding = service.generate_embedding("test text")
        assert len(embedding) == EMBEDDING_DIMENSION
        assert all(isinstance(v, float) for v in embedding)

    def test_generate_embeddings_batch_delegates(self) -> None:
        """Semantic batch should delegate to RAG service."""
        from src.semantic.embeddings import EmbeddingService as SemanticService

        service = SemanticService()
        embeddings = service.generate_embeddings_batch(["hello", "world"])
        assert len(embeddings) == 2
        for emb in embeddings:
            assert len(emb) == EMBEDDING_DIMENSION

    def test_dimension_property(self) -> None:
        """Dimension property should work."""
        from src.semantic.embeddings import EmbeddingService as SemanticService

        service = SemanticService(dimension=256)
        assert service.dimension == 256
