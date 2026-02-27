"""BDD tests for Story #374: LLM Modification Suggestion Engine.

Tests cover 4 acceptance scenarios:
1. LLM generates structured modification suggestions
2. Each suggestion includes all required fields
3. Governance flags from knowledge graph
4. Full LLM interaction audit logging
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import LLMAuditLog, SimulationScenario
from src.simulation.suggestion_engine import (
    CONSIDERATION_FRAMING,
    generate_audited_suggestions,
)


def _make_scenario(**overrides: Any) -> MagicMock:
    """Build a mock SimulationScenario with sane defaults."""
    scenario = MagicMock(spec=SimulationScenario)
    scenario.id = overrides.get("id", uuid.uuid4())
    scenario.engagement_id = overrides.get("engagement_id", uuid.uuid4())
    scenario.name = overrides.get("name", "Test Scenario")
    scenario.description = overrides.get("description", "A test scenario")
    scenario.simulation_type = MagicMock(value="what_if")
    scenario.modifications = overrides.get("modifications", [])
    return scenario


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.suggester_model = "claude-sonnet-4-20250514"
    return settings


class TestScenario1StructuredSuggestions:
    """Scenario 1: LLM generates structured modification suggestions."""

    @pytest.mark.asyncio
    async def test_generates_suggestions_from_llm(self) -> None:
        """Given a scenario, the engine calls LLM and returns parsed suggestions."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        llm_response = """[
            {"suggestion_text": "Consider automating step 3", "rationale": "Reduces cycle time",
             "governance_flags": [], "evidence_gaps": ["step_3_volume_data"]},
            {"suggestion_text": "Consider merging steps 5 and 6", "rationale": "Eliminates handoff",
             "governance_flags": [], "evidence_gaps": []}
        ]"""

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value=llm_response)
            mock_svc._parse_response.return_value = [
                {
                    "suggestion_text": "Consider automating step 3",
                    "rationale": "Reduces cycle time",
                    "governance_flags": [],
                    "evidence_gaps": ["step_3_volume_data"],
                },
                {
                    "suggestion_text": "Consider merging steps 5 and 6",
                    "rationale": "Eliminates handoff",
                    "governance_flags": [],
                    "evidence_gaps": [],
                },
            ]

            result = await generate_audited_suggestions(scenario, user_id, session)

        assert len(result) >= 2
        assert all("suggestion_text" in s for s in result)

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self) -> None:
        """Given the LLM fails, fallback suggestions are returned."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(side_effect=RuntimeError("API down"))
            mock_svc._fallback_suggestions.return_value = [
                {"suggestion_text": "Fallback suggestion", "llm_response": None},
            ]

            result = await generate_audited_suggestions(scenario, user_id, session)

        assert len(result) >= 1


class TestScenario2RequiredFields:
    """Scenario 2: Each suggestion includes required fields."""

    @pytest.mark.asyncio
    async def test_consideration_framing_added(self) -> None:
        """Suggestions without 'consideration for review' get it prepended."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value="[]")
            mock_svc._parse_response.return_value = [
                {"suggestion_text": "Automate step 3", "rationale": "Faster"},
            ]

            result = await generate_audited_suggestions(scenario, user_id, session)

        assert len(result) == 1
        text = result[0]["suggestion_text"]
        assert CONSIDERATION_FRAMING in text.lower()

    @pytest.mark.asyncio
    async def test_framing_not_duplicated(self) -> None:
        """Suggestions already containing framing are not double-wrapped."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value="[]")
            mock_svc._parse_response.return_value = [
                {"suggestion_text": "As a consideration for review, automate step 3"},
            ]

            result = await generate_audited_suggestions(scenario, user_id, session)

        text = result[0]["suggestion_text"]
        assert text.lower().count(CONSIDERATION_FRAMING) == 1


class TestScenario3GovernanceFlags:
    """Scenario 3: Suggestions affecting regulatory controls include governance flags."""

    @pytest.mark.asyncio
    async def test_governance_flags_from_graph(self) -> None:
        """Governed elements get known_constraint flags from the knowledge graph."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        graph_service = AsyncMock()
        graph_service.run_query = AsyncMock(
            return_value=[
                {
                    "element_id": "elem-001",
                    "activity_name": "Manual Review",
                    "control_name": "SOX-404",
                    "regulation": "SOX",
                },
            ]
        )

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value="[]")
            mock_svc._parse_response.return_value = [
                {
                    "suggestion_text": "Automate manual review",
                    "affected_element_ids": ["elem-001"],
                    "governance_flags": None,
                },
            ]

            result = await generate_audited_suggestions(
                scenario,
                user_id,
                session,
                graph_service=graph_service,
            )

        flags = result[0].get("governance_flags")
        assert flags is not None
        assert len(flags) >= 1
        assert flags[0]["type"] == "known_constraint"
        assert flags[0]["regulation"] == "SOX"
        assert "Manual Review" in flags[0]["message"]

    @pytest.mark.asyncio
    async def test_no_flags_for_ungoverned_elements(self) -> None:
        """Elements not in the governance graph get no flags."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        graph_service = AsyncMock()
        graph_service.run_query = AsyncMock(return_value=[])

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value="[]")
            mock_svc._parse_response.return_value = [
                {
                    "suggestion_text": "Simplify step",
                    "affected_element_ids": ["elem-999"],
                    "governance_flags": None,
                },
            ]

            result = await generate_audited_suggestions(
                scenario,
                user_id,
                session,
                graph_service=graph_service,
            )

        assert result[0].get("governance_flags") is None

    @pytest.mark.asyncio
    async def test_graph_query_failure_returns_suggestions_without_flags(self) -> None:
        """If the graph query fails, suggestions are still returned without flags."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        graph_service = AsyncMock()
        graph_service.run_query = AsyncMock(side_effect=RuntimeError("Graph unavailable"))

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(return_value="[]")
            mock_svc._parse_response.return_value = [
                {"suggestion_text": "Do something"},
            ]

            result = await generate_audited_suggestions(
                scenario,
                user_id,
                session,
                graph_service=graph_service,
            )

        assert len(result) == 1


class TestScenario4AuditLogging:
    """Scenario 5: Full LLM interaction is logged for audit."""

    @pytest.mark.asyncio
    async def test_audit_log_created_on_success(self) -> None:
        """A successful LLM call persists an audit log entry."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt text"
            mock_svc._call_llm = AsyncMock(return_value="[{}]")
            mock_svc._parse_response.return_value = [{"suggestion_text": "Test"}]

            await generate_audited_suggestions(scenario, user_id, session)

        # Verify session.add was called with an LLMAuditLog
        session.add.assert_called_once()
        audit_entry = session.add.call_args[0][0]
        assert isinstance(audit_entry, LLMAuditLog)
        assert audit_entry.scenario_id == scenario.id
        assert audit_entry.user_id == user_id
        assert audit_entry.prompt_text == "test prompt text"
        assert audit_entry.response_text == "[{}]"
        assert audit_entry.error_message is None
        assert audit_entry.model_name == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_audit_log_created_on_failure(self) -> None:
        """A failed LLM call still persists an audit log with error_message."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = "test prompt"
            mock_svc._call_llm = AsyncMock(side_effect=RuntimeError("Claude timeout"))
            mock_svc._fallback_suggestions.return_value = [
                {"suggestion_text": "Fallback", "llm_response": None},
            ]

            await generate_audited_suggestions(scenario, user_id, session)

        session.add.assert_called_once()
        audit_entry = session.add.call_args[0][0]
        assert isinstance(audit_entry, LLMAuditLog)
        assert audit_entry.error_message == "Claude timeout"
        assert audit_entry.prompt_text == "test prompt"

    @pytest.mark.asyncio
    async def test_audit_log_includes_token_estimates(self) -> None:
        """Token estimates are stored based on text length."""
        scenario = _make_scenario()
        user_id = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()

        prompt_text = "x" * 400  # ~100 tokens at //4 approximation
        llm_response = "y" * 200  # ~50 tokens

        with (
            patch("src.simulation.suggestion_engine.get_settings", return_value=_make_settings()),
            patch("src.simulation.suggestion_engine.AlternativeSuggesterService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc._build_prompt.return_value = prompt_text
            mock_svc._call_llm = AsyncMock(return_value=llm_response)
            mock_svc._parse_response.return_value = [{"suggestion_text": "Test"}]

            await generate_audited_suggestions(scenario, user_id, session)

        audit_entry = session.add.call_args[0][0]
        assert audit_entry.prompt_tokens == 100
        assert audit_entry.completion_tokens == 50


class TestLLMAuditLogModel:
    """Test LLMAuditLog model structure."""

    def test_model_tablename(self) -> None:
        assert LLMAuditLog.__tablename__ == "llm_audit_logs"

    def test_model_has_required_columns(self) -> None:
        column_names = {c.name for c in LLMAuditLog.__table__.columns}
        required = {
            "id",
            "scenario_id",
            "user_id",
            "prompt_text",
            "response_text",
            "evidence_ids",
            "prompt_tokens",
            "completion_tokens",
            "model_name",
            "error_message",
            "created_at",
        }
        assert required.issubset(column_names)

    def test_model_has_repr(self) -> None:
        assert hasattr(LLMAuditLog, "__repr__")
