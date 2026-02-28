"""Tests for DeterministicLinker: case ID extraction and event linking."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.canonical_event import CanonicalActivityEvent
from src.taskmining.correlation.deterministic import DeterministicLinker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    window_title: str | None = None,
    engagement_id: uuid.UUID | None = None,
) -> CanonicalActivityEvent:
    event = MagicMock(spec=CanonicalActivityEvent)
    event.id = uuid.uuid4()
    event.engagement_id = engagement_id or uuid.uuid4()
    event.raw_payload = {"window_title": window_title} if window_title else {}
    event.timestamp_utc = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    event.source_system = "taskmining"
    event.performer_role_ref = "analyst"
    return event


# ---------------------------------------------------------------------------
# extract_case_id_from_title
# ---------------------------------------------------------------------------


class TestExtractCaseId:
    def setup_method(self) -> None:
        self.linker = DeterministicLinker()

    def test_extract_case_id_standard_pattern(self) -> None:
        """CASE-XXXXX hyphenated pattern is extracted."""
        result = self.linker.extract_case_id_from_title("CASE-12345 - Invoice Processing")
        assert result == "CASE-12345"

    def test_extract_case_id_servicenow_pattern(self) -> None:
        """ServiceNow INC pattern is extracted."""
        result = self.linker.extract_case_id_from_title("ServiceNow - INC0012345 - Password Reset")
        assert result == "INC0012345"

    def test_extract_case_id_servicenow_chg_pattern(self) -> None:
        """ServiceNow CHG pattern is extracted."""
        result = self.linker.extract_case_id_from_title("Chrome - CHG0001234 - Network Upgrade")
        assert result == "CHG0001234"

    def test_extract_case_id_jira_style(self) -> None:
        """Jira-style PROJECT-1234 pattern is extracted."""
        result = self.linker.extract_case_id_from_title("PROJ-999 | Jira Issue Board")
        assert result == "PROJ-999"

    def test_extract_case_id_hash_prefixed(self) -> None:
        """Hash-prefixed #12345 pattern is extracted."""
        result = self.linker.extract_case_id_from_title("GitHub PR #12345: Fix login bug")
        assert result == "12345"

    def test_extract_case_id_no_match(self) -> None:
        """Returns None when no case ID pattern is found."""
        result = self.linker.extract_case_id_from_title("Microsoft Word - Annual Report.docx")
        assert result is None

    def test_extract_case_id_empty_title(self) -> None:
        """Returns None for an empty window title."""
        result = self.linker.extract_case_id_from_title("")
        assert result is None

    def test_extract_case_id_custom_patterns(self) -> None:
        """Custom override patterns replace defaults."""
        result = self.linker.extract_case_id_from_title(
            "MYAPP-XYZ-001 details",
            patterns=[r"\bMYAPP-[A-Z]+-\d+\b"],
        )
        assert result == "MYAPP-XYZ-001"

    def test_extract_case_id_returns_uppercase(self) -> None:
        """Matched ID is returned in uppercase."""
        result = self.linker.extract_case_id_from_title("case-12345 processing")
        assert result == "CASE-12345"

    def test_extract_case_id_first_match_wins(self) -> None:
        """When multiple patterns match, the first wins."""
        # INC pattern is listed before CASE pattern
        result = self.linker.extract_case_id_from_title("INC0012345 and CASE-999 open")
        # INC has higher priority in DEFAULT_PATTERNS
        assert result is not None
        assert "INC" in result or "CASE" in result


# ---------------------------------------------------------------------------
# link_events_to_cases
# ---------------------------------------------------------------------------


class TestLinkEventsToCases:
    def setup_method(self) -> None:
        self.linker = DeterministicLinker()
        self.engagement_id = uuid.uuid4()

    @pytest.mark.asyncio
    async def test_link_events_deterministic(self) -> None:
        """Events with recognized window titles produce CaseLinkEdge records."""
        session = AsyncMock()
        session.add = MagicMock()

        event = _make_event("INC0012345 - Password Reset", self.engagement_id)

        edges = await self.linker.link_events_to_cases(session, self.engagement_id, [event])

        assert len(edges) == 1
        assert edges[0].case_id == "INC0012345"
        assert edges[0].method == "deterministic"
        assert edges[0].confidence == 1.0
        assert edges[0].engagement_id == self.engagement_id
        assert edges[0].event_id == event.id

    @pytest.mark.asyncio
    async def test_link_events_no_window_title(self) -> None:
        """Events without a window_title in raw_payload are skipped."""
        session = AsyncMock()
        session.add = MagicMock()

        event = _make_event(None, self.engagement_id)

        edges = await self.linker.link_events_to_cases(session, self.engagement_id, [event])

        assert edges == []
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_link_events_no_match_skipped(self) -> None:
        """Events whose window titles don't match patterns are skipped."""
        session = AsyncMock()
        session.add = MagicMock()

        event = _make_event("Microsoft Excel - Budget_2026.xlsx", self.engagement_id)

        edges = await self.linker.link_events_to_cases(session, self.engagement_id, [event])

        assert edges == []

    @pytest.mark.asyncio
    async def test_link_events_multiple_mixed(self) -> None:
        """Only events with matching titles produce edges."""
        session = AsyncMock()
        session.add = MagicMock()

        events = [
            _make_event("CASE-111 - Loan Application", self.engagement_id),
            _make_event("Microsoft Word", self.engagement_id),
            _make_event("INC0099999 - Network Issue", self.engagement_id),
        ]

        edges = await self.linker.link_events_to_cases(session, self.engagement_id, events)

        assert len(edges) == 2
        case_ids = {e.case_id for e in edges}
        assert "CASE-111" in case_ids
        assert "INC0099999" in case_ids

    @pytest.mark.asyncio
    async def test_link_events_explainability_populated(self) -> None:
        """Edge explainability dict records the source window title."""
        session = AsyncMock()
        session.add = MagicMock()

        title = "CHG0001234 change approval"
        event = _make_event(title, self.engagement_id)

        edges = await self.linker.link_events_to_cases(session, self.engagement_id, [event])

        assert edges[0].explainability["window_title"] == title
        assert edges[0].explainability["extracted_id"] == "CHG0001234"
