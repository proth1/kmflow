"""Hybrid retrieval engine for RAG copilot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
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
        use_reranking: bool = True,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7,
    ) -> list[RetrievalResult]:
        """Retrieve relevant context using hybrid search.

        Args:
            query: The user's query string.
            session: Database session for pgvector queries.
            engagement_id: Engagement scope.
            top_k: Number of results to return.
            use_reranking: Whether to apply cross-encoder reranking.
            use_mmr: Whether to apply MMR diversity filtering.
            mmr_lambda: MMR trade-off parameter (1.0 = pure relevance, 0.0 = pure diversity).
        """
        results: list[RetrievalResult] = []

        # 1. Semantic search via pgvector — over-fetch for reranking/MMR
        fetch_k = top_k * 3 if (use_reranking or use_mmr) else top_k
        semantic_results = await self._semantic_search(query, session, engagement_id, top_k=fetch_k)
        results.extend(semantic_results)

        # 2. Graph expansion via Neo4j (if available)
        if self.neo4j_driver:
            graph_results = await self._graph_expand(query, engagement_id, top_k=min(5, top_k))
            results.extend(graph_results)

        # 3. Deduplicate
        seen: set[tuple[str, str]] = set()
        unique_results: list[RetrievalResult] = []
        for r in sorted(results, key=lambda x: x.similarity_score, reverse=True):
            key = (r.source_id, r.source_type)
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        # 4. Cross-encoder reranking (if available)
        if use_reranking and unique_results:
            unique_results = await self._rerank(query, unique_results)

        # 5. MMR diversity filtering
        if use_mmr and len(unique_results) > top_k:
            unique_results = self._apply_mmr(query, unique_results, top_k=top_k, lambda_param=mmr_lambda)

        return unique_results[:top_k]

    async def _rerank(
        self,
        query: str,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Re-score results using a cross-encoder model for better precision.

        Falls back gracefully if sentence-transformers cross-encoder is not available.
        """
        try:
            from sentence_transformers import CrossEncoder

            # Lazy-load the cross-encoder model
            if not hasattr(self, "_cross_encoder"):
                self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-12-v2")

            pairs = [[query, r.content] for r in results]

            import asyncio

            scores = await asyncio.to_thread(self._cross_encoder.predict, pairs)

            # Update scores and re-sort
            for result, score in zip(results, scores, strict=True):
                # Normalize cross-encoder score to [0, 1] range
                normalized = 1.0 / (1.0 + np.exp(-float(score)))
                result.similarity_score = normalized

            results.sort(key=lambda x: x.similarity_score, reverse=True)
        except (ImportError, OSError):
            logger.debug("Cross-encoder not available, skipping reranking")

        return results

    def _apply_mmr(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int = 10,
        lambda_param: float = 0.7,
    ) -> list[RetrievalResult]:
        """Apply Maximal Marginal Relevance to diversify results.

        Avoids returning multiple chunks from the same document section
        by penalizing results similar to already-selected ones.
        """
        if len(results) <= top_k:
            return results

        selected: list[RetrievalResult] = []
        candidates = list(results)

        # Select first result (highest score)
        selected.append(candidates.pop(0))

        while len(selected) < top_k and candidates:
            best_score = -1.0
            best_idx = 0

            for i, candidate in enumerate(candidates):
                # Relevance score
                relevance = candidate.similarity_score

                # Max similarity to any already-selected result (content overlap)
                max_sim = 0.0
                for sel in selected:
                    # Use source_id-based similarity: same evidence_id = high similarity
                    cand_eid = candidate.metadata.get("evidence_id", "")
                    sel_eid = sel.metadata.get("evidence_id", "")
                    if cand_eid and sel_eid and cand_eid == sel_eid:
                        max_sim = max(max_sim, 0.8)
                    # Content-based similarity via Jaccard on word sets
                    cand_words = set(candidate.content.lower().split()[:50])
                    sel_words = set(sel.content.lower().split()[:50])
                    if cand_words and sel_words:
                        jaccard = len(cand_words & sel_words) / len(cand_words | sel_words)
                        max_sim = max(max_sim, jaccard)

                # MMR score: balance relevance and diversity
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(candidates.pop(best_idx))

        return selected

    async def _semantic_search(
        self,
        query: str,
        session: AsyncSession,
        engagement_id: str,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Search evidence fragments using pgvector cosine similarity."""
        query_embedding = await self.embedding_service.embed_text_async(query)

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
        """Expand context using Neo4j graph relationships with query-term matching.

        Extracts key terms from the query, matches against graph node names,
        and scores results by relevance instead of returning arbitrary nodes
        with a flat score.
        """
        if not self.neo4j_driver:
            return []

        # Extract meaningful query terms (3+ chars, skip stopwords)
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "for",
            "and",
            "nor",
            "but",
            "or",
            "yet",
            "so",
            "in",
            "on",
            "at",
            "to",
            "of",
            "by",
            "with",
            "from",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "not",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "what",
            "which",
            "who",
            "whom",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
        }
        query_terms = [w.lower() for w in query.split() if len(w) >= 3 and w.lower() not in stopwords]

        if not query_terms:
            return []

        try:
            async with self.neo4j_driver.session() as neo4j_session:
                # Use CONTAINS matching against query terms for relevance
                # Fetch more candidates than needed, then score and rank
                result = await neo4j_session.run(
                    """
                    MATCH (n)-[r]-(m)
                    WHERE n.engagement_id = $engagement_id
                      AND m.engagement_id = $engagement_id
                      AND n.name IS NOT NULL
                    WITH DISTINCT n, labels(n)[0] as label, elementId(n) as node_id
                    RETURN n.name as name, n.description as description,
                           label, node_id
                    LIMIT $fetch_limit
                    """,
                    engagement_id=engagement_id,
                    fetch_limit=top_k * 10,  # Over-fetch for scoring
                )
                records = [record async for record in result]

                # Score each node by query term overlap
                scored_results: list[tuple[float, dict[str, Any]]] = []
                for r in records:
                    name = r.get("name", "")
                    if not name:
                        continue

                    name_lower = name.lower()
                    desc = (r.get("description") or "").lower()

                    # Count matching terms — name matches weighted higher
                    name_matches = sum(1 for t in query_terms if t in name_lower)
                    desc_matches = sum(1 for t in query_terms if t in desc)

                    if name_matches == 0 and desc_matches == 0:
                        continue

                    # Score: name matches are worth more than description matches
                    score = min(0.95, 0.4 + (name_matches * 0.2) + (desc_matches * 0.05))

                    scored_results.append((score, r))

                # Sort by score descending, take top_k
                scored_results.sort(key=lambda x: x[0], reverse=True)

                return [
                    RetrievalResult(
                        content=f"{r['label']}: {r['name']} - {r.get('description', '')}",
                        source_id=str(r["node_id"]),
                        source_type="graph_node",
                        similarity_score=score,
                        metadata={"label": r["label"]},
                    )
                    for score, r in scored_results[:top_k]
                ]
        except (ConnectionError, RuntimeError) as e:
            logger.warning("Graph expansion failed: %s", e)
            return []
