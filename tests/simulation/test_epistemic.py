"""Tests for the Epistemic Action Planner service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.simulation.epistemic import (
    MAX_PROJECTED_CONFIDENCE,
    EpistemicActionItem,
    EpistemicPlannerService,
    EpistemicPlanResult,
    calculate_confidence_uplift,
    compute_information_gain,
)


class TestCalculateConfidenceUplift:
    """Tests for confidence uplift calculation."""

    def test_zero_confidence_gets_uplift(self) -> None:
        uplift, projected = calculate_confidence_uplift(0.0, 0, 1.0)
        assert uplift > 0
        assert projected > 0

    def test_max_confidence_no_uplift(self) -> None:
        uplift, projected = calculate_confidence_uplift(0.95, 3, 1.0)
        assert uplift == 0.0
        assert projected == MAX_PROJECTED_CONFIDENCE

    def test_above_max_no_uplift(self) -> None:
        uplift, projected = calculate_confidence_uplift(0.96, 0, 1.0)
        assert uplift == 0.0
        assert projected == MAX_PROJECTED_CONFIDENCE  # Capped even when current > max

    def test_capped_at_max(self) -> None:
        _, projected = calculate_confidence_uplift(0.0, 0, 1.0)
        assert projected <= MAX_PROJECTED_CONFIDENCE

    def test_diminishing_returns_with_more_sources(self) -> None:
        uplift_0, _ = calculate_confidence_uplift(0.3, 0, 1.0)
        uplift_3, _ = calculate_confidence_uplift(0.3, 3, 1.0)
        assert uplift_0 > uplift_3

    def test_higher_weight_gives_more_uplift(self) -> None:
        uplift_high, _ = calculate_confidence_uplift(0.3, 0, 1.0)
        uplift_low, _ = calculate_confidence_uplift(0.3, 0, 0.3)
        assert uplift_high > uplift_low

    def test_projected_never_exceeds_max(self) -> None:
        _, projected = calculate_confidence_uplift(0.90, 0, 1.0)
        assert projected <= MAX_PROJECTED_CONFIDENCE

    def test_uplift_is_non_negative(self) -> None:
        uplift, _ = calculate_confidence_uplift(0.5, 5, 0.5)
        assert uplift >= 0


class TestComputeInformationGain:
    """Tests for information gain computation."""

    def test_zero_uplift_zero_gain(self) -> None:
        assert compute_information_gain(0.0, 0.5) == 0.0

    def test_positive_uplift_positive_gain(self) -> None:
        gain = compute_information_gain(0.1, 0.5)
        assert gain > 0

    def test_higher_cascade_amplifies_gain(self) -> None:
        gain_low = compute_information_gain(0.1, 0.1)
        gain_high = compute_information_gain(0.1, 0.9)
        assert gain_high > gain_low

    def test_gain_proportional_to_uplift(self) -> None:
        gain_small = compute_information_gain(0.01, 0.5)
        gain_large = compute_information_gain(0.10, 0.5)
        assert gain_large > gain_small


class TestEpistemicPlannerService:
    """Tests for the full planner pipeline."""

    @pytest.mark.asyncio
    async def test_empty_coverage_returns_empty_plan(self) -> None:
        """When all elements are bright, no actions needed."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage("e1", "Element 1", "bright", 5, 0.9),
            ],
            bright_count=1,
            dim_count=0,
            dark_count=0,
            aggregate_confidence=0.9,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)
            result = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

        assert isinstance(result, EpistemicPlanResult)
        assert result.total_actions == 0
        assert result.actions == []

    @pytest.mark.asyncio
    async def test_dim_dark_elements_produce_actions(self) -> None:
        """Dim and dark elements should generate epistemic actions."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage("e1", "Strong Element", "bright", 5, 0.9),
                ElementCoverage("e2", "Weak Element", "dim", 1, 0.45),
                ElementCoverage("e3", "Missing Element", "dark", 0, 0.0),
            ],
            bright_count=1,
            dim_count=1,
            dark_count=1,
            aggregate_confidence=0.45,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)
            result = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

        assert result.total_actions == 2
        assert all(isinstance(a, EpistemicActionItem) for a in result.actions)

    @pytest.mark.asyncio
    async def test_actions_ranked_by_info_gain_desc(self) -> None:
        """Actions should be sorted by information_gain_score descending."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage("e1", "Dim A", "dim", 2, 0.5),
                ElementCoverage("e2", "Dark B", "dark", 0, 0.0),
                ElementCoverage("e3", "Dim C", "dim", 1, 0.42),
            ],
            bright_count=0,
            dim_count=2,
            dark_count=1,
            aggregate_confidence=0.3,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)
            result = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

        gains = [a.information_gain_score for a in result.actions]
        assert gains == sorted(gains, reverse=True)

    @pytest.mark.asyncio
    async def test_removed_elements_excluded(self) -> None:
        """Removed elements should not appear in epistemic plan."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage(
                    "e1",
                    "Removed",
                    "dark",
                    0,
                    0.0,
                    is_removed=True,
                ),
                ElementCoverage("e2", "Active Dark", "dark", 0, 0.0),
            ],
            bright_count=0,
            dim_count=0,
            dark_count=1,
            aggregate_confidence=0.0,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)
            result = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

        assert result.total_actions == 1
        assert result.actions[0].target_element_name == "Active Dark"

    @pytest.mark.asyncio
    async def test_aggregate_calculations(self) -> None:
        """Aggregates should be computed correctly."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage("e1", "Dark A", "dark", 0, 0.0),
                ElementCoverage("e2", "Dark B", "dark", 0, 0.1),
            ],
            bright_count=0,
            dim_count=0,
            dark_count=2,
            aggregate_confidence=0.05,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)
            result = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

        assert result.total_actions == 2
        assert result.estimated_aggregate_uplift > 0
        assert result.high_priority_count >= 0

    @pytest.mark.asyncio
    async def test_process_graph_impacts_gain(self) -> None:
        """Providing a process graph should affect information gain scores."""
        from src.simulation.coverage import ElementCoverage, ScenarioCoverageResult

        mock_graph = AsyncMock()
        service = EpistemicPlannerService(mock_graph)

        coverage = ScenarioCoverageResult(
            scenario_id="test",
            elements=[
                ElementCoverage("e1", "Node A", "dark", 0, 0.0),
            ],
            bright_count=0,
            dim_count=0,
            dark_count=1,
            aggregate_confidence=0.0,
        )

        with patch("src.simulation.coverage.EvidenceCoverageService") as mock_coverage_cls:
            mock_coverage_cls.return_value.compute_coverage = AsyncMock(return_value=coverage)

            # Without graph connections
            result_no_graph = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
            )

            # With graph connections that cause cascading impact
            result_with_graph = await service.generate_epistemic_plan(
                scenario_id=uuid.uuid4(),
                engagement_id=uuid.uuid4(),
                session=None,
                process_graph={
                    "connections": [
                        {"source": "Node A", "target": "Node B"},
                        {"source": "Node B", "target": "Node C"},
                    ]
                },
            )

        # Both should produce actions
        assert result_no_graph.total_actions == 1
        assert result_with_graph.total_actions == 1
