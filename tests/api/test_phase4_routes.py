"""Tests for Phase 4 API routes: financial assumptions, suggestions, impact, ranking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.simulation.financial import compute_financial_impact
from src.simulation.ranking import rank_scenarios
from src.simulation.suggester import AlternativeSuggesterService


class TestComputeFinancialImpactIntegration:
    """Integration-level tests for financial impact via the service function."""

    def test_returns_expected_keys(self) -> None:
        assumptions = [MagicMock(name="A", value=1000.0, confidence=0.9)]
        result = compute_financial_impact(assumptions)
        assert "cost_range" in result
        assert "sensitivity_analysis" in result
        assert "delta_vs_baseline" in result

    def test_empty_returns_zeros(self) -> None:
        result = compute_financial_impact([])
        assert result["cost_range"]["expected"] == 0.0


class TestRankScenariosIntegration:
    """Integration-level tests for scenario ranking via the service function."""

    def test_ranking_returns_list(self) -> None:
        scenario = MagicMock()
        scenario.id = uuid4()
        scenario.name = "Test"
        scenario.evidence_confidence_score = 0.7
        result = rank_scenarios(
            [scenario], {}, [],
            {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2},
        )
        assert isinstance(result, list)
        assert len(result) == 1

    def test_ranking_empty(self) -> None:
        result = rank_scenarios(
            [], {}, [],
            {"evidence": 0.3, "simulation": 0.25, "financial": 0.25, "governance": 0.2},
        )
        assert result == []


class TestAlternativeSuggesterService:
    """Tests for AlternativeSuggesterService."""

    def test_build_prompt(self) -> None:
        service = AlternativeSuggesterService()
        scenario = MagicMock()
        scenario.name = "Test Scenario"
        scenario.simulation_type.value = "what_if"
        scenario.description = "A test"
        scenario.modifications = []

        prompt = service._build_prompt(scenario, "extra context")
        assert "Test Scenario" in prompt
        assert "extra context" in prompt

    def test_parse_valid_json(self) -> None:
        service = AlternativeSuggesterService()
        response = '[{"suggestion_text":"Do X","rationale":"Because Y","governance_flags":null,"evidence_gaps":null}]'
        result = service._parse_response(response, "prompt")
        assert len(result) == 1
        assert result[0]["suggestion_text"] == "Do X"
        assert result[0]["llm_prompt"] == "prompt"

    def test_parse_invalid_json_fallback(self) -> None:
        service = AlternativeSuggesterService()
        result = service._parse_response("not json", "prompt")
        assert len(result) == 1
        assert "parse_warning" in result[0]["governance_flags"]

    def test_fallback_suggestions(self) -> None:
        service = AlternativeSuggesterService()
        scenario = MagicMock()
        scenario.name = "Fallback Test"
        result = service._fallback_suggestions(scenario, "prompt")
        assert len(result) == 1
        assert "Fallback Test" in result[0]["suggestion_text"]
        assert "LLM_UNAVAILABLE" in result[0]["llm_response"]

    @pytest.mark.asyncio
    async def test_generate_suggestions_fallback_on_error(self) -> None:
        service = AlternativeSuggesterService()
        scenario = MagicMock()
        scenario.name = "Error Test"
        scenario.simulation_type.value = "what_if"
        scenario.description = "test"
        scenario.modifications = []

        with patch.object(service, "_call_llm", side_effect=Exception("API Error")):
            result = await service.generate_suggestions(scenario, uuid4())
            assert len(result) == 1
            assert "LLM_UNAVAILABLE" in result[0]["llm_response"]
