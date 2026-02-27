"""Best Practice Gap Matcher.

Matches gap analysis results to relevant industry best practices
using TOM dimension alignment and optional embedding similarity ranking.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import BestPractice, GapAnalysisResult

logger = logging.getLogger(__name__)

_EMBEDDING_THRESHOLD = 0.5


class BestPracticeMatcher:
    """Matches TOM gaps to relevant industry best practices.

    Uses TOM dimension for primary filtering and optional embedding
    cosine similarity for relevance ranking within a dimension.
    """

    def __init__(self, embedding_service: Any | None = None) -> None:
        self._embedding_service = embedding_service

    async def match_gaps_to_practices(
        self,
        session: AsyncSession,
        engagement_id: str,
        tom_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Find best practices that match each gap by TOM dimension.

        Args:
            session: Database session.
            engagement_id: The engagement to query gaps for.
            tom_id: The TOM to query gaps for.

        Returns:
            Dict mapping gap_id (str) -> list of matched BestPractice dicts
            with score field added.
        """
        # Fetch gaps for this engagement+TOM
        gap_result = await session.execute(
            select(GapAnalysisResult)
            .where(GapAnalysisResult.engagement_id == engagement_id)
            .where(GapAnalysisResult.tom_id == tom_id)
        )
        gaps = list(gap_result.scalars().all())

        # Fetch all best practices
        bp_result = await session.execute(select(BestPractice))
        best_practices = list(bp_result.scalars().all())

        if not gaps or not best_practices:
            return {}

        matches: dict[str, list[dict[str, Any]]] = {}

        for gap in gaps:
            gap_id = str(gap.id)
            # Primary filter: same TOM dimension
            dimension_matches = [bp for bp in best_practices if bp.tom_dimension == gap.dimension]

            if not dimension_matches:
                matches[gap_id] = []
                continue

            if self._embedding_service is not None and gap.recommendation:
                scored = await self._rank_by_embedding(gap.recommendation, dimension_matches)
            else:
                # Assign a default score of 1.0 for dimension-matched practices
                scored = [self._bp_to_dict(bp, score=1.0) for bp in dimension_matches]

            matches[gap_id] = scored

        return matches

    async def _rank_by_embedding(
        self,
        query_text: str,
        practices: list[BestPractice],
    ) -> list[dict[str, Any]]:
        """Rank best practices by embedding similarity to gap recommendation."""
        descriptions = [bp.description for bp in practices]
        if self._embedding_service is None:
            return [self._bp_to_dict(bp, score=1.0) for bp in practices]
        try:
            query_emb = await self._embedding_service.embed_text_async(query_text)
            bp_embs = await self._embedding_service.embed_texts_async(descriptions)
        except (ConnectionError, RuntimeError, ValueError) as e:
            logger.warning("Embedding failed during BP ranking, using default scores: %s", e)
            return [self._bp_to_dict(bp, score=1.0) for bp in practices]

        scored = []
        for bp, emb in zip(practices, bp_embs, strict=True):
            score = float(np.dot(query_emb, emb))
            if score >= _EMBEDDING_THRESHOLD:
                scored.append(self._bp_to_dict(bp, score=score))

        # Sort by similarity descending
        scored.sort(key=lambda x: float(x["score"]), reverse=True)
        return scored

    def _bp_to_dict(self, bp: BestPractice, score: float) -> dict[str, Any]:
        """Convert a BestPractice ORM object to a serializable dict."""
        return {
            "id": str(bp.id),
            "domain": bp.domain,
            "industry": bp.industry,
            "description": bp.description,
            "source": bp.source,
            "tom_dimension": str(bp.tom_dimension),
            "score": round(score, 4),
        }


def _gap_id_str(gap_id: uuid.UUID) -> str:
    return str(gap_id)
