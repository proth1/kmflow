"""BDD tests for Suggestion Review Workflow (Story #379).

Tests the 4 acceptance scenarios:
1. ACCEPTED → ScenarioModification with template_source="llm_suggestion"
2. MODIFIED → ScenarioModification with original_suggestion_id and modified_content
3. REJECTED → No modification, rejection_reason stored
4. Validation: MODIFIED without modified_content → error
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import AlternativeSuggestion, ScenarioModification, SuggestionDisposition
from src.simulation.suggestion_review import review_suggestion

SCENARIO_ID = uuid.uuid4()
SUGGESTION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_suggestion(
    suggestion_id: uuid.UUID = SUGGESTION_ID,
    scenario_id: uuid.UUID = SCENARIO_ID,
    disposition: SuggestionDisposition = SuggestionDisposition.PENDING,
) -> MagicMock:
    s = MagicMock(spec=AlternativeSuggestion)
    s.id = suggestion_id
    s.scenario_id = scenario_id
    s.suggestion_text = "Add a validation gateway before approval"
    s.rationale = "Reduces error rate by 30%"
    s.disposition = disposition
    s.disposition_notes = None
    s.modified_content = None
    s.disposed_at = None
    s.disposed_by_user_id = None
    s.governance_flags = None
    s.evidence_gaps = None
    return s


def _make_session(suggestion: MagicMock | None) -> AsyncMock:
    """Create a mock session that returns the given suggestion on execute."""
    session = AsyncMock()
    result = AsyncMock()
    result.scalar_one_or_none = MagicMock(return_value=suggestion)
    session.execute = AsyncMock(return_value=result)

    added_objects: list = []

    def capture_add(obj: object) -> None:
        added_objects.append(obj)

    session.add = capture_add
    session._added = added_objects
    return session


class TestAcceptSuggestion:
    """Scenario 1: ACCEPTED creates a ScenarioModification."""

    @pytest.mark.asyncio
    async def test_accepted_creates_modification(self) -> None:
        """ACCEPTED → ScenarioModification with template_source='llm_suggestion'."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        result = await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.ACCEPTED,
            user_id=USER_ID,
        )

        assert result["disposition"] == "accepted"
        assert result["modification_id"] is not None
        assert suggestion.disposition == SuggestionDisposition.ACCEPTED
        assert suggestion.disposed_at is not None
        assert suggestion.disposed_by_user_id == USER_ID

    @pytest.mark.asyncio
    async def test_accepted_modification_has_template_source(self) -> None:
        """ScenarioModification has template_source='llm_suggestion'."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.ACCEPTED,
            user_id=USER_ID,
        )

        added = session._added
        assert len(added) == 1
        mod = added[0]
        assert isinstance(mod, ScenarioModification)
        assert mod.template_source == "llm_suggestion"
        assert mod.suggestion_id == SUGGESTION_ID

    @pytest.mark.asyncio
    async def test_accepted_modification_links_suggestion(self) -> None:
        """ScenarioModification has suggestion_id FK linking to original."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.ACCEPTED,
            user_id=USER_ID,
        )

        mod = session._added[0]
        assert mod.suggestion_id == SUGGESTION_ID
        assert mod.original_suggestion_id is None


class TestModifySuggestion:
    """Scenario 2: MODIFIED creates modification with original linked."""

    @pytest.mark.asyncio
    async def test_modified_creates_modification_with_content(self) -> None:
        """MODIFIED → ScenarioModification from modified_content."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)
        modified_content = {"name": "Adjusted gateway", "description": "Modified validation step"}

        result = await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.MODIFIED,
            user_id=USER_ID,
            modified_content=modified_content,
        )

        assert result["disposition"] == "modified"
        assert result["modification_id"] is not None
        assert suggestion.disposition == SuggestionDisposition.MODIFIED
        assert suggestion.modified_content == modified_content

    @pytest.mark.asyncio
    async def test_modified_links_original_suggestion(self) -> None:
        """ScenarioModification has original_suggestion_id (not suggestion_id)."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.MODIFIED,
            user_id=USER_ID,
            modified_content={"name": "Adjusted"},
        )

        mod = session._added[0]
        assert mod.original_suggestion_id == SUGGESTION_ID
        assert mod.suggestion_id is None

    @pytest.mark.asyncio
    async def test_modified_uses_content_name(self) -> None:
        """element_name on modification uses modified_content['name']."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.MODIFIED,
            user_id=USER_ID,
            modified_content={"name": "Custom Element Name"},
        )

        mod = session._added[0]
        assert mod.element_name == "Custom Element Name"


class TestRejectSuggestion:
    """Scenario 3: REJECTED stores reason, no modification created."""

    @pytest.mark.asyncio
    async def test_rejected_no_modification(self) -> None:
        """REJECTED → no ScenarioModification created."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        result = await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.REJECTED,
            user_id=USER_ID,
            rejection_reason="Not aligned with client goals",
        )

        assert result["disposition"] == "rejected"
        assert result["modification_id"] is None
        assert len(session._added) == 0

    @pytest.mark.asyncio
    async def test_rejected_stores_reason(self) -> None:
        """Rejection reason is stored on the suggestion."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.REJECTED,
            user_id=USER_ID,
            rejection_reason="Not aligned with client goals",
        )

        assert suggestion.disposition == SuggestionDisposition.REJECTED
        assert suggestion.disposition_notes == "Not aligned with client goals"
        assert suggestion.disposed_at is not None

    @pytest.mark.asyncio
    async def test_rejected_suggestion_remains_retrievable(self) -> None:
        """Rejected suggestion is not deleted, remains in database."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        await review_suggestion(
            session=session,
            scenario_id=SCENARIO_ID,
            suggestion_id=SUGGESTION_ID,
            disposition=SuggestionDisposition.REJECTED,
            user_id=USER_ID,
            rejection_reason="Not relevant",
        )

        # Suggestion still has its ID (not deleted)
        assert suggestion.id == SUGGESTION_ID
        assert suggestion.disposed_by_user_id == USER_ID


class TestValidation:
    """Scenario 4: Validation rules."""

    @pytest.mark.asyncio
    async def test_modified_without_content_raises(self) -> None:
        """MODIFIED without modified_content → ValueError."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        with pytest.raises(ValueError, match="modified_content is required"):
            await review_suggestion(
                session=session,
                scenario_id=SCENARIO_ID,
                suggestion_id=SUGGESTION_ID,
                disposition=SuggestionDisposition.MODIFIED,
                user_id=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_rejected_without_reason_raises(self) -> None:
        """REJECTED without rejection_reason → ValueError."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        with pytest.raises(ValueError, match="rejection_reason is required"):
            await review_suggestion(
                session=session,
                scenario_id=SCENARIO_ID,
                suggestion_id=SUGGESTION_ID,
                disposition=SuggestionDisposition.REJECTED,
                user_id=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_suggestion_not_found_raises(self) -> None:
        """Non-existent suggestion → ValueError."""
        session = _make_session(None)

        with pytest.raises(ValueError, match="not found"):
            await review_suggestion(
                session=session,
                scenario_id=SCENARIO_ID,
                suggestion_id=uuid.uuid4(),
                disposition=SuggestionDisposition.ACCEPTED,
                user_id=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_already_disposed_raises(self) -> None:
        """Already-disposed suggestion → ValueError."""
        suggestion = _make_suggestion(disposition=SuggestionDisposition.ACCEPTED)
        session = _make_session(suggestion)

        with pytest.raises(ValueError, match="already accepted"):
            await review_suggestion(
                session=session,
                scenario_id=SCENARIO_ID,
                suggestion_id=SUGGESTION_ID,
                disposition=SuggestionDisposition.REJECTED,
                user_id=USER_ID,
                rejection_reason="Changed mind",
            )

    @pytest.mark.asyncio
    async def test_pending_status_remains_on_validation_error(self) -> None:
        """Failed validation does not change suggestion status."""
        suggestion = _make_suggestion()
        session = _make_session(suggestion)

        with pytest.raises(ValueError):
            await review_suggestion(
                session=session,
                scenario_id=SCENARIO_ID,
                suggestion_id=SUGGESTION_ID,
                disposition=SuggestionDisposition.MODIFIED,
                user_id=USER_ID,
            )

        # Status should still be PENDING
        assert suggestion.disposition == SuggestionDisposition.PENDING
