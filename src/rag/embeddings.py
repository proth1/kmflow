"""Embedding generation for RAG retrieval."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for RAG queries and document fragments."""

    def __init__(self, model_name: str = "all-mpnet-base-v2", dimension: int = 768):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed, using random embeddings")
                self._model = None
        return self._model

    def embed_text(self, text: str) -> list[float]:
        model = self._get_model()
        if model is None:
            return np.random.randn(self.dimension).tolist()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        if model is None:
            return [np.random.randn(self.dimension).tolist() for _ in texts]
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
