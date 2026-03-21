"""LLM-as-Judge evaluation for the RAG copilot pipeline.

Each dimension (faithfulness, answer relevance, hallucination, citation accuracy)
is evaluated independently. Results can be composed via ``evaluate_answer`` for
a single-call combined assessment.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.core.llm import LLMProvider
from src.evaluation.prompts import (
    ANSWER_RELEVANCE_PROMPT,
    FAITHFULNESS_PROMPT,
    HALLUCINATION_PROMPT,
    PROMPT_VERSION,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_judge_response(raw: str, dimension: str) -> dict[str, Any]:
    """Parse a JSON judge response from an LLM output string.

    Handles cases where the model wraps its JSON in markdown code fences.

    Args:
        raw: Raw string returned by the LLM.
        dimension: Name of the evaluation dimension (used in error logging).

    Returns:
        Dict with at minimum "score" and "reasoning" keys. On parse failure
        returns {"score": None, "reasoning": "<error description>"}.
    """
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```) and closing fence
        inner_lines = [line for line in lines[1:] if not line.strip().startswith("```")]
        text = "\n".join(inner_lines).strip()

    try:
        parsed = json.loads(text)
        if "score" not in parsed or "reasoning" not in parsed:
            return {
                "score": None,
                "reasoning": f"Judge response missing required keys for dimension '{dimension}': {text[:200]}",
            }
        score = parsed["score"]
        if score is not None:
            try:
                score = float(score)
                score = max(0.0, min(1.0, score))
            except (TypeError, ValueError):
                score = None
        parsed["score"] = score
        return parsed
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse judge JSON for dimension '%s': %s | raw=%s", dimension, exc, text[:300])
        return {
            "score": None,
            "reasoning": f"JSON parse error for dimension '{dimension}': {exc}",
        }


# ---------------------------------------------------------------------------
# Individual dimension evaluators
# ---------------------------------------------------------------------------


async def evaluate_faithfulness(
    llm: LLMProvider,
    context: str,
    answer: str,
) -> dict[str, Any]:
    """Judge whether every claim in the answer is supported by the context.

    Args:
        llm: LLM provider instance with an async ``generate`` method.
        context: Concatenated source passages used to generate the answer.
        answer: The generated answer text to evaluate.

    Returns:
        Dict with keys: score (float|None), reasoning (str), dimension (str),
        prompt_version (str). score=1.0 means fully faithful.
    """
    user_prompt = f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"
    try:
        raw = await llm.generate(user_prompt, system=FAITHFULNESS_PROMPT)
    except Exception as exc:  # Intentionally broad: LLM errors must return graceful null score, not propagate
        logger.exception("LLM call failed for faithfulness evaluation")
        return {
            "score": None,
            "reasoning": f"LLM call failed: {exc}",
            "dimension": "faithfulness",
            "prompt_version": PROMPT_VERSION,
        }

    result = _parse_judge_response(raw, "faithfulness")
    result["dimension"] = "faithfulness"
    result["prompt_version"] = PROMPT_VERSION
    return result


async def evaluate_answer_relevance(
    llm: LLMProvider,
    query: str,
    answer: str,
) -> dict[str, Any]:
    """Judge how well the answer addresses the user query.

    Args:
        llm: LLM provider instance.
        query: The original user question.
        answer: The generated answer text to evaluate.

    Returns:
        Dict with keys: score (float|None), reasoning (str), dimension (str),
        prompt_version (str). score=1.0 means fully relevant.
    """
    user_prompt = f"QUERY:\n{query}\n\nANSWER:\n{answer}"
    try:
        raw = await llm.generate(user_prompt, system=ANSWER_RELEVANCE_PROMPT)
    except Exception as exc:  # Intentionally broad: LLM errors must return graceful null score, not propagate
        logger.exception("LLM call failed for answer_relevance evaluation")
        return {
            "score": None,
            "reasoning": f"LLM call failed: {exc}",
            "dimension": "answer_relevance",
            "prompt_version": PROMPT_VERSION,
        }

    result = _parse_judge_response(raw, "answer_relevance")
    result["dimension"] = "answer_relevance"
    result["prompt_version"] = PROMPT_VERSION
    return result


async def evaluate_hallucination(
    llm: LLMProvider,
    context: str,
    answer: str,
) -> dict[str, Any]:
    """Identify claims in the answer not supported by the context.

    Note: A lower score indicates more hallucinations (worse). A score of
    1.0 means no hallucinations were detected.

    Args:
        llm: LLM provider instance.
        context: Concatenated source passages available to the generator.
        answer: The generated answer text to evaluate.

    Returns:
        Dict with keys: score (float|None), reasoning (str), dimension (str),
        prompt_version (str). score=0.0 means fully hallucinated.
    """
    user_prompt = f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"
    try:
        raw = await llm.generate(user_prompt, system=HALLUCINATION_PROMPT)
    except Exception as exc:  # Intentionally broad: LLM errors must return graceful null score, not propagate
        logger.exception("LLM call failed for hallucination evaluation")
        return {
            "score": None,
            "reasoning": f"LLM call failed: {exc}",
            "dimension": "hallucination",
            "prompt_version": PROMPT_VERSION,
        }

    result = _parse_judge_response(raw, "hallucination")
    result["dimension"] = "hallucination"
    result["prompt_version"] = PROMPT_VERSION
    return result


def evaluate_citation_accuracy(
    answer: str,
    citations: list[dict[str, Any]],
    context_by_source: dict[str, str],
) -> dict[str, Any]:
    """Deterministically verify that cited sources actually contain supporting content.

    For each citation in the answer, checks that the cited source ID exists in
    ``context_by_source`` and that the associated content is non-empty. Does not
    perform semantic matching — this is a structural/coverage check.

    Args:
        answer: The generated answer text (used to verify citation count is non-zero).
        citations: List of citation dicts, each expected to have a "source_id" key
            and optionally a "quote" key with the verbatim excerpt.
        context_by_source: Mapping of source_id (str) -> source content (str).

    Returns:
        Dict with keys:
          score (float): Fraction of citations that resolved to a valid, non-empty
              source. Returns 1.0 if no citations are present (vacuously correct).
          reasoning (str): Human-readable explanation of citation accuracy.
          dimension (str): "citation_accuracy".
          total_citations (int): Number of citations provided.
          valid_citations (int): Citations with a matching non-empty source.
          invalid_citation_ids (list[str]): Source IDs that could not be resolved.
    """
    if not citations:
        return {
            "score": 1.0,
            "reasoning": "No citations provided; vacuously accurate.",
            "dimension": "citation_accuracy",
            "total_citations": 0,
            "valid_citations": 0,
            "invalid_citation_ids": [],
        }

    total = len(citations)
    valid = 0
    invalid_ids: list[str] = []

    for citation in citations:
        source_id = citation.get("source_id", "")
        content = context_by_source.get(source_id, "")
        if content and content.strip():
            valid += 1
        else:
            invalid_ids.append(source_id)

    score = valid / total if total > 0 else 1.0

    if invalid_ids:
        reasoning = (
            f"{valid}/{total} citations resolved to valid, non-empty sources. Unresolvable source IDs: {invalid_ids}."
        )
    else:
        reasoning = f"All {total} citation(s) resolved to valid, non-empty sources."

    return {
        "score": score,
        "reasoning": reasoning,
        "dimension": "citation_accuracy",
        "total_citations": total,
        "valid_citations": valid,
        "invalid_citation_ids": invalid_ids,
    }


# ---------------------------------------------------------------------------
# Combined evaluator
# ---------------------------------------------------------------------------


async def evaluate_answer(
    llm: LLMProvider,
    query: str,
    context: str,
    answer: str,
    citations: list[dict[str, Any]],
    context_by_source: dict[str, str],
) -> dict[str, Any]:
    """Run all four evaluation dimensions and return a combined result.

    Runs faithfulness, answer_relevance, and hallucination concurrently via
    separate awaits, then appends the deterministic citation_accuracy check.

    Args:
        llm: LLM provider instance.
        query: The original user question.
        context: Concatenated source passages used to generate the answer.
        answer: The generated answer text to evaluate.
        citations: List of citation dicts with "source_id" keys.
        context_by_source: Mapping of source_id -> content text.

    Returns:
        Dict with keys:
          faithfulness (dict): Result from evaluate_faithfulness.
          answer_relevance (dict): Result from evaluate_answer_relevance.
          hallucination (dict): Result from evaluate_hallucination.
          citation_accuracy (dict): Result from evaluate_citation_accuracy.
          composite_score (float|None): Mean of all non-None scores across the
              four dimensions. None if every score is None.
          prompt_version (str): Version of the prompt templates used.
    """
    faithfulness_result = await evaluate_faithfulness(llm, context, answer)
    relevance_result = await evaluate_answer_relevance(llm, query, answer)
    hallucination_result = await evaluate_hallucination(llm, context, answer)
    citation_result = evaluate_citation_accuracy(answer, citations, context_by_source)

    scores = [
        faithfulness_result.get("score"),
        relevance_result.get("score"),
        hallucination_result.get("score"),
        citation_result.get("score"),
    ]
    valid_scores = [s for s in scores if s is not None]
    composite: float | None = sum(valid_scores) / len(valid_scores) if valid_scores else None

    return {
        "faithfulness": faithfulness_result,
        "answer_relevance": relevance_result,
        "hallucination": hallucination_result,
        "citation_accuracy": citation_result,
        "composite_score": composite,
        "prompt_version": PROMPT_VERSION,
    }
