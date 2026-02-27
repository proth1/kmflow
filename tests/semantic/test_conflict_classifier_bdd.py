"""BDD tests for Three-Way Distinction Classifier (Story #384).

Covers 4 acceptance scenarios:
1. Naming variant detected and entities merged
2. Temporal shift detected from non-overlapping effective dates
3. Genuine disagreement preserves both views with epistemic frames
4. ConflictObject updated with resolution metadata

Plus unit tests for idempotency, batch classification, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import (
    ConflictObject,
    MismatchType,
    ResolutionStatus,
    ResolutionType,
    SeedTerm,
)
from src.semantic.conflict_classifier import (
    CLASSIFIER_VERSION,
    ThreeWayDistinctionClassifier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = uuid.uuid4()
SOURCE_A = uuid.uuid4()
SOURCE_B = uuid.uuid4()


def _make_conflict(
    mismatch_type: MismatchType = MismatchType.SEQUENCE_MISMATCH,
    source_a: uuid.UUID | None = None,
    source_b: uuid.UUID | None = None,
) -> ConflictObject:
    """Create a mock ConflictObject for testing."""
    obj = MagicMock(spec=ConflictObject)
    obj.id = uuid.uuid4()
    obj.engagement_id = ENGAGEMENT_ID
    obj.mismatch_type = mismatch_type
    obj.source_a_id = source_a or SOURCE_A
    obj.source_b_id = source_b or SOURCE_B
    obj.severity = 0.7
    obj.resolution_type = None
    obj.resolution_status = ResolutionStatus.UNRESOLVED
    obj.resolution_details = None
    obj.resolution_notes = None
    obj.classified_at = None
    obj.classifier_version = None
    obj.resolved_at = None
    obj.escalation_flag = False
    return obj


def _make_graph_service() -> MagicMock:
    """Create a mock graph service."""
    svc = MagicMock()
    svc.run_query = AsyncMock(return_value=[])
    svc.run_write_query = AsyncMock(return_value=[])
    return svc


def _make_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)
    session.flush = AsyncMock()
    return session


# ===========================================================================
# Scenario 1: Naming variant detected and entities merged
# ===========================================================================


class TestScenario1NamingVariant:
    """Naming variant detection via seed list and entity merging."""

    @pytest.mark.asyncio
    async def test_naming_variant_detected(self) -> None:
        """Given 'Credit Check' and 'Creditworthiness Assessment' with seed list alias,
        When the classifier runs,
        Then resolution_type=NAMING_VARIANT is assigned."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        # Graph read returns two different activity names
        graph.run_query = AsyncMock(
            side_effect=[
                # _get_conflicting_names
                [
                    {"name": "Credit Check", "source_id": str(SOURCE_A)},
                    {"name": "Creditworthiness Assessment", "source_id": str(SOURCE_B)},
                ],
            ]
        )
        # Graph write for _merge_graph_nodes
        graph.run_write_query = AsyncMock(return_value=[])

        # Seed list has "Credit Check" as canonical
        seed = MagicMock(spec=SeedTerm)
        seed.term = "Credit Check"
        seed_result = MagicMock()
        seed_result.scalars.return_value.all.return_value = [seed]
        session.execute = AsyncMock(return_value=seed_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_type == ResolutionType.NAMING_VARIANT
        assert result.resolution_status == ResolutionStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_entities_merged_with_canonical_name(self) -> None:
        """Two activity nodes are merged using seed list canonical name."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(
            side_effect=[
                [
                    {"name": "Credit Check", "source_id": str(SOURCE_A)},
                    {"name": "Creditworthiness Assessment", "source_id": str(SOURCE_B)},
                ],
            ]
        )
        graph.run_write_query = AsyncMock(return_value=[])

        seed = MagicMock(spec=SeedTerm)
        seed.term = "Credit Check"
        seed_result = MagicMock()
        seed_result.scalars.return_value.all.return_value = [seed]
        session.execute = AsyncMock(return_value=seed_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_details is not None
        assert result.resolution_details["canonical_name"] == "Credit Check"
        assert "Creditworthiness Assessment" in result.resolution_details["merged_from"]

    @pytest.mark.asyncio
    async def test_conflict_status_resolved_after_naming_variant(self) -> None:
        """ConflictObject status updated to resolved with resolution details."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(
            side_effect=[
                [
                    {"name": "Credit Check", "source_id": str(SOURCE_A)},
                    {"name": "Creditworthiness Assessment", "source_id": str(SOURCE_B)},
                ],
            ]
        )
        graph.run_write_query = AsyncMock(return_value=[])

        seed = MagicMock(spec=SeedTerm)
        seed.term = "Credit Check"
        seed_result = MagicMock()
        seed_result.scalars.return_value.all.return_value = [seed]
        session.execute = AsyncMock(return_value=seed_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_status == ResolutionStatus.RESOLVED
        assert result.resolved_at is not None
        assert "merge" in str(result.resolution_details.get("resolution_note", "")).lower()


# ===========================================================================
# Scenario 2: Temporal shift detected from non-overlapping effective dates
# ===========================================================================


class TestScenario2TemporalShift:
    """Temporal shift detection from non-overlapping effective dates."""

    @pytest.mark.asyncio
    async def test_temporal_shift_detected(self) -> None:
        """Given non-overlapping effective dates,
        When the classifier runs,
        Then resolution_type=TEMPORAL_SHIFT is assigned."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        # Read queries: _get_conflicting_names, _get_effective_dates
        graph.run_query = AsyncMock(
            side_effect=[
                # _get_conflicting_names - return only one name (no naming variant)
                [{"name": "Activity A", "source_id": str(SOURCE_A)}],
                # _get_effective_dates
                [
                    {
                        "source_id": str(SOURCE_A),
                        "effective_from": datetime(2022, 1, 1, tzinfo=UTC),
                        "effective_to": datetime(2023, 12, 31, tzinfo=UTC),
                    },
                    {
                        "source_id": str(SOURCE_B),
                        "effective_from": datetime(2024, 1, 1, tzinfo=UTC),
                        "effective_to": None,
                    },
                ],
            ]
        )
        # Write queries: _set_bitemporal_validity (2 calls)
        graph.run_write_query = AsyncMock(return_value=[])

        # No seed term match
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_type == ResolutionType.TEMPORAL_SHIFT

    @pytest.mark.asyncio
    async def test_bitemporal_validity_set(self) -> None:
        """Bitemporal validity ranges set on conflicting edges."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(
            side_effect=[
                [{"name": "Activity A", "source_id": str(SOURCE_A)}],
                [
                    {
                        "source_id": str(SOURCE_A),
                        "effective_from": datetime(2022, 1, 1, tzinfo=UTC),
                        "effective_to": datetime(2023, 12, 31, tzinfo=UTC),
                    },
                    {
                        "source_id": str(SOURCE_B),
                        "effective_from": datetime(2024, 1, 1, tzinfo=UTC),
                        "effective_to": None,
                    },
                ],
            ]
        )
        graph.run_write_query = AsyncMock(return_value=[])

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_details is not None
        assert result.resolution_details["source_a_range"]["from"] == "2022-01-01"
        assert result.resolution_details["source_b_range"]["from"] == "2024-01-01"

    @pytest.mark.asyncio
    async def test_both_views_preserved(self) -> None:
        """Both views preserved in the graph with validity ranges."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(
            side_effect=[
                [{"name": "A", "source_id": str(SOURCE_A)}],
                [
                    {
                        "source_id": str(SOURCE_A),
                        "effective_from": datetime(2022, 1, 1, tzinfo=UTC),
                        "effective_to": datetime(2023, 12, 31, tzinfo=UTC),
                    },
                    {
                        "source_id": str(SOURCE_B),
                        "effective_from": datetime(2024, 1, 1, tzinfo=UTC),
                        "effective_to": None,
                    },
                ],
            ]
        )
        graph.run_write_query = AsyncMock(return_value=[])

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_status == ResolutionStatus.RESOLVED
        assert "preserved" in result.resolution_details.get("resolution_note", "").lower()


# ===========================================================================
# Scenario 3: Genuine disagreement preserves both views with epistemic frames
# ===========================================================================


class TestScenario3GenuineDisagreement:
    """Genuine disagreement preserves both views with epistemic frame tagging."""

    @pytest.mark.asyncio
    async def test_genuine_disagreement_assigned(self) -> None:
        """Given no naming variants and no effective dates,
        When the classifier runs,
        Then resolution_type=GENUINE_DISAGREEMENT is assigned."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        # All graph queries return empty (no naming variant, no temporal data)
        graph.run_query = AsyncMock(return_value=[])

        # No seed term match
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_type == ResolutionType.GENUINE_DISAGREEMENT

    @pytest.mark.asyncio
    async def test_status_remains_open_for_sme_review(self) -> None:
        """Genuine disagreement status remains UNRESOLVED for SME review."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_status == ResolutionStatus.UNRESOLVED
        assert result.resolved_at is None

    @pytest.mark.asyncio
    async def test_epistemic_frames_tagged(self) -> None:
        """Each view tagged with source's epistemic frame."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        call_count = 0

        async def _mock_query(query: str, params: dict) -> list:
            nonlocal call_count
            call_count += 1
            # _get_conflicting_names (empty → skip naming)
            if call_count == 1:
                return []
            # _get_effective_dates (empty → skip temporal)
            if call_count == 2:
                return []
            # _get_epistemic_frames
            if call_count == 3:
                return [
                    {"source_id": str(SOURCE_A), "frame": "documentary", "evidence_type": "policy_document"},
                    {"source_id": str(SOURCE_B), "frame": "testimonial", "evidence_type": "interview_transcript"},
                ]
            return []

        graph.run_query = AsyncMock(side_effect=_mock_query)
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_details is not None
        frames = result.resolution_details.get("conflicting_frames", [])
        assert len(frames) == 2
        frame_types = [f["frame"] for f in frames]
        assert "documentary" in frame_types
        assert "testimonial" in frame_types

    @pytest.mark.asyncio
    async def test_requires_sme_review_flag(self) -> None:
        """Resolution details include requires_sme_review=True."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.resolution_details["requires_sme_review"] is True


# ===========================================================================
# Scenario 4: ConflictObject updated with resolution metadata
# ===========================================================================


class TestScenario4ResolutionMetadata:
    """ConflictObject updated with resolution_type, resolution_details,
    classified_at, and classifier_version."""

    @pytest.mark.asyncio
    async def test_classified_at_timestamp_set(self) -> None:
        """classified_at timestamp is set on classification."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        before = datetime.now(UTC)
        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)
        after = datetime.now(UTC)

        assert result.classified_at is not None
        assert before <= result.classified_at <= after

    @pytest.mark.asyncio
    async def test_classifier_version_set(self) -> None:
        """classifier_version is set for auditability."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert result.classifier_version == CLASSIFIER_VERSION

    @pytest.mark.asyncio
    async def test_resolution_details_is_json_dict(self) -> None:
        """resolution_details is a JSON-serializable dict."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)
        result = await classifier.classify(conflict)

        assert isinstance(result.resolution_details, dict)


# ===========================================================================
# Idempotency tests
# ===========================================================================


class TestIdempotency:
    """Re-classifying the same ConflictObject produces the same result."""

    @pytest.mark.asyncio
    async def test_idempotent_classification(self) -> None:
        """Classifying twice produces the same resolution_type."""
        conflict = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        classifier = ThreeWayDistinctionClassifier(graph, session)

        result1 = await classifier.classify(conflict)
        type1 = result1.resolution_type

        # Reset for re-classification
        conflict.resolution_type = None
        conflict.classified_at = None

        result2 = await classifier.classify(conflict)
        type2 = result2.resolution_type

        assert type1 == type2


# ===========================================================================
# Batch classification tests
# ===========================================================================


class TestBatchClassification:
    """Batch classification of all unclassified ConflictObjects for an engagement."""

    @pytest.mark.asyncio
    async def test_batch_classifies_unresolved_conflicts(self) -> None:
        """classify_batch processes all unclassified conflicts."""
        conflict1 = _make_conflict()
        conflict2 = _make_conflict()
        graph = _make_graph_service()
        session = _make_session()

        graph.run_query = AsyncMock(return_value=[])

        # Session returns 2 unclassified conflicts
        batch_result = MagicMock()
        batch_result.scalars.return_value.all.return_value = [conflict1, conflict2]

        # Seed lookup returns empty
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[batch_result, empty_result, empty_result])

        classifier = ThreeWayDistinctionClassifier(graph, session)
        results = await classifier.classify_batch(ENGAGEMENT_ID)

        assert len(results) == 2
        for r in results:
            assert r.resolution_type is not None

    @pytest.mark.asyncio
    async def test_batch_empty_engagement(self) -> None:
        """classify_batch with no unclassified conflicts returns empty list."""
        graph = _make_graph_service()
        session = _make_session()

        classifier = ThreeWayDistinctionClassifier(graph, session)
        results = await classifier.classify_batch(ENGAGEMENT_ID)

        assert results == []
        session.flush.assert_not_called()


# ===========================================================================
# Model field tests
# ===========================================================================


class TestModelFields:
    """Verify new ConflictObject fields exist."""

    def test_resolution_details_field(self) -> None:
        assert hasattr(ConflictObject, "resolution_details")

    def test_classified_at_field(self) -> None:
        assert hasattr(ConflictObject, "classified_at")

    def test_classifier_version_field(self) -> None:
        assert hasattr(ConflictObject, "classifier_version")

    def test_classifier_version_constant(self) -> None:
        assert CLASSIFIER_VERSION == "1.0.0"
