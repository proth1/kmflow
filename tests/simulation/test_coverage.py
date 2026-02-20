"""Tests for evidence coverage classification service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.models import ModificationType
from src.simulation.coverage import (
    BRIGHT_MIN_CONFIDENCE,
    BRIGHT_MIN_SOURCES,
    DIM_MIN_CONFIDENCE,
    MODIFICATION_CONFIDENCE_PENALTY,
    EvidenceCoverageService,
    ScenarioCoverageResult,
    classify_element,
)


class TestClassifyElement:
    """Tests for the classify_element function."""

    def test_bright_at_exact_threshold(self):
        result = classify_element(BRIGHT_MIN_SOURCES, BRIGHT_MIN_CONFIDENCE)
        assert result == "bright"

    def test_bright_above_threshold(self):
        result = classify_element(5, 0.90)
        assert result == "bright"

    def test_dim_with_one_source_and_sufficient_confidence(self):
        result = classify_element(1, 0.50)
        assert result == "dim"

    def test_dim_with_two_sources_below_bright_confidence(self):
        result = classify_element(2, 0.60)
        assert result == "dim"

    def test_dim_at_exact_lower_threshold(self):
        result = classify_element(1, DIM_MIN_CONFIDENCE)
        assert result == "dim"

    def test_dark_with_zero_sources(self):
        result = classify_element(0, 0.0)
        assert result == "dark"

    def test_dark_with_low_confidence(self):
        result = classify_element(1, 0.39)
        assert result == "dark"

    def test_dark_with_many_sources_but_low_confidence(self):
        result = classify_element(5, 0.30)
        assert result == "dark"

    def test_added_element_always_dark(self):
        result = classify_element(5, 0.95, is_added=True)
        assert result == "dark"

    def test_bright_boundary_below_sources(self):
        result = classify_element(BRIGHT_MIN_SOURCES - 1, BRIGHT_MIN_CONFIDENCE)
        assert result == "dim"

    def test_bright_boundary_below_confidence(self):
        result = classify_element(BRIGHT_MIN_SOURCES, BRIGHT_MIN_CONFIDENCE - 0.01)
        assert result == "dim"


class TestEvidenceCoverageService:
    """Tests for the async coverage service."""

    @pytest.fixture()
    def mock_graph(self):
        graph = AsyncMock()
        graph._run_query = AsyncMock(return_value=[])
        return graph

    @pytest.fixture()
    def service(self, mock_graph):
        return EvidenceCoverageService(mock_graph)

    @pytest.mark.asyncio
    async def test_empty_graph_returns_zero_counts(self, service, mock_graph):
        mock_graph._run_query.return_value = []
        result = await service.compute_coverage(uuid4(), uuid4())
        assert isinstance(result, ScenarioCoverageResult)
        assert result.bright_count == 0
        assert result.dim_count == 0
        assert result.dark_count == 0
        assert result.aggregate_confidence == 0.0

    @pytest.mark.asyncio
    async def test_bright_element_counted(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "elem1", "name": "Task A", "evidence_count": 4, "avg_confidence": 0.85},
        ]
        result = await service.compute_coverage(uuid4(), uuid4())
        assert result.bright_count == 1
        assert result.dim_count == 0
        assert result.dark_count == 0
        assert result.elements[0].classification == "bright"

    @pytest.mark.asyncio
    async def test_dim_element_counted(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "elem1", "name": "Task A", "evidence_count": 1, "avg_confidence": 0.50},
        ]
        result = await service.compute_coverage(uuid4(), uuid4())
        assert result.bright_count == 0
        assert result.dim_count == 1
        assert result.elements[0].classification == "dim"

    @pytest.mark.asyncio
    async def test_added_element_forced_dark(self, service, mock_graph):
        mock_graph._run_query.return_value = []
        mod = SimpleNamespace(
            modification_type=ModificationType.TASK_ADD,
            element_id="new_elem",
            element_name="New Task",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        assert result.dark_count == 1
        assert result.elements[0].is_added is True
        assert result.elements[0].classification == "dark"

    @pytest.mark.asyncio
    async def test_modification_penalty_applied(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "elem1", "name": "Task A", "evidence_count": 4, "avg_confidence": 0.80},
        ]
        mod = SimpleNamespace(
            modification_type=ModificationType.TASK_MODIFY,
            element_id="elem1",
            element_name="Task A",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        expected_conf = 0.80 - MODIFICATION_CONFIDENCE_PENALTY
        assert result.elements[0].confidence == pytest.approx(expected_conf, abs=0.001)
        assert result.elements[0].is_modified is True

    @pytest.mark.asyncio
    async def test_removed_element_excluded_from_aggregate(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "elem1", "name": "Active", "evidence_count": 4, "avg_confidence": 0.80},
            {"id": "elem2", "name": "Removed", "evidence_count": 1, "avg_confidence": 0.50},
        ]
        mod = SimpleNamespace(
            modification_type=ModificationType.TASK_REMOVE,
            element_id="elem2",
            element_name="Removed",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        # Only elem1 should count in aggregates
        assert result.bright_count == 1
        assert result.dim_count == 0
        # elem2 is still in elements but marked removed
        removed = [e for e in result.elements if e.is_removed]
        assert len(removed) == 1
        # Aggregate confidence based on active only
        assert result.aggregate_confidence == pytest.approx(0.80, abs=0.01)

    @pytest.mark.asyncio
    async def test_aggregate_confidence_is_mean_of_active(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "e1", "name": "T1", "evidence_count": 4, "avg_confidence": 0.90},
            {"id": "e2", "name": "T2", "evidence_count": 4, "avg_confidence": 0.70},
        ]
        result = await service.compute_coverage(uuid4(), uuid4())
        assert result.aggregate_confidence == pytest.approx(0.80, abs=0.01)

    @pytest.mark.asyncio
    async def test_penalty_does_not_go_below_zero(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "elem1", "name": "Task A", "evidence_count": 1, "avg_confidence": 0.05},
        ]
        mod = SimpleNamespace(
            modification_type=ModificationType.TASK_MODIFY,
            element_id="elem1",
            element_name="Task A",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        assert result.elements[0].confidence >= 0.0

    @pytest.mark.asyncio
    async def test_control_remove_excludes_from_aggregate(self, service, mock_graph):
        mock_graph._run_query.return_value = [
            {"id": "ctrl1", "name": "Control", "evidence_count": 2, "avg_confidence": 0.60},
        ]
        mod = SimpleNamespace(
            modification_type=ModificationType.CONTROL_REMOVE,
            element_id="ctrl1",
            element_name="Control",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        assert result.bright_count == 0
        assert result.dim_count == 0
        assert result.dark_count == 0
        assert result.aggregate_confidence == 0.0

    @pytest.mark.asyncio
    async def test_control_add_forced_dark(self, service, mock_graph):
        mock_graph._run_query.return_value = []
        mod = SimpleNamespace(
            modification_type=ModificationType.CONTROL_ADD,
            element_id="new_ctrl",
            element_name="New Control",
        )
        result = await service.compute_coverage(uuid4(), uuid4(), [mod])
        assert result.dark_count == 1
        assert result.elements[0].is_added is True
