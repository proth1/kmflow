"""Standard information retrieval metrics for evaluating the RAG retrieval pipeline.

Provides pure metric functions (precision, recall, MRR, NDCG) and orchestration
helpers that run queries through HybridRetriever and persist GoldenEvalResult rows.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.pipeline_quality import GoldenEvalQuery, GoldenEvalResult
from src.rag.retrieval import HybridRetriever, RetrievalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure metric functions
# ---------------------------------------------------------------------------


def precision_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int) -> float:
    """Fraction of the top-k retrieved items that are relevant.

    Args:
        retrieved_ids: Ordered list of retrieved source IDs.
        expected_ids: Set of ground-truth relevant source IDs.
        k: Cutoff rank.

    Returns:
        Precision@k in [0.0, 1.0]. Returns 0.0 if k == 0.
    """
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in top_k if rid in expected_ids)
    return hits / k


def recall_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int) -> float:
    """Fraction of all relevant items that appear in the top-k results.

    Args:
        retrieved_ids: Ordered list of retrieved source IDs.
        expected_ids: Set of ground-truth relevant source IDs.
        k: Cutoff rank.

    Returns:
        Recall@k in [0.0, 1.0]. Returns 0.0 if expected_ids is empty or k == 0.
    """
    if not expected_ids or k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in top_k if rid in expected_ids)
    return hits / len(expected_ids)


def mean_reciprocal_rank(retrieved_ids: list[str], expected_ids: set[str]) -> float:
    """Reciprocal rank of the first relevant item in the retrieved list.

    Args:
        retrieved_ids: Ordered list of retrieved source IDs.
        expected_ids: Set of ground-truth relevant source IDs.

    Returns:
        MRR value in (0.0, 1.0], or 0.0 if no relevant item was retrieved.
    """
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in expected_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int) -> float:
    """Normalised Discounted Cumulative Gain at rank k.

    Relevance is binary: 1 if the retrieved ID is in expected_ids, else 0.
    Ideal DCG is computed assuming all relevant items are ranked first.

    Args:
        retrieved_ids: Ordered list of retrieved source IDs.
        expected_ids: Set of ground-truth relevant source IDs.
        k: Cutoff rank.

    Returns:
        NDCG@k in [0.0, 1.0]. Returns 0.0 if k == 0 or expected_ids is empty.
    """
    if k == 0 or not expected_ids:
        return 0.0

    top_k = retrieved_ids[:k]
    gains = np.array([1.0 if rid in expected_ids else 0.0 for rid in top_k])

    if gains.size == 0:
        return 0.0

    # Discount: 1/log2(rank+1), rank is 1-indexed
    positions = np.arange(1, gains.size + 1)
    discounts = 1.0 / np.log2(positions + 1)
    dcg: float = float(np.dot(gains, discounts))

    # Ideal DCG: place all relevant docs at the top
    n_ideal = min(len(expected_ids), k)
    ideal_gains = np.ones(n_ideal)
    ideal_positions = np.arange(1, n_ideal + 1)
    ideal_discounts = 1.0 / np.log2(ideal_positions + 1)
    idcg: float = float(np.dot(ideal_gains, ideal_discounts))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


async def evaluate_query(
    retriever: HybridRetriever,
    session: AsyncSession,
    query: GoldenEvalQuery,
    engagement_id: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Run a single golden query through the retriever and compute IR metrics.

    Args:
        retriever: Configured HybridRetriever instance.
        session: Async database session used for pgvector queries.
        query: The GoldenEvalQuery containing ground-truth information.
        engagement_id: Engagement scope string passed to the retriever.
        top_k: Number of results to retrieve.

    Returns:
        Dict with keys: retrieved_ids, retrieval_latency_ms,
        precision_at_5, precision_at_10, recall_at_5, recall_at_10,
        mrr, ndcg_at_10.
    """
    expected_ids: set[str] = set(query.expected_source_ids)

    t0 = time.perf_counter()
    results: list[RetrievalResult] = await retriever.retrieve(
        query.query,
        session,
        engagement_id,
        top_k=top_k,
    )
    latency_ms = (time.perf_counter() - t0) * 1000.0

    retrieved_ids = [r.source_id for r in results]

    return {
        "retrieved_ids": retrieved_ids,
        "retrieval_latency_ms": latency_ms,
        "precision_at_5": precision_at_k(retrieved_ids, expected_ids, k=5),
        "precision_at_10": precision_at_k(retrieved_ids, expected_ids, k=10),
        "recall_at_5": recall_at_k(retrieved_ids, expected_ids, k=5),
        "recall_at_10": recall_at_k(retrieved_ids, expected_ids, k=10),
        "mrr": mean_reciprocal_rank(retrieved_ids, expected_ids),
        "ndcg_at_10": ndcg_at_k(retrieved_ids, expected_ids, k=10),
    }


async def evaluate_dataset(
    retriever: HybridRetriever,
    session: AsyncSession,
    engagement_id: str,
    queries: list[GoldenEvalQuery],
) -> tuple[uuid.UUID, list[GoldenEvalResult]]:
    """Evaluate all queries in the dataset and persist results.

    All results share a single eval_run_id so they can be grouped and compared
    across runs. Each GoldenEvalResult row is added to the session but the
    caller is responsible for committing.

    Args:
        retriever: Configured HybridRetriever instance.
        session: Async database session.
        engagement_id: Engagement scope string passed to the retriever.
        queries: List of GoldenEvalQuery rows to evaluate.

    Returns:
        Tuple of (eval_run_id, list[GoldenEvalResult]).
    """
    eval_run_id = uuid.uuid4()
    db_engagement_id = uuid.UUID(engagement_id) if isinstance(engagement_id, str) else engagement_id
    results: list[GoldenEvalResult] = []

    for q in queries:
        try:
            metrics = await evaluate_query(retriever, session, q, engagement_id, top_k=10)
        except Exception:  # Intentionally broad: per-query errors must not abort the full evaluation run
            logger.exception("Failed to evaluate query %s", q.id)
            continue

        result = GoldenEvalResult(
            id=uuid.uuid4(),
            eval_run_id=eval_run_id,
            query_id=q.id,
            engagement_id=db_engagement_id,
            precision_at_5=metrics["precision_at_5"],
            precision_at_10=metrics["precision_at_10"],
            recall_at_5=metrics["recall_at_5"],
            recall_at_10=metrics["recall_at_10"],
            mrr=metrics["mrr"],
            ndcg_at_10=metrics["ndcg_at_10"],
            retrieved_source_ids=metrics["retrieved_ids"],
            retrieval_latency_ms=metrics["retrieval_latency_ms"],
            # LLM-judge fields are left null; populate via rag_evaluator if needed
            faithfulness_score=None,
            answer_relevance_score=None,
            hallucination_score=None,
            citation_accuracy_score=None,
            generated_answer=None,
            judge_reasoning=None,
            generation_latency_ms=None,
        )
        session.add(result)
        results.append(result)

    await session.flush()
    return eval_run_id, results
