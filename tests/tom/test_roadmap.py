"""Tests for RoadmapGenerator.

Validates transformation roadmap generation, phase categorization,
and initiative prioritization functionality.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import TOMDimension, TOMGapType
from src.tom.roadmap import RoadmapGenerator


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database queries."""
    return AsyncMock()


@pytest.fixture
def roadmap_generator():
    """RoadmapGenerator instance."""
    return RoadmapGenerator()


def create_mock_gap(gap_type: str, dimension: str, severity: float, confidence: float) -> MagicMock:
    """Create a mock GapAnalysisResult."""
    gap = MagicMock()
    gap.id = uuid.uuid4()
    gap.gap_type = gap_type
    gap.dimension = dimension
    gap.severity = severity
    gap.confidence = confidence
    gap.priority_score = severity * confidence  # Matches the property definition
    gap.recommendation = f"Address {dimension} gap"
    return gap


@pytest.mark.asyncio
async def test_generate_roadmap_categorization(roadmap_generator, mock_session):
    """Test that gaps are categorized correctly into phases."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    # Create gaps for each type
    gaps = [
        # Phase 1: Deviations
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.PROCESS_ARCHITECTURE, 0.25, 0.8),
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.GOVERNANCE_STRUCTURES, 0.2, 0.7),
        # Phase 2: Partial gaps with high priority (>0.5)
        create_mock_gap(TOMGapType.PARTIAL_GAP, TOMDimension.TECHNOLOGY_AND_DATA, 0.7, 0.8),
        # Phase 3: Full gaps
        create_mock_gap(TOMGapType.FULL_GAP, TOMDimension.RISK_AND_COMPLIANCE, 1.0, 0.9),
        # Phase 4: Partial gaps with low priority (<=0.5)
        create_mock_gap(TOMGapType.PARTIAL_GAP, TOMDimension.PERFORMANCE_MANAGEMENT, 0.3, 0.5),
        # NO_GAP should be ignored
        create_mock_gap(TOMGapType.NO_GAP, TOMDimension.PEOPLE_AND_ORGANIZATION, 0.0, 1.0),
    ]

    # Mock database query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = gaps
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    assert roadmap.engagement_id == engagement_id
    assert roadmap.tom_id == tom_id
    assert len(roadmap.phases) == 4

    # Phase 1: Quick Wins (deviations)
    phase_1 = roadmap.phases[0]
    assert phase_1.phase_number == 1
    assert phase_1.name == "Quick Wins"
    assert phase_1.duration_months == 3
    assert len(phase_1.initiatives) == 2  # 2 deviations

    # Phase 2: Foundation (partial gaps with high priority)
    phase_2 = roadmap.phases[1]
    assert phase_2.phase_number == 2
    assert phase_2.name == "Foundation Building"
    assert phase_2.duration_months == 6
    assert len(phase_2.initiatives) == 1  # 1 high-priority partial gap

    # Phase 3: Transformation (full gaps)
    phase_3 = roadmap.phases[2]
    assert phase_3.phase_number == 3
    assert phase_3.name == "Transformation"
    assert phase_3.duration_months == 9
    assert len(phase_3.initiatives) == 1  # 1 full gap

    # Phase 4: Optimization (remaining partial gaps)
    phase_4 = roadmap.phases[3]
    assert phase_4.phase_number == 4
    assert phase_4.name == "Optimization"
    assert phase_4.duration_months == 6
    assert len(phase_4.initiatives) == 1  # 1 low-priority partial gap


@pytest.mark.asyncio
async def test_generate_roadmap_empty_gaps(roadmap_generator, mock_session):
    """Test roadmap generation with no gaps."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    # Mock empty gaps
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    assert len(roadmap.phases) == 4
    assert all(len(phase.initiatives) == 0 for phase in roadmap.phases)
    assert roadmap.total_initiatives == 0


@pytest.mark.asyncio
async def test_generate_roadmap_total_initiatives(roadmap_generator, mock_session):
    """Test that total initiatives count equals sum of all gaps (excluding NO_GAP)."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    gaps = [
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.PROCESS_ARCHITECTURE, 0.25, 0.8),
        create_mock_gap(TOMGapType.PARTIAL_GAP, TOMDimension.TECHNOLOGY_AND_DATA, 0.7, 0.8),
        create_mock_gap(TOMGapType.FULL_GAP, TOMDimension.RISK_AND_COMPLIANCE, 1.0, 0.9),
        create_mock_gap(TOMGapType.NO_GAP, TOMDimension.GOVERNANCE_STRUCTURES, 0.0, 1.0),  # Should be excluded
    ]

    # Mock database query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = gaps
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    # Total should be 3 (excluding the NO_GAP)
    assert roadmap.total_initiatives == 3

    # Verify sum of initiatives across all phases
    total = sum(len(phase.initiatives) for phase in roadmap.phases)
    assert total == 3


@pytest.mark.asyncio
async def test_generate_roadmap_duration(roadmap_generator, mock_session):
    """Test that total duration equals sum of phase durations."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    # Mock empty gaps for simplicity
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    # Total duration = 3 + 6 + 9 + 6 = 24 months
    assert roadmap.estimated_duration_months == 24

    # Verify individual phase durations
    assert roadmap.phases[0].duration_months == 3
    assert roadmap.phases[1].duration_months == 6
    assert roadmap.phases[2].duration_months == 9
    assert roadmap.phases[3].duration_months == 6


@pytest.mark.asyncio
async def test_roadmap_phase_dependencies(roadmap_generator, mock_session):
    """Test that phases have correct dependencies."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    # Mock empty gaps
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    # Phase 1 has no dependencies
    assert roadmap.phases[0].dependencies == []

    # Phase 2 depends on phase_1
    assert roadmap.phases[1].dependencies == ["phase_1"]

    # Phase 3 depends on phase_2
    assert roadmap.phases[2].dependencies == ["phase_2"]

    # Phase 4 depends on phase_3
    assert roadmap.phases[3].dependencies == ["phase_3"]


@pytest.mark.asyncio
async def test_initiatives_sorted_by_priority(roadmap_generator, mock_session):
    """Test that initiatives within each phase are sorted by priority_score descending."""
    engagement_id = "eng-1"
    tom_id = "tom-1"

    # Create multiple deviations with different priorities
    gaps = [
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.PROCESS_ARCHITECTURE, 0.2, 0.5),  # priority: 0.10
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.GOVERNANCE_STRUCTURES, 0.5, 0.9),  # priority: 0.45
        create_mock_gap(TOMGapType.DEVIATION, TOMDimension.TECHNOLOGY_AND_DATA, 0.3, 0.8),  # priority: 0.24
    ]

    # Mock database query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = gaps
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Execute
    roadmap = await roadmap_generator.generate_roadmap(mock_session, engagement_id, tom_id)

    # Assertions
    # All deviations should be in Phase 1
    phase_1 = roadmap.phases[0]
    assert len(phase_1.initiatives) == 3

    # Check sorting (descending by priority_score)
    priorities = [init["priority_score"] for init in phase_1.initiatives]
    assert priorities == sorted(priorities, reverse=True)

    # Verify specific order
    assert priorities[0] == 0.45  # Highest priority first
    assert priorities[1] == 0.24
    assert priorities[2] == 0.10  # Lowest priority last
