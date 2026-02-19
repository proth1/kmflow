"""Semantic embedding service for similarity search and storage.

Delegates embedding generation to the unified RAG embedding service
(src/rag/embeddings.py) while providing pgvector storage and search
functionality for evidence fragments.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.rag.embeddings import EMBEDDING_DIMENSION
from src.rag.embeddings import EmbeddingService as _RagEmbeddingService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating and searching text embeddings.

    Delegates embedding generation to the unified RAG embedding service.
    Provides pgvector storage and similarity search for evidence fragments.
    """

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        """Initialize the embedding service.

        Args:
            dimension: Target embedding vector dimension.
        """
        self._dimension = dimension
        self._rag_service = _RagEmbeddingService(dimension=dimension)

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self._dimension

    def generate_embedding(self, text_input: str) -> list[float]:
        """Generate an embedding vector for a text string.

        Delegates to the unified RAG embedding service.

        Args:
            text_input: The text to embed.

        Returns:
            List of floats with length equal to self.dimension.
        """
        return self._rag_service.embed_text(text_input)

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Delegates to the unified RAG embedding service.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        return self._rag_service.generate_embeddings(texts)

    async def generate_embedding_async(self, text_input: str) -> list[float]:
        """Generate an embedding vector for a text string (async).

        Delegates to the unified RAG embedding service.

        Args:
            text_input: The text to embed.

        Returns:
            List of floats with length equal to self.dimension.
        """
        return await self._rag_service.embed_text_async(text_input)

    async def generate_embeddings_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts (async).

        Delegates to the unified RAG embedding service.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        return await self._rag_service.generate_embeddings_async(texts)

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
        query_embedding = await self.generate_embedding_async(query_text)
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
