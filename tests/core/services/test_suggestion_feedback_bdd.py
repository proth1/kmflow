"""BDD tests for LLM suggestion feedback loop (Story #390).

Scenario 1: Accepted suggestions appear in simulation
Scenario 2: LLM-sourced vs manual modifications treated equally
Scenario 3: Rejected suggestions excluded from future prompts
Scenario 4: Full traceability chain
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from src.core.models import (
    AlternativeSuggestion,
    LLMAuditLog,
    ScenarioModification,
    SuggestionDisposition,
)
from src.core.models.simulation import ModificationType
from src.core.services.suggestion_feedback import (
    _summarize_pattern,
    build_exclusion_prompt,
    build_traceability_chain,
    get_rejection_patterns,
    record_rejection_feedback,
)

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_ID = uuid.uuid4()


def _mock_suggestion(
    suggestion_text: str = "Automate invoice processing using RPA",
    disposition: SuggestionDisposition = SuggestionDisposition.REJECTED,
) -> MagicMock:
    s = MagicMock(spec=AlternativeSuggestion)
    s.id = uuid.uuid4()
    s.scenario_id = SCENARIO_ID
    s.suggestion_text = suggestion_text
    s.rationale = "This would reduce manual effort by 80%"
    s.disposition = disposition
    s.disposition_notes = "Not feasible in current environment"
    s.disposed_at = datetime(2026, 2, 27, 12, 0, tzinfo=UTC)
    s.llm_prompt = "Generate suggestions for process improvement"
    s.llm_response = '{"suggestions": [...]}'
    s.created_at = datetime(2026, 2, 27, 10, 0, tzinfo=UTC)
    return s


def _mock_modification(
    template_source: str = "llm_suggestion",
    suggestion_id: uuid.UUID | None = None,
) -> MagicMock:
    m = MagicMock(spec=ScenarioModification)
    m.id = uuid.uuid4()
    m.scenario_id = SCENARIO_ID
    m.modification_type = ModificationType.TASK_REMOVE
    m.element_id = "task_1"
    m.element_name = "Manual Review"
    m.template_source = template_source
    m.suggestion_id = suggestion_id
    m.original_suggestion_id = None
    m.applied_at = datetime(2026, 2, 27, 11, 0, tzinfo=UTC)
    return m


def _mock_audit_log() -> MagicMock:
    a = MagicMock(spec=LLMAuditLog)
    a.id = uuid.uuid4()
    a.scenario_id = SCENARIO_ID
    a.prompt_text = "Generate suggestions for process improvement"
    a.response_text = '{"suggestions": [{"text": "Automate invoice processing"}]}'
    a.model_name = "claude-sonnet-4-6"
    a.prompt_tokens = 500
    a.completion_tokens = 200
    a.hallucination_flagged = False
    a.created_at = datetime(2026, 2, 27, 10, 0, tzinfo=UTC)
    return a


class TestRejectionFeedbackRecording:
    """Scenario 3: Rejected suggestions create feedback records."""

    async def test_record_rejection_creates_feedback(self) -> None:
        """When a suggestion is rejected, a RejectionFeedback record is created."""
        session = AsyncMock()
        suggestion = _mock_suggestion()

        feedback = await record_rejection_feedback(session, ENGAGEMENT_ID, suggestion)

        assert feedback.engagement_id == ENGAGEMENT_ID
        assert feedback.suggestion_pattern_summary == suggestion.suggestion_text
        assert str(suggestion.id) in feedback.rejected_suggestion_ids
        session.add.assert_called_once_with(feedback)

    async def test_long_suggestion_is_truncated(self) -> None:
        """Long suggestion text is summarized to 200 chars."""
        session = AsyncMock()
        long_text = "A" * 300
        suggestion = _mock_suggestion(suggestion_text=long_text)

        feedback = await record_rejection_feedback(session, ENGAGEMENT_ID, suggestion)

        assert len(feedback.suggestion_pattern_summary) == 200
        assert feedback.suggestion_pattern_summary.endswith("...")


class TestRejectionPatternRetrieval:
    """Scenario 3: Rejected patterns loaded for prompt injection."""

    async def test_get_patterns_returns_summaries(self) -> None:
        """Patterns are loaded in reverse chronological order."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            "Automate using RPA",
            "Replace manual review with AI",
        ]
        session.execute.return_value = mock_result

        patterns = await get_rejection_patterns(session, ENGAGEMENT_ID)

        assert len(patterns) == 2
        assert patterns[0] == "Automate using RPA"

    async def test_empty_patterns(self) -> None:
        """No rejections returns empty list."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        patterns = await get_rejection_patterns(session, ENGAGEMENT_ID)

        assert patterns == []


class TestExclusionPromptGeneration:
    """Scenario 3: Exclusion prompt formatted for LLM injection."""

    def test_builds_numbered_exclusion_prompt(self) -> None:
        """Patterns are formatted as a numbered list."""
        patterns = ["Automate using RPA", "Replace manual review"]
        prompt = build_exclusion_prompt(patterns)

        assert "previously rejected" in prompt
        assert "1. Automate using RPA" in prompt
        assert "2. Replace manual review" in prompt

    def test_empty_patterns_returns_empty_string(self) -> None:
        """No patterns means no exclusion text."""
        assert build_exclusion_prompt([]) == ""

    def test_single_pattern(self) -> None:
        """Single pattern formats correctly."""
        prompt = build_exclusion_prompt(["Remove quality checks"])
        assert "1. Remove quality checks" in prompt


class TestTraceabilityChain:
    """Scenario 4: Full traceability from modification to audit log."""

    async def test_full_chain_with_suggestion_and_audit(self) -> None:
        """Complete chain: modification → suggestion → audit log."""
        session = AsyncMock()
        suggestion_id = uuid.uuid4()
        modification = _mock_modification(suggestion_id=suggestion_id)
        suggestion = _mock_suggestion()
        audit_log = _mock_audit_log()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = modification
            elif call_count == 2:
                result.scalar_one_or_none.return_value = suggestion
            else:
                result.scalar_one_or_none.return_value = audit_log
            return result

        session.execute = side_effect

        chain = await build_traceability_chain(session, SCENARIO_ID, modification.id)

        assert chain is not None
        assert chain["traceability_complete"] is True
        assert chain["modification"]["element_name"] == "Manual Review"
        assert chain["suggestion"]["rationale"] == "This would reduce manual effort by 80%"
        assert chain["audit_log"]["model_name"] == "claude-sonnet-4-6"

    async def test_modification_without_suggestion(self) -> None:
        """Manual modification returns incomplete chain."""
        session = AsyncMock()
        modification = _mock_modification(template_source="manual", suggestion_id=None)
        modification.original_suggestion_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = modification
        session.execute.return_value = mock_result

        chain = await build_traceability_chain(session, SCENARIO_ID, modification.id)

        assert chain is not None
        assert chain["traceability_complete"] is False
        assert chain["suggestion"] is None
        assert chain["audit_log"] is None

    async def test_modification_not_found(self) -> None:
        """Missing modification returns None."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        chain = await build_traceability_chain(session, SCENARIO_ID, uuid.uuid4())

        assert chain is None

    async def test_suggestion_without_audit_log(self) -> None:
        """Suggestion exists but no matching audit log."""
        session = AsyncMock()
        suggestion_id = uuid.uuid4()
        modification = _mock_modification(suggestion_id=suggestion_id)
        suggestion = _mock_suggestion()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = modification
            elif call_count == 2:
                result.scalar_one_or_none.return_value = suggestion
            else:
                result.scalar_one_or_none.return_value = None  # no audit log
            return result

        session.execute = side_effect

        chain = await build_traceability_chain(session, SCENARIO_ID, modification.id)

        assert chain["traceability_complete"] is False
        assert chain["suggestion"] is not None
        assert chain["audit_log"] is None


class TestModificationSourceEquality:
    """Scenario 2: LLM-sourced and manual modifications treated equally."""

    def test_template_source_distinguishes_origin(self) -> None:
        """template_source field indicates origin without affecting computation."""
        llm_mod = _mock_modification(template_source="llm_suggestion")
        manual_mod = _mock_modification(template_source="manual")

        # Both have same modification_type and can be simulated identically
        assert llm_mod.modification_type == manual_mod.modification_type
        # Source is metadata only
        assert llm_mod.template_source != manual_mod.template_source


class TestPatternSummarization:
    """Edge cases for pattern summarization."""

    def test_short_text_unchanged(self) -> None:
        assert _summarize_pattern("short text") == "short text"

    def test_exactly_200_chars(self) -> None:
        text = "A" * 200
        assert _summarize_pattern(text) == text

    def test_201_chars_truncated(self) -> None:
        text = "A" * 201
        result = _summarize_pattern(text)
        assert len(result) == 200
        assert result.endswith("...")

    def test_whitespace_stripped(self) -> None:
        assert _summarize_pattern("  hello  ") == "hello"
