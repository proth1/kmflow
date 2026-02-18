"""Embedding service for semantic similarity search.

MVP implementation uses TF-IDF vectorization as a lightweight fallback
that requires no GPU or external model downloads. Embeddings are stored
in the pgvector column on EvidenceFragment.

The service provides:
- Embedding generation for text fragments
- Top-k similarity search
- Hybrid retrieval combining graph traversal with vector similarity
"""

from __future__ import annotations

import hashlib
import logging
import struct
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Target embedding dimension (matches EvidenceFragment.embedding Vector(768))
EMBEDDING_DIMENSION = 768


def _hash_based_embedding(text_input: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic embedding using content hashing.

    This is a simple MVP fallback that creates a pseudo-embedding by
    hashing overlapping n-grams of the input text. Not suitable for
    real semantic similarity but provides a consistent vector
    representation for testing and development.

    Args:
        text_input: Text to generate an embedding for.
        dimension: Target embedding dimension.

    Returns:
        List of floats representing the embedding vector.
    """
    if not text_input or not text_input.strip():
        return [0.0] * dimension

    # Normalize text
    normalized = text_input.lower().strip()

    # Generate hash-based features from overlapping character n-grams
    embedding = [0.0] * dimension
    ngram_sizes = [3, 4, 5]

    for ngram_size in ngram_sizes:
        for i in range(len(normalized) - ngram_size + 1):
            ngram = normalized[i : i + ngram_size]
            # Hash the n-gram to get a deterministic index and value
            h = hashlib.md5(ngram.encode(), usedforsecurity=False).digest()
            # Use first 4 bytes for index, next 4 for value
            idx = struct.unpack("<I", h[:4])[0] % dimension
            val = struct.unpack("<f", h[4:8])[0]
            # Clamp the value to a reasonable range
            val = max(-1.0, min(1.0, val / 1e10))
            embedding[idx] += val

    # L2 normalize
    norm = sum(v * v for v in embedding) ** 0.5
    if norm > 0:
        embedding = [v / norm for v in embedding]

    return embedding


class EmbeddingService:
    """Service for generating and searching text embeddings.

    Uses hash-based embeddings as the MVP fallback. Can be extended
    to use TF-IDF, sentence-transformers, or OpenAI embeddings.
    """

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        """Initialize the embedding service.

        Args:
            dimension: Target embedding vector dimension.
        """
        self._dimension = dimension
        self._tfidf_fitted = False
        self._tfidf_vectorizer: Any = None

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self._dimension

    def generate_embedding(self, text_input: str) -> list[float]:
        """Generate an embedding vector for a text string.

        Args:
            text_input: The text to embed.

        Returns:
            List of floats with length equal to self.dimension.
        """
        return _hash_based_embedding(text_input, self._dimension)

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        return [self.generate_embedding(t) for t in texts]

    async def store_embedding(
        self,
        session: AsyncSession,
        fragment_id: str,
        embedding: list[float],
    ) -> None:
        """Store an embedding vector for a fragment in pgvector.

        Args:
            session: Async database session.
            fragment_id: UUID of the evidence fragment.
            embedding: Embedding vector to store.
        """
        # Convert to pgvector format string: [0.1, 0.2, ...]
        vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
        query = text("UPDATE evidence_fragments SET embedding = :embedding WHERE id = :fragment_id")
        await session.execute(
            query,
            {"embedding": vector_str, "fragment_id": fragment_id},
        )

    async def search_similar(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        engagement_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Find the top-k most similar fragments using pgvector cosine distance.

        Args:
            session: Async database session.
            query_embedding: The query embedding vector.
            engagement_id: Optional engagement ID to scope the search.
            top_k: Number of results to return.

        Returns:
            List of dicts with fragment_id, content, similarity_score.
        """
        vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        if engagement_id:
            query = text("""
                SELECT ef.id, ef.content, ef.evidence_id,
                       1 - (ef.embedding <=> :query_vec::vector) AS similarity
                FROM evidence_fragments ef
                JOIN evidence_items ei ON ef.evidence_id = ei.id
                WHERE ei.engagement_id = :engagement_id
                  AND ef.embedding IS NOT NULL
                ORDER BY ef.embedding <=> :query_vec::vector
                LIMIT :top_k
            """)
            params = {
                "query_vec": vector_str,
                "engagement_id": engagement_id,
                "top_k": top_k,
            }
        else:
            query = text("""
                SELECT ef.id, ef.content, ef.evidence_id,
                       1 - (ef.embedding <=> :query_vec::vector) AS similarity
                FROM evidence_fragments ef
                WHERE ef.embedding IS NOT NULL
                ORDER BY ef.embedding <=> :query_vec::vector
                LIMIT :top_k
            """)
            params = {"query_vec": vector_str, "top_k": top_k}

        result = await session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "fragment_id": str(row[0]),
                "content": row[1],
                "evidence_id": str(row[2]),
                "similarity_score": float(row[3]) if row[3] is not None else 0.0,
            }
            for row in rows
        ]

    async def search_by_text(
        self,
        session: AsyncSession,
        query_text: str,
        engagement_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for similar fragments given a text query.

        Convenience method that generates the query embedding and
        then performs similarity search.

        Args:
            session: Async database session.
            query_text: The text to search for.
            engagement_id: Optional engagement ID to scope the search.
            top_k: Number of results to return.

        Returns:
            List of similarity search results.
        """
        query_embedding = self.generate_embedding(query_text)
        return await self.search_similar(
            session,
            query_embedding,
            engagement_id=engagement_id,
            top_k=top_k,
        )


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec_a: First vector.
        vec_b: Second vector.

    Returns:
        Cosine similarity score between -1.0 and 1.0.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimensions must match: {len(vec_a)} != {len(vec_b)}")

    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot / (norm_a * norm_b))
