"""Tests for the POV generator pipeline (end-to-end)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.core.models import ProcessModelStatus
from src.pov.generator import GenerationResult, generate_pov


def _make_evidence_item(
    engagement_id: str,
    category: str = "documents",
    name: str = "test_doc.pdf",
    quality_score: float = 0.7,
    freshness_score: float = 0.8,
    reliability_score: float = 0.75,
):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.engagement_id = uuid.UUID(engagement_id)
    item.category = category
    item.name = name
    item.fragments = []
    item.duplicate_of_id = None
    type(item).quality_score = PropertyMock(return_value=quality_score)
    item.freshness_score = freshness_score
    item.reliability_score = reliability_score
    item.completeness_score = 0.6
    item.consistency_score = 0.65
    item.source_date = None
    item.metadata_json = None
    return item


def _make_fragment(evidence_id=None, content="The Finance Manager must Submit Request for approval."):
    frag = MagicMock()
    frag.id = uuid.uuid4()
    frag.evidence_id = evidence_id or uuid.uuid4()
    frag.content = content
    return frag


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


class TestGeneratePov:
    """Tests for the generate_pov orchestration function."""

    @pytest.mark.asyncio
    async def test_returns_generation_result(self, mock_session):
        """generate_pov returns a GenerationResult."""
        eng_id = str(uuid.uuid4())

        # Mock aggregation to return empty evidence
        with patch("src.pov.generator.aggregate_evidence") as mock_agg:
            mock_agg.return_value = MagicMock(
                evidence_count=0,
                fragment_count=0,
                evidence_items=[],
                fragments=[],
            )

            result = await generate_pov(mock_session, eng_id)

        assert isinstance(result, GenerationResult)
        assert result.process_model is not None

    @pytest.mark.asyncio
    async def test_fails_with_no_evidence(self, mock_session):
        """generate_pov fails gracefully when no evidence found."""
        eng_id = str(uuid.uuid4())

        with patch("src.pov.generator.aggregate_evidence") as mock_agg:
            mock_agg.return_value = MagicMock(
                evidence_count=0,
                fragment_count=0,
                evidence_items=[],
                fragments=[],
            )

            result = await generate_pov(mock_session, eng_id)

        assert result.success is False
        assert "No validated evidence" in result.error
        assert result.process_model.status == ProcessModelStatus.FAILED

    @pytest.mark.asyncio
    async def test_fails_with_no_entities(self, mock_session):
        """generate_pov fails when extraction yields no entities."""
        eng_id = str(uuid.uuid4())
        item = _make_evidence_item(eng_id)
        frag = _make_fragment(item.id, content="No extractable entities here just plain text.")
        item.fragments = [frag]

        with (
            patch("src.pov.generator.aggregate_evidence") as mock_agg,
            patch("src.pov.generator.extract_from_evidence") as mock_extract,
        ):
            mock_agg.return_value = MagicMock(
                evidence_count=1,
                fragment_count=1,
                evidence_items=[item],
                fragments=[frag],
            )
            mock_extract.return_value = MagicMock(
                entities=[],
                raw_entity_count=0,
                entity_to_evidence={},
                entity_to_fragments={},
            )

            result = await generate_pov(mock_session, eng_id)

        assert result.success is False
        assert "No entities" in result.error

    @pytest.mark.asyncio
    async def test_successful_generation(self, mock_session):
        """generate_pov succeeds with valid evidence and entities."""
        eng_id = str(uuid.uuid4())
        item = _make_evidence_item(eng_id)
        frag = _make_fragment(item.id)
        item.fragments = [frag]

        from src.semantic.entity_extraction import EntityType, ExtractedEntity

        entity = ExtractedEntity(
            id="ent_submit",
            entity_type=EntityType.ACTIVITY,
            name="Submit Request",
            confidence=0.7,
        )

        with (
            patch("src.pov.generator.aggregate_evidence") as mock_agg,
            patch("src.pov.generator.extract_from_evidence") as mock_extract,
        ):
            mock_agg.return_value = MagicMock(
                evidence_count=1,
                fragment_count=1,
                evidence_items=[item],
                fragments=[frag],
            )
            mock_extract.return_value = MagicMock(
                entities=[entity],
                raw_entity_count=1,
                entity_to_evidence={entity.id: [str(item.id)]},
                entity_to_fragments={entity.id: [str(frag.id)]},
            )

            result = await generate_pov(mock_session, eng_id)

        assert result.success is True
        assert result.process_model is not None
        assert result.process_model.status == ProcessModelStatus.COMPLETED
        assert result.process_model.bpmn_xml is not None
        assert result.process_model.element_count > 0
        assert result.stats["elements"] > 0

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, mock_session):
        """generate_pov catches exceptions and returns failure."""
        eng_id = str(uuid.uuid4())

        with patch("src.pov.generator.aggregate_evidence") as mock_agg:
            mock_agg.side_effect = RuntimeError("Database connection lost")

            result = await generate_pov(mock_session, eng_id)

        assert result.success is False
        assert "Database connection lost" in result.error
        assert result.process_model.status == ProcessModelStatus.FAILED

    @pytest.mark.asyncio
    async def test_uses_scope_parameter(self, mock_session):
        """generate_pov passes scope to aggregation."""
        eng_id = str(uuid.uuid4())

        with patch("src.pov.generator.aggregate_evidence") as mock_agg:
            mock_agg.return_value = MagicMock(
                evidence_count=0,
                evidence_items=[],
                fragments=[],
                fragment_count=0,
            )

            await generate_pov(mock_session, eng_id, scope="procurement")

        # Verify scope was passed (None because "all" is the default,
        # but "procurement" != "all" so it should be passed as-is)
        mock_agg.assert_called_once()
        call_kwargs = mock_agg.call_args
        assert call_kwargs[1].get("scope") == "procurement" or call_kwargs[0][2] == "procurement"

    @pytest.mark.asyncio
    async def test_model_persisted_with_metadata(self, mock_session):
        """generate_pov stores metadata on the process model."""
        eng_id = str(uuid.uuid4())
        item = _make_evidence_item(eng_id)
        frag = _make_fragment(item.id)
        item.fragments = [frag]

        from src.semantic.entity_extraction import EntityType, ExtractedEntity

        entity = ExtractedEntity(
            id="ent_review",
            entity_type=EntityType.ACTIVITY,
            name="Review Invoice",
            confidence=0.8,
        )

        with (
            patch("src.pov.generator.aggregate_evidence") as mock_agg,
            patch("src.pov.generator.extract_from_evidence") as mock_extract,
        ):
            mock_agg.return_value = MagicMock(
                evidence_count=1,
                fragment_count=1,
                evidence_items=[item],
                fragments=[frag],
            )
            mock_extract.return_value = MagicMock(
                entities=[entity],
                raw_entity_count=1,
                entity_to_evidence={entity.id: [str(item.id)]},
                entity_to_fragments={entity.id: [str(frag.id)]},
            )

            result = await generate_pov(mock_session, eng_id)

        model = result.process_model
        assert model.metadata_json is not None
        assert "overall_confidence_level" in model.metadata_json
        assert "element_count" in model.metadata_json
        assert model.generated_at is not None
