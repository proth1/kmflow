"""Hybrid retrieval engine for RAG copilot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result with source metadata."""

    content: str
    source_id: str
    source_type: str  # "fragment", "graph_node"
    similarity_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """Combines pgvector semantic search with Neo4j graph expansion."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        neo4j_driver: Any = None,
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.neo4j_driver = neo4j_driver

    async def retrieve(
        self,
        query: str,
        session: AsyncSession,
        engagement_id: str,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Retrieve relevant context using hybrid search."""
        results: list[RetrievalResult] = []

        # 1. Semantic search via pgvector
        semantic_results = await self._semantic_search(query, session, engagement_id, top_k=top_k)
        results.extend(semantic_results)

        # 2. Graph expansion via Neo4j (if available)
        if self.neo4j_driver:
            graph_results = await self._graph_expand(query, engagement_id, top_k=min(5, top_k))
            results.extend(graph_results)

        # 3. Deduplicate and rerank by score
        seen = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.similarity_score, reverse=True):
            key = (r.source_id, r.source_type)
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        return unique_results[:top_k]

    async def _semantic_search(
        self,
        query: str,
        session: AsyncSession,
        engagement_id: str,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Search evidence fragments using pgvector cosine similarity."""
        query_embedding = self.embedding_service.embed_text(query)

        sql = text("""
            SELECT
                ef.id::text as fragment_id,
                ef.content,
                ef.evidence_id::text as evidence_id,
                1 - (ef.embedding <=> :query_embedding::vector) as similarity
            FROM evidence_fragments ef
            JOIN evidence_items ei ON ef.evidence_id = ei.id
            WHERE ei.engagement_id = :engagement_id::uuid
              AND ef.embedding IS NOT NULL
            ORDER BY ef.embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)

        result = await session.execute(
            sql,
            {
                "query_embedding": str(query_embedding),
                "engagement_id": engagement_id,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        return [
            RetrievalResult(
                content=row.content,
                source_id=row.fragment_id,
                source_type="fragment",
                similarity_score=float(row.similarity),
                metadata={"evidence_id": row.evidence_id},
            )
            for row in rows
        ]

    async def _graph_expand(
        self,
        query: str,
        engagement_id: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Expand context using Neo4j graph relationships."""
        if not self.neo4j_driver:
            return []

        try:
            async with self.neo4j_driver.session() as neo4j_session:
                result = await neo4j_session.run(
                    """
                    MATCH (n)-[r]-(m)
                    WHERE n.engagement_id = $engagement_id
                      AND m.engagement_id = $engagement_id
                    RETURN n.name as name, n.description as description,
                           labels(n)[0] as label, elementId(n) as node_id
                    LIMIT $top_k
                    """,
                    engagement_id=engagement_id,
                    top_k=top_k,
                )
                records = [record async for record in result]

                return [
                    RetrievalResult(
                        content=f"{r['label']}: {r['name']} - {r.get('description', '')}",
                        source_id=str(r["node_id"]),
                        source_type="graph_node",
                        similarity_score=0.5,  # Graph results get moderate score
                        metadata={"label": r["label"]},
                    )
                    for r in records
                    if r.get("name")
                ]
        except Exception as e:
            logger.warning("Graph expansion failed: %s", e)
            return []
