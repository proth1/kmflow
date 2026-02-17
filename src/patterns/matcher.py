"""Embedding-based pattern matching for the pattern library.

Uses vector similarity to find relevant patterns from the library
based on a query description or process context.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def compute_similarity(
    embedding_a: list[float],
    embedding_b: list[float],
) -> float:
    """Compute cosine similarity between two embeddings."""
    if len(embedding_a) != len(embedding_b):
        return 0.0
    if not embedding_a:
        return 0.0

    dot = sum(a * b for a, b in zip(embedding_a, embedding_b))
    mag_a = sum(a * a for a in embedding_a) ** 0.5
    mag_b = sum(b * b for b in embedding_b) ** 0.5

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def rank_patterns(
    query_embedding: list[float],
    patterns: list[dict[str, Any]],
    top_k: int = 10,
    min_score: float = 0.5,
) -> list[dict[str, Any]]:
    """Rank patterns by similarity to a query embedding.

    Args:
        query_embedding: The query vector.
        patterns: List of pattern dicts with 'embedding' field.
        top_k: Maximum number of results to return.
        min_score: Minimum similarity score threshold.

    Returns:
        Ranked list of patterns with similarity scores.
    """
    scored: list[tuple[float, dict[str, Any]]] = []

    for pattern in patterns:
        pattern_embedding = pattern.get("embedding")
        if not pattern_embedding:
            continue
        score = compute_similarity(query_embedding, pattern_embedding)
        if score >= min_score:
            scored.append((score, pattern))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[dict[str, Any]] = []
    for score, pattern in scored[:top_k]:
        result = dict(pattern)
        result["similarity_score"] = round(score, 4)
        results.append(result)

    return results


def find_applicable_patterns(
    industry: str,
    categories: list[str],
    patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find patterns matching industry and category criteria.

    Args:
        industry: Target industry to match.
        categories: Target pattern categories.
        patterns: All available patterns.

    Returns:
        Filtered patterns matching criteria.
    """
    results: list[dict[str, Any]] = []
    for pattern in patterns:
        industry_match = (
            not pattern.get("industry")
            or pattern["industry"].lower() == industry.lower()
        )
        category_match = (
            not categories
            or pattern.get("category", "") in categories
        )
        if industry_match and category_match:
            results.append(pattern)
    return results
