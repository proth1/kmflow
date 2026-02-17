"""Tests for evidence aggregation (LCD Step 1)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.pov.aggregation import AggregatedEvidence, aggregate_evidence


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    return session


def _make_evidence_item(
    engagement_id: str,
    category: str = "documents",
    name: str = "test_doc.pdf",
    validation_status: str = "validated",
    fragments: list | None = None,
):
    """Create a mock evidence item."""
    item = MagicMock()
    item.id = uuid.uuid4()
    item.engagement_id = uuid.UUID(engagement_id)
    item.category = category
    item.name = name
    item.validation_status = validation_status
    item.fragments = fragments or []
    item.duplicate_of_id = None
    item.quality_score = 0.7
    item.freshness_score = 0.8
    item.reliability_score = 0.75
    item.completeness_score = 0.6
    item.consistency_score = 0.65
    return item


def _make_fragment(evidence_id: str | None = None, content: str = "Test content"):
    """Create a mock evidence fragment."""
    frag = MagicMock()
    frag.id = uuid.uuid4()
    frag.evidence_id = uuid.UUID(evidence_id) if evidence_id else uuid.uuid4()
    frag.content = content
    return frag


class TestAggregateEvidence:
    """Tests for the aggregate_evidence function."""

    @pytest.mark.asyncio
    async def test_aggregate_returns_aggregated_evidence(self, mock_session):
        """aggregate_evidence returns AggregatedEvidence dataclass."""
        eng_id = str(uuid.uuid4())
        frag1 = _make_fragment(content="Fragment 1")
        item1 = _make_evidence_item(eng_id, fragments=[frag1])

        # Mock the query execution
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = [item1]
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await aggregate_evidence(mock_session, eng_id)

        assert isinstance(result, AggregatedEvidence)
        assert result.engagement_id == eng_id
        assert result.evidence_count == 1
        assert result.fragment_count == 1
        assert len(result.evidence_items) == 1
        assert len(result.fragments) == 1

    @pytest.mark.asyncio
    async def test_aggregate_empty_engagement(self, mock_session):
        """aggregate_evidence with no evidence returns empty result."""
        eng_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = []
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await aggregate_evidence(mock_session, eng_id)

        assert result.evidence_count == 0
        assert result.fragment_count == 0

    @pytest.mark.asyncio
    async def test_aggregate_multiple_items_multiple_fragments(self, mock_session):
        """aggregate_evidence collects fragments from multiple items."""
        eng_id = str(uuid.uuid4())
        frag1 = _make_fragment(content="Fragment A")
        frag2 = _make_fragment(content="Fragment B")
        frag3 = _make_fragment(content="Fragment C")
        item1 = _make_evidence_item(eng_id, fragments=[frag1, frag2])
        item2 = _make_evidence_item(eng_id, fragments=[frag3])

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = [item1, item2]
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await aggregate_evidence(mock_session, eng_id)

        assert result.evidence_count == 2
        assert result.fragment_count == 3

    @pytest.mark.asyncio
    async def test_aggregate_with_scope_filter(self, mock_session):
        """aggregate_evidence passes scope filter."""
        eng_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = []
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await aggregate_evidence(mock_session, eng_id, scope="documents")

        assert result.scope == "documents"
        # Verify the query was executed (scope filter was applied)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggregate_default_scope(self, mock_session):
        """aggregate_evidence uses 'all' scope when none specified."""
        eng_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_unique = MagicMock()
        mock_unique.all.return_value = []
        mock_scalars.unique.return_value = mock_unique
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await aggregate_evidence(mock_session, eng_id)

        assert result.scope == "all"
