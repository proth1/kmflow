"""Tests for the evidence deduplication module (src/evidence/dedup.py).

Covers find_duplicates_by_hash, check_is_duplicate, get_duplicate_groups,
and edge cases with no duplicates and multiple groups.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.evidence.dedup import (
    check_is_duplicate,
    find_duplicates_by_hash,
    get_duplicate_groups,
)


@pytest.fixture
def engagement_id() -> uuid.UUID:
    """A fixed engagement UUID for test consistency."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# find_duplicates_by_hash
# ---------------------------------------------------------------------------


class TestFindDuplicatesByHash:
    """Tests for hash-based duplicate detection."""

    @pytest.mark.asyncio
    async def test_find_duplicates_returns_matching_items(self, engagement_id: uuid.UUID) -> None:
        """Should return evidence items with the same content hash."""
        item1 = MagicMock()
        item1.id = uuid.uuid4()
        item1.content_hash = "abc123"

        item2 = MagicMock()
        item2.id = uuid.uuid4()
        item2.content_hash = "abc123"

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [item1, item2]
        session.execute = AsyncMock(return_value=mock_result)

        results = await find_duplicates_by_hash(
            session=session,
            content_hash="abc123",
            engagement_id=engagement_id,
        )

        assert len(results) == 2
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_find_duplicates_excludes_specified_id(self, engagement_id: uuid.UUID) -> None:
        """Should exclude the specified evidence item from results."""
        exclude_id = uuid.uuid4()

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        results = await find_duplicates_by_hash(
            session=session,
            content_hash="abc123",
            engagement_id=engagement_id,
            exclude_id=exclude_id,
        )

        assert results == []
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_find_duplicates_no_matches(self, engagement_id: uuid.UUID) -> None:
        """Should return empty list when no duplicates exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        results = await find_duplicates_by_hash(
            session=session,
            content_hash="unique-hash",
            engagement_id=engagement_id,
        )

        assert results == []


# ---------------------------------------------------------------------------
# check_is_duplicate
# ---------------------------------------------------------------------------


class TestCheckIsDuplicate:
    """Tests for single-item duplicate check."""

    @pytest.mark.asyncio
    async def test_check_is_duplicate_found(self, engagement_id: uuid.UUID) -> None:
        """Should return the UUID of existing evidence when hash matches."""
        existing_id = uuid.uuid4()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_id
        session.execute = AsyncMock(return_value=mock_result)

        result = await check_is_duplicate(
            session=session,
            content_hash="dup-hash",
            engagement_id=engagement_id,
        )

        assert result == existing_id

    @pytest.mark.asyncio
    async def test_check_is_duplicate_not_found(self, engagement_id: uuid.UUID) -> None:
        """Should return None when hash does not exist."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await check_is_duplicate(
            session=session,
            content_hash="new-hash",
            engagement_id=engagement_id,
        )

        assert result is None


# ---------------------------------------------------------------------------
# get_duplicate_groups
# ---------------------------------------------------------------------------


class TestGetDuplicateGroups:
    """Tests for grouping duplicates across an engagement."""

    @pytest.mark.asyncio
    async def test_get_duplicate_groups_with_duplicates(self, engagement_id: uuid.UUID) -> None:
        """Should return groups of 2+ items sharing a hash."""
        id1, id2, id3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        # Simulate rows: (content_hash, item_id)
        rows = [
            ("hash-a", id1),
            ("hash-a", id2),
            ("hash-b", id3),  # only one item -> not a duplicate group
        ]

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(rows))
        session.execute = AsyncMock(return_value=mock_result)

        groups = await get_duplicate_groups(
            session=session,
            engagement_id=engagement_id,
        )

        assert "hash-a" in groups
        assert len(groups["hash-a"]) == 2
        assert id1 in groups["hash-a"]
        assert id2 in groups["hash-a"]
        # hash-b has only 1 item, should not appear
        assert "hash-b" not in groups

    @pytest.mark.asyncio
    async def test_get_duplicate_groups_no_duplicates(self, engagement_id: uuid.UUID) -> None:
        """Should return empty dict when no duplicates exist."""
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        rows = [
            ("hash-a", id1),
            ("hash-b", id2),
        ]

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(rows))
        session.execute = AsyncMock(return_value=mock_result)

        groups = await get_duplicate_groups(
            session=session,
            engagement_id=engagement_id,
        )

        assert groups == {}

    @pytest.mark.asyncio
    async def test_get_duplicate_groups_multiple_groups(self, engagement_id: uuid.UUID) -> None:
        """Should return multiple groups when several hashes have duplicates."""
        ids = [uuid.uuid4() for _ in range(5)]
        rows = [
            ("hash-x", ids[0]),
            ("hash-x", ids[1]),
            ("hash-y", ids[2]),
            ("hash-y", ids[3]),
            ("hash-y", ids[4]),
        ]

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(rows))
        session.execute = AsyncMock(return_value=mock_result)

        groups = await get_duplicate_groups(
            session=session,
            engagement_id=engagement_id,
        )

        assert len(groups) == 2
        assert len(groups["hash-x"]) == 2
        assert len(groups["hash-y"]) == 3
