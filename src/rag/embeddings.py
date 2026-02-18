"""Unified embedding generation service.

This is the single source of truth for embedding generation across KMFlow.
Uses SentenceTransformer when available, falls back to random embeddings.
Both RAG retrieval and semantic search delegate to this service.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Default embedding dimension (matches pgvector column on EvidenceFragment)
EMBEDDING_DIMENSION = 768


class EmbeddingService:
    """Unified embedding service for RAG queries and document fragments.

    This is the canonical embedding generator. The semantic embeddings module
    delegates to this service for vector generation while keeping its own
    pgvector search functionality.
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2", dimension: int = EMBEDDING_DIMENSION):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed, using random embeddings")
                self._model = None
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text string."""
        model = self._get_model()
        if model is None:
            return np.random.randn(self.dimension).tolist()
        embedding = model.encode(text, normalize_embeddings=True)
        return list(embedding.tolist())

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (batch)."""
        model = self._get_model()
        if model is None:
            return [list(np.random.randn(self.dimension).tolist()) for _ in texts]
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [list(e) for e in embeddings.tolist()]

    def generate_embeddings(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Generate embeddings for a list of texts with batching.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to process per batch.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self.embed_texts(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings
