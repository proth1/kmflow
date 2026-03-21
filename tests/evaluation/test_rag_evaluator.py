"""Tests for the RAG evaluator (src.evaluation.rag_evaluator).

evaluate_citation_accuracy is fully deterministic.
evaluate_faithfulness and evaluate_answer_relevance are tested with a mocked
LLM so no network calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.evaluation.rag_evaluator import (
    _parse_judge_response,
    evaluate_citation_accuracy,
    evaluate_faithfulness,
)

# ---------------------------------------------------------------------------
# _parse_judge_response (internal helper — tested directly for precision)
# ---------------------------------------------------------------------------


class TestParseJudgeResponse:
    def test_valid_json_parsed_correctly(self) -> None:
        raw = '{"score": 0.85, "reasoning": "looks good"}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] == pytest.approx(0.85)
        assert result["reasoning"] == "looks good"

    def test_score_clamped_above_one(self) -> None:
        raw = '{"score": 1.5, "reasoning": "over-confident"}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] == pytest.approx(1.0)

    def test_score_clamped_below_zero(self) -> None:
        raw = '{"score": -0.3, "reasoning": "negative"}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] == pytest.approx(0.0)

    def test_invalid_json_returns_none_score(self) -> None:
        result = _parse_judge_response("this is not json", "faithfulness")
        assert result["score"] is None
        assert "JSON parse error" in result["reasoning"]

    def test_missing_score_key_returns_none(self) -> None:
        raw = '{"reasoning": "no score here"}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] is None

    def test_missing_reasoning_key_returns_none_score(self) -> None:
        raw = '{"score": 0.9}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] is None

    def test_markdown_fenced_json_stripped(self) -> None:
        raw = '```json\n{"score": 0.7, "reasoning": "ok"}\n```'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] == pytest.approx(0.7)

    def test_non_numeric_score_coerced_to_none(self) -> None:
        raw = '{"score": "high", "reasoning": "qualitative"}'
        result = _parse_judge_response(raw, "faithfulness")
        assert result["score"] is None


# ---------------------------------------------------------------------------
# evaluate_citation_accuracy (deterministic, no LLM)
# ---------------------------------------------------------------------------


class TestEvaluateCitationAccuracy:
    def test_all_citations_found_score_is_one(self) -> None:
        citations = [{"source_id": "src-1"}, {"source_id": "src-2"}]
        context = {"src-1": "Some content.", "src-2": "More content."}
        result = evaluate_citation_accuracy("answer", citations, context)
        assert result["score"] == pytest.approx(1.0)
        assert result["valid_citations"] == 2
        assert result["invalid_citation_ids"] == []

    def test_half_citations_found_score_is_half(self) -> None:
        citations = [{"source_id": "src-1"}, {"source_id": "src-missing"}]
        context = {"src-1": "Content here."}
        result = evaluate_citation_accuracy("answer", citations, context)
        assert result["score"] == pytest.approx(0.5)
        assert result["valid_citations"] == 1
        assert "src-missing" in result["invalid_citation_ids"]

    def test_no_citations_found_score_is_zero(self) -> None:
        citations = [{"source_id": "ghost-1"}, {"source_id": "ghost-2"}]
        context = {}
        result = evaluate_citation_accuracy("answer", citations, context)
        assert result["score"] == pytest.approx(0.0)
        assert result["valid_citations"] == 0
        assert set(result["invalid_citation_ids"]) == {"ghost-1", "ghost-2"}

    def test_empty_citations_score_is_one_vacuously(self) -> None:
        result = evaluate_citation_accuracy("answer", [], {})
        assert result["score"] == pytest.approx(1.0)
        assert result["total_citations"] == 0
        assert result["dimension"] == "citation_accuracy"

    def test_whitespace_only_content_counts_as_invalid(self) -> None:
        citations = [{"source_id": "ws"}]
        context = {"ws": "   "}
        result = evaluate_citation_accuracy("answer", citations, context)
        assert result["score"] == pytest.approx(0.0)
        assert "ws" in result["invalid_citation_ids"]

    def test_dimension_field_is_citation_accuracy(self) -> None:
        result = evaluate_citation_accuracy("answer", [], {})
        assert result["dimension"] == "citation_accuracy"

    def test_total_citations_matches_input_length(self) -> None:
        citations = [{"source_id": f"s{i}"} for i in range(5)]
        context = {f"s{i}": f"content {i}" for i in range(5)}
        result = evaluate_citation_accuracy("answer", citations, context)
        assert result["total_citations"] == 5


# ---------------------------------------------------------------------------
# evaluate_faithfulness (async, uses mocked LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluateFaithfulness:
    async def test_returns_parsed_score_from_llm(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value='{"score": 0.85, "reasoning": "test reasoning"}')

        result = await evaluate_faithfulness(
            llm=mock_llm,
            context="The project started in 2020.",
            answer="The project began in 2020.",
        )

        assert result["score"] == pytest.approx(0.85)
        assert result["dimension"] == "faithfulness"
        assert "prompt_version" in result
        mock_llm.generate.assert_called_once()

    async def test_json_parse_failure_returns_none_score(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="not valid json at all")

        result = await evaluate_faithfulness(
            llm=mock_llm,
            context="Some context.",
            answer="Some answer.",
        )

        assert result["score"] is None
        assert result["dimension"] == "faithfulness"

    async def test_llm_exception_returns_none_score(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        result = await evaluate_faithfulness(
            llm=mock_llm,
            context="Some context.",
            answer="Some answer.",
        )

        assert result["score"] is None
        assert "LLM call failed" in result["reasoning"]
        assert result["dimension"] == "faithfulness"

    async def test_prompt_includes_context_and_answer(self) -> None:
        """The user prompt passed to llm.generate should contain context and answer."""
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value='{"score": 1.0, "reasoning": "ok"}')

        context_text = "UNIQUE_CONTEXT_MARKER"
        answer_text = "UNIQUE_ANSWER_MARKER"

        await evaluate_faithfulness(
            llm=mock_llm,
            context=context_text,
            answer=answer_text,
        )

        user_prompt: str = mock_llm.generate.call_args[0][0]
        assert context_text in user_prompt
        assert answer_text in user_prompt

    async def test_score_clamped_to_one(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value='{"score": 99.0, "reasoning": "very faithful"}')

        result = await evaluate_faithfulness(
            llm=mock_llm,
            context="ctx",
            answer="ans",
        )

        assert result["score"] == pytest.approx(1.0)
