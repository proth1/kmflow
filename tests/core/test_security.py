"""Tests for engagement-level data isolation (src/core/security.py).

Covers get_accessible_engagement_ids and filter_by_engagement_access.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from src.core.models import EvidenceItem, User, UserRole
from src.core.security import filter_by_engagement_access, get_accessible_engagement_ids


def _make_user(role: UserRole = UserRole.PROCESS_ANALYST) -> User:
    """Create a test User object."""
    return User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        role=role,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# get_accessible_engagement_ids
# ---------------------------------------------------------------------------


class TestGetAccessibleEngagementIds:
    """Tests for get_accessible_engagement_ids."""

    @pytest.mark.asyncio
    async def test_admin_returns_empty(self) -> None:
        """Platform admin should get empty list (no filtering needed)."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        session = AsyncMock()
        result = await get_accessible_engagement_ids(session, admin)
        assert result == []
        # Should not query the database
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_regular_user_queries_memberships(self) -> None:
        """Non-admin should query engagement_members for their engagements."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        eng_id_1 = uuid.uuid4()
        eng_id_2 = uuid.uuid4()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [eng_id_1, eng_id_2]
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_accessible_engagement_ids(session, user)
        assert result == [eng_id_1, eng_id_2]
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_with_no_engagements(self) -> None:
        """User with no memberships should get empty list."""
        user = _make_user(UserRole.PROCESS_ANALYST)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        result = await get_accessible_engagement_ids(session, user)
        assert result == []


# ---------------------------------------------------------------------------
# filter_by_engagement_access
# ---------------------------------------------------------------------------


class TestFilterByEngagementAccess:
    """Tests for filter_by_engagement_access."""

    def test_admin_query_unchanged(self) -> None:
        """Platform admin should get the query unchanged."""
        admin = _make_user(UserRole.PLATFORM_ADMIN)
        query = select(EvidenceItem)

        filtered = filter_by_engagement_access(query, admin, [], EvidenceItem.engagement_id)
        # For admin, the query should be returned unchanged
        # We compare the string representation to check no WHERE was added
        assert "WHERE" not in str(filtered.compile(compile_kwargs={"literal_binds": True}))

    def test_regular_user_gets_filtered_query(self) -> None:
        """Non-admin should get a WHERE IN clause added."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        eng_id = uuid.uuid4()
        query = select(EvidenceItem)

        filtered = filter_by_engagement_access(query, user, [eng_id], EvidenceItem.engagement_id)
        compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
        assert "WHERE" in compiled
        assert "IN" in compiled

    def test_empty_ids_returns_no_results(self) -> None:
        """Non-admin with empty IDs should produce an empty IN clause."""
        user = _make_user(UserRole.PROCESS_ANALYST)
        query = select(EvidenceItem)

        filtered = filter_by_engagement_access(query, user, [], EvidenceItem.engagement_id)
        compiled = str(filtered.compile(compile_kwargs={"literal_binds": True}))
        # Should still have a WHERE clause (even if IN is empty)
        assert "WHERE" in compiled
