"""Tests for RoleAssociator: role-cohort aggregation of unlinked events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX, RoleAssociator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    performer_role_ref: str | None = None,
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    event = MagicMock(spec=CanonicalActivityEvent)
    event.id = uuid.uuid4()
    event.engagement_id = engagement_id or uuid.uuid4()
    event.performer_role_ref = performer_role_ref
    event.timestamp_utc = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    return event


def _build_session(linked_ids: list[uuid.UUID], unlinked_events: list[MagicMock]) -> AsyncMock:
    """Build a mock session where:
    - First execute() returns linked_ids (subquery for existing CaseLinkEdge.event_ids)
    - Second execute() returns unlinked_events
    """
    session = AsyncMock()
    session.add = MagicMock()

    # First call: select(CaseLinkEdge.event_id) — return linked event ids
    linked_result = MagicMock()
    linked_result.scalars.return_value.all.return_value = linked_ids

    # Second call: select(CanonicalActivityEvent) — return unlinked events
    unlinked_result = MagicMock()
    unlinked_result.scalars.return_value.all.return_value = unlinked_events

    session.execute = AsyncMock(side_effect=[linked_result, unlinked_result])
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoleAssociator:
    def setup_method(self) -> None:
        self.assoc = RoleAssociator()
        self.engagement_id = uuid.uuid4()

    @pytest.mark.asyncio
    async def test_associate_unlinked_events(self) -> None:
        """Unlinked events get role-aggregate CaseLinkEdge records."""
        event_a = _make_event("analyst", self.engagement_id)
        event_b = _make_event("manager", self.engagement_id)

        session = _build_session(linked_ids=[], unlinked_events=[event_a, event_b])

        count = await self.assoc.associate_unlinked(session, self.engagement_id)

        assert count == 2
        assert session.add.call_count == 2

        edges: list[CaseLinkEdge] = [call.args[0] for call in session.add.call_args_list]
        case_ids = {e.case_id for e in edges}
        assert f"{ROLE_AGGREGATE_PREFIX}:analyst" in case_ids
        assert f"{ROLE_AGGREGATE_PREFIX}:manager" in case_ids

        for edge in edges:
            assert edge.method == "role_aggregate"
            assert edge.confidence == 0.0
            assert edge.engagement_id == self.engagement_id

    @pytest.mark.asyncio
    async def test_unknown_role_fallback(self) -> None:
        """Events with no performer_role_ref use 'unknown_role' in the synthetic case_id."""
        event = _make_event(None, self.engagement_id)

        session = _build_session(linked_ids=[], unlinked_events=[event])

        count = await self.assoc.associate_unlinked(session, self.engagement_id)

        assert count == 1
        edge: CaseLinkEdge = session.add.call_args.args[0]
        assert edge.case_id == f"{ROLE_AGGREGATE_PREFIX}:unknown_role"
        assert edge.explainability["role"] == "unknown_role"

    @pytest.mark.asyncio
    async def test_no_unlinked_events(self) -> None:
        """Returns 0 and makes no session.add calls when all events are linked."""
        session = _build_session(linked_ids=[], unlinked_events=[])

        count = await self.assoc.associate_unlinked(session, self.engagement_id)

        assert count == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_explainability_reason_populated(self) -> None:
        """Edge explainability includes reason field."""
        event = _make_event("consultant", self.engagement_id)
        session = _build_session(linked_ids=[], unlinked_events=[event])

        await self.assoc.associate_unlinked(session, self.engagement_id)

        edge: CaseLinkEdge = session.add.call_args.args[0]
        assert edge.explainability["reason"] == "no_deterministic_or_assisted_match"
