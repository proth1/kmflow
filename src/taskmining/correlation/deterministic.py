"""Deterministic correlation: regex-based case ID extraction from window titles.

Handles common patterns found in enterprise tooling:
- Hyphenated IDs: CASE-12345, INC-0012345, PROJ-999
- ServiceNow: INC0012345, CHG0001234, REQ0099999
- Hash-prefixed: #12345
- Jira-style: PROJ-1234 (PROJECT key in uppercase, hyphen, numeric)
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default extraction patterns (ordered from most-specific to least-specific)
DEFAULT_PATTERNS: list[str] = [
    # ServiceNow: INC0012345, CHG0001234, REQ0099999, TASK0001234
    r"\b(?:INC|CHG|REQ|TASK|PRB|SCTASK)\d{7,10}\b",
    # Jira-style with uppercase project key: PROJ-1234
    r"\b[A-Z]{2,10}-\d{1,6}\b",
    # Hash-prefixed numeric: #12345
    r"#(\d{4,8})\b",
    # Generic WORD-NUMBER: CASE-12345, TICKET-999
    r"\b(?:CASE|TICKET|INCIDENT|CHANGE|REQUEST)-\d{3,8}\b",
]


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


class DeterministicLinker:
    """Extracts case/ticket IDs from window titles using regex patterns."""

    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = _compile_patterns(patterns or DEFAULT_PATTERNS)

    def extract_case_id_from_title(
        self,
        window_title: str,
        patterns: list[str] | None = None,
    ) -> str | None:
        """Extract the first case/ticket ID found in a window title.

        Args:
            window_title: Raw window title string from the desktop agent.
            patterns: Optional override list of regex patterns (replaces defaults).

        Returns:
            Matched case ID string, or None if no match found.
        """
        compiled = _compile_patterns(patterns) if patterns else self._patterns
        for pattern in compiled:
            match = pattern.search(window_title)
            if match:
                # For hash-prefixed patterns the ID is in group 1; otherwise the full match
                result = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                return result.upper()
        return None

    async def link_events_to_cases(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
        events: list[CanonicalActivityEvent],
    ) -> list[CaseLinkEdge]:
        """Create CaseLinkEdge records for events whose window titles contain a case ID.

        Args:
            session: Async database session.
            engagement_id: Engagement context for the new edges.
            events: Canonical events to process (should include raw_payload with window_title).

        Returns:
            List of newly created (and added to session) CaseLinkEdge records.
        """
        edges: list[CaseLinkEdge] = []

        for event in events:
            window_title: str | None = None
            if event.raw_payload and isinstance(event.raw_payload, dict):
                window_title = event.raw_payload.get("window_title")

            if not window_title:
                continue

            case_id = self.extract_case_id_from_title(window_title)
            if case_id is None:
                continue

            edge = CaseLinkEdge(
                id=uuid.uuid4(),
                engagement_id=engagement_id,
                event_id=event.id,
                case_id=case_id,
                method="deterministic",
                confidence=1.0,
                explainability={"window_title": window_title, "extracted_id": case_id},
            )
            session.add(edge)
            edges.append(edge)

        if edges:
            logger.info(
                "DeterministicLinker: created %d edges for engagement %s",
                len(edges),
                engagement_id,
            )

        return edges
