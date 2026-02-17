"""Tests for TOMAlignmentEngine.

Validates TOM alignment analysis, gap detection, maturity scoring,
and gap prioritization functionality.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ProcessMaturity, TOMDimension, TOMGapType
from src.semantic.graph import GraphStats, KnowledgeGraphService
from src.tom.alignment import DIMENSION_WEIGHTS, MATURITY_SCORES, AlignmentResult, TOMAlignmentEngine


@pytest.fixture
def mock_graph():
    """Mock KnowledgeGraphService."""
    return AsyncMock(spec=KnowledgeGraphService)


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database queries."""
    return AsyncMock()


@pytest.fixture
def alignment_engine(mock_graph):
    """TOMAlignmentEngine instance with mocked graph service."""
    return TOMAlignmentEngine(mock_graph)


@pytest.fixture
def sample_tom():
    """Sample TOM with maturity targets."""
    tom = MagicMock()
    tom.id = uuid.uuid4()
    tom.maturity_targets = {
        TOMDimension.PROCESS_ARCHITECTURE: ProcessMaturity.OPTIMIZING,  # target 5.0
        TOMDimension.GOVERNANCE_STRUCTURES: ProcessMaturity.DEFINED,    # target 3.0
        TOMDimension.TECHNOLOGY_AND_DATA: ProcessMaturity.MANAGED,      # target 2.0
    }
    return tom


@pytest.mark.asyncio
async def test_run_alignment_finds_gaps(alignment_engine, mock_graph, mock_session, sample_tom):
    """Test run_alignment detects gaps when current maturity is low."""
    engagement_id = "eng-1"
    tom_id = str(sample_tom.id)

    # Mock TOM query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_tom
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock low graph stats (will result in low maturity scores)
    stats = GraphStats(
        node_count=5,
        relationship_count=3,
        nodes_by_label={"Process": 2},
        relationships_by_type={"SUPPORTED_BY": 3}
    )
    mock_graph.get_stats = AsyncMock(return_value=stats)

    # Execute
    result = await alignment_engine.run_alignment(mock_session, engagement_id, tom_id)

    # Assertions
    assert result.engagement_id == engagement_id
    assert result.tom_id == tom_id
    assert len(result.gaps) > 0  # Should detect gaps for all dimensions

    # Check that gaps were detected for the dimensions with targets
    gap_dimensions = {gap["dimension"] for gap in result.gaps}
    assert TOMDimension.PROCESS_ARCHITECTURE in gap_dimensions or TOMDimension.GOVERNANCE_STRUCTURES in gap_dimensions

    # Verify maturity scores were calculated
    assert len(result.maturity_scores) == len(TOMDimension)

    # Overall alignment should be < 100%
    assert result.overall_alignment < 100


@pytest.mark.asyncio
async def test_run_alignment_no_tom(alignment_engine, mock_graph, mock_session):
    """Test run_alignment when TOM is not found."""
    engagement_id = "eng-1"
    tom_id = str(uuid.uuid4())

    # Mock TOM not found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    result = await alignment_engine.run_alignment(mock_session, engagement_id, tom_id)

    # Assertions
    assert result.engagement_id == engagement_id
    assert result.tom_id == tom_id
    assert len(result.gaps) == 0
    assert len(result.maturity_scores) == 0
    assert result.overall_alignment == 0.0


@pytest.mark.asyncio
async def test_run_alignment_high_maturity(alignment_engine, mock_graph, mock_session, sample_tom):
    """Test run_alignment with high graph stats resulting in high maturity."""
    engagement_id = "eng-1"
    tom_id = str(sample_tom.id)

    # Lower the TOM targets for this test
    sample_tom.maturity_targets = {
        TOMDimension.PROCESS_ARCHITECTURE: ProcessMaturity.DEFINED,  # target 3.0
        TOMDimension.GOVERNANCE_STRUCTURES: ProcessMaturity.MANAGED,  # target 2.0
    }

    # Mock TOM query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_tom
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock high graph stats (will result in high maturity scores)
    stats = GraphStats(
        node_count=150,
        relationship_count=200,
        nodes_by_label={"Process": 50, "Activity": 30, "Policy": 10},
        relationships_by_type={"SUPPORTED_BY": 100}
    )
    mock_graph.get_stats = AsyncMock(return_value=stats)

    # Execute
    result = await alignment_engine.run_alignment(mock_session, engagement_id, tom_id)

    # Assertions
    assert result.engagement_id == engagement_id
    assert result.tom_id == tom_id

    # With high stats, maturity scores should be high (4.0+)
    assert result.maturity_scores[TOMDimension.PROCESS_ARCHITECTURE] >= 4.0

    # Overall alignment should be high
    assert result.overall_alignment > 50  # At least moderate alignment


def test_classify_gap_no_gap(alignment_engine):
    """Test gap classification when current >= target."""
    # Current equals target
    gap_type = alignment_engine._classify_gap(current=3.0, target=3.0)
    assert gap_type == TOMGapType.NO_GAP

    # Current exceeds target
    gap_type = alignment_engine._classify_gap(current=4.0, target=3.0)
    assert gap_type == TOMGapType.NO_GAP


def test_classify_gap_deviation(alignment_engine):
    """Test gap classification for small gaps (deviation)."""
    # Diff < 1.0
    gap_type = alignment_engine._classify_gap(current=2.5, target=3.0)
    assert gap_type == TOMGapType.DEVIATION

    gap_type = alignment_engine._classify_gap(current=2.1, target=3.0)
    assert gap_type == TOMGapType.DEVIATION


def test_classify_gap_partial(alignment_engine):
    """Test gap classification for partial gaps."""
    # 1.0 <= diff < 2.0
    gap_type = alignment_engine._classify_gap(current=2.0, target=3.0)
    assert gap_type == TOMGapType.PARTIAL_GAP

    gap_type = alignment_engine._classify_gap(current=2.5, target=4.0)
    assert gap_type == TOMGapType.PARTIAL_GAP


def test_classify_gap_full(alignment_engine):
    """Test gap classification for full gaps."""
    # diff >= 2.0
    gap_type = alignment_engine._classify_gap(current=1.0, target=3.0)
    assert gap_type == TOMGapType.FULL_GAP

    gap_type = alignment_engine._classify_gap(current=1.0, target=5.0)
    assert gap_type == TOMGapType.FULL_GAP


def test_calculate_priority(alignment_engine):
    """Test priority score calculation."""
    # Priority = severity * confidence * weight
    severity = 0.5
    confidence = 0.8
    dimension = TOMDimension.PROCESS_ARCHITECTURE
    weight = DIMENSION_WEIGHTS[dimension]  # 1.0

    priority = alignment_engine.calculate_priority(severity, confidence, dimension)

    expected = round(0.5 * 0.8 * weight, 4)
    assert priority == expected


def test_calculate_severity(alignment_engine):
    """Test severity calculation."""
    # Severity = (target - current) / 4.0, capped at 1.0

    # Normal case
    severity = alignment_engine._calculate_severity(current=2.0, target=4.0)
    assert severity == round(2.0 / 4.0, 4)

    # Capped at 1.0
    severity = alignment_engine._calculate_severity(current=1.0, target=5.0)
    assert severity == 1.0

    # Small gap
    severity = alignment_engine._calculate_severity(current=2.5, target=3.0)
    assert severity == round(0.5 / 4.0, 4)


@pytest.mark.asyncio
async def test_persist_gaps(alignment_engine, mock_session):
    """Test persisting gap analysis results to database."""
    # Create mock alignment result
    result = AlignmentResult(
        engagement_id="eng-1",
        tom_id="tom-1",
        gaps=[
            {
                "dimension": TOMDimension.PROCESS_ARCHITECTURE,
                "gap_type": TOMGapType.PARTIAL_GAP,
                "current_maturity": 2.0,
                "target_maturity": 3.5,
                "severity": 0.375,
                "confidence": 0.7,
                "priority_score": 0.2625,
            },
            {
                "dimension": TOMDimension.GOVERNANCE_STRUCTURES,
                "gap_type": TOMGapType.FULL_GAP,
                "current_maturity": 1.0,
                "target_maturity": 4.0,
                "severity": 0.75,
                "confidence": 0.6,
                "priority_score": 0.4275,
            },
        ],
    )

    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Execute
    persisted = await alignment_engine.persist_gaps(mock_session, result)

    # Assertions
    assert len(persisted) == 2
    assert mock_session.add.call_count == 2

    # Verify first gap
    first_gap = persisted[0]
    assert first_gap.engagement_id == "eng-1"
    assert first_gap.tom_id == "tom-1"
    assert first_gap.gap_type == TOMGapType.PARTIAL_GAP
    assert first_gap.dimension == TOMDimension.PROCESS_ARCHITECTURE
    assert first_gap.severity == 0.375
    assert first_gap.confidence == 0.7

    # Verify session.flush was called
    mock_session.flush.assert_called_once()


def test_dimension_weights():
    """Test that all dimensions have weights defined."""
    for dimension in TOMDimension:
        assert dimension in DIMENSION_WEIGHTS
        weight = DIMENSION_WEIGHTS[dimension]
        assert 0 < weight <= 1.0


def test_generate_recommendation_critical(alignment_engine):
    """Test recommendation generation for full gaps."""
    rec = alignment_engine._generate_recommendation(
        TOMDimension.PROCESS_ARCHITECTURE,
        TOMGapType.FULL_GAP
    )

    assert rec.startswith("CRITICAL:")
    assert "process" in rec.lower()


def test_generate_recommendation_high(alignment_engine):
    """Test recommendation generation for partial gaps."""
    rec = alignment_engine._generate_recommendation(
        TOMDimension.GOVERNANCE_STRUCTURES,
        TOMGapType.PARTIAL_GAP
    )

    assert rec.startswith("HIGH:")
    assert "governance" in rec.lower()
