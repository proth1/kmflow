"""Tests for evidence lineage service.

Tests cover: lineage creation, transformation appending, chain retrieval.
Uses mock SQLAlchemy sessions to avoid database dependency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.datalake.lineage import (
    append_transformation,
    create_lineage_record,
    get_lineage_chain,
)


def _make_evidence_item(
    item_id: uuid.UUID | None = None,
    name: str = "test.pdf",
) -> MagicMock:
    """Create a mock EvidenceItem."""
    item = MagicMock()
    item.id = item_id or uuid.uuid4()
    item.name = name
    item.created_at = datetime.now(UTC)
    item.lineage_id = None
    item.source_system = None
    return item


def _make_session(existing_lineage=None) -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()

    # Mock the execute method for SELECT queries
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_lineage
    result.scalars.return_value.all.return_value = (
        [existing_lineage] if existing_lineage else []
    )
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()

    return session


class TestCreateLineageRecord:
    """Test lineage record creation."""

    @pytest.mark.asyncio
    async def test_creates_lineage_for_new_item(self) -> None:
        session = _make_session(existing_lineage=None)
        item = _make_evidence_item()

        lineage = await create_lineage_record(
            session=session,
            evidence_item=item,
            source_system="direct_upload",
            content_hash="abc123",
        )

        # Should have called session.add
        session.add.assert_called_once()
        session.flush.assert_called_once()

        # Should have linked lineage to evidence item
        assert item.source_system == "direct_upload"

    @pytest.mark.asyncio
    async def test_creates_with_custom_source(self) -> None:
        session = _make_session(existing_lineage=None)
        item = _make_evidence_item()

        await create_lineage_record(
            session=session,
            evidence_item=item,
            source_system="salesforce",
            source_url="https://salesforce.com/files/123",
            source_identifier="SF-FILE-123",
        )

        assert item.source_system == "salesforce"
        session.add.assert_called_once()


class TestAppendTransformation:
    """Test transformation chain appending."""

    @pytest.mark.asyncio
    async def test_appends_step_to_chain(self) -> None:
        lineage = MagicMock()
        lineage.id = uuid.uuid4()
        lineage.transformation_chain = [
            {"step": "ingestion", "action": "uploaded"},
        ]

        session = _make_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = lineage
        session.execute = AsyncMock(return_value=result)

        updated = await append_transformation(
            session=session,
            lineage_id=lineage.id,
            step_name="entity_extraction",
            details={"entities_found": 5},
        )

        assert len(updated.transformation_chain) == 2
        assert updated.transformation_chain[1]["step"] == "entity_extraction"
        assert updated.transformation_chain[1]["entities_found"] == 5

    @pytest.mark.asyncio
    async def test_raises_on_missing_lineage(self) -> None:
        session = _make_session(existing_lineage=None)

        with pytest.raises(ValueError, match="not found"):
            await append_transformation(
                session=session,
                lineage_id=uuid.uuid4(),
                step_name="test",
            )


class TestGetLineageChain:
    """Test lineage chain retrieval."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_lineage(self) -> None:
        session = _make_session(existing_lineage=None)

        chain = await get_lineage_chain(session, uuid.uuid4())
        assert chain == []
