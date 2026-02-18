"""Tests for evidence-based recommender."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.recommender import (
    _calculate_confidence,
    _get_dimension_remediation,
    build_shelf_request_items,
    generate_recommendations,
    generate_recommendations_graph,
)


class _MockResult:
    """Mock Neo4j result supporting async iteration."""

    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def __aiter__(self):
        return self._generate()

    async def _generate(self):
        for record in self._records:
            yield record


def _make_neo4j_driver(mock_session: AsyncMock) -> MagicMock:
    """Create a MagicMock Neo4j driver with proper async context manager."""
    mock_driver = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = mock_session
    mock_driver.session.return_value = ctx
    return mock_driver


class TestGenerateRecommendationsGraph:
    """Tests for graph-based recommendation generation."""

    @pytest.mark.asyncio
    async def test_generates_recommendations_from_gaps(self) -> None:
        """Should generate recommendations with confidence scores."""
        mock_session = AsyncMock()

        call_count = [0]
        results_sequence = [
            _MockResult(
                [
                    {"label": "Activity", "count": 10},
                    {"label": "Role", "count": 5},
                ]
            ),  # node counts
            _MockResult(
                [
                    {"name": "Review Invoice", "label": "Activity", "rel_count": 5},
                ]
            ),  # well-connected nodes
        ]

        async def mock_run(query, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(results_sequence):
                return results_sequence[idx]
            return _MockResult([])

        mock_session.run = mock_run
        mock_driver = _make_neo4j_driver(mock_session)

        gaps = [
            {
                "gap_type": "unsupported_process",
                "severity": "high",
                "element_name": "Approve Invoice",
                "element_id": "act-1",
                "description": "Activity 'Approve Invoice' lacks evidence support",
                "recommendation": "Collect evidence supporting 'Approve Invoice'",
            },
            {
                "gap_type": "orphaned_node",
                "severity": "medium",
                "element_name": "Tax Specialist",
                "element_id": "role-1",
                "description": "Role 'Tax Specialist' has no relationships",
                "recommendation": "Add evidence linking 'Tax Specialist'",
            },
        ]

        recs = await generate_recommendations_graph("eng-1", gaps, mock_driver)

        assert len(recs) == 2
        assert recs[0]["severity"] == "high"
        assert recs[0]["confidence"] > 0
        assert isinstance(recs[0]["evidence_context"], list)

    @pytest.mark.asyncio
    async def test_skips_existing_requests(self) -> None:
        """Should skip recommendations that already exist."""
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=_MockResult([]))

        mock_driver = _make_neo4j_driver(mock_session)

        gaps = [
            {
                "gap_type": "missing_evidence",
                "severity": "high",
                "element_name": "test",
                "recommendation": "Already Requested",
            },
        ]
        existing = [{"items": [{"item_name": "already requested"}]}]

        recs = await generate_recommendations_graph("eng-1", gaps, mock_driver, existing)
        assert len(recs) == 0

    @pytest.mark.asyncio
    async def test_dimension_coverage_includes_remediation(self) -> None:
        """Dimension coverage gaps should include remediation strategy."""
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=_MockResult([]))

        mock_driver = _make_neo4j_driver(mock_session)

        gaps = [
            {
                "gap_type": "dimension_coverage",
                "severity": "high",
                "dimension": "process_architecture",
                "coverage_score": 0.1,
                "element_name": "process_architecture",
                "recommendation": "Add more process evidence",
            },
        ]

        recs = await generate_recommendations_graph("eng-1", gaps, mock_driver)
        assert len(recs) == 1
        assert "remediation_strategy" in recs[0]


class TestCalculateConfidence:
    """Tests for confidence calculation."""

    def test_base_confidence(self) -> None:
        """Base confidence should be around 0.5."""
        gap = {"gap_type": "other", "element_name": "test"}
        confidence = _calculate_confidence(gap, {}, 0, [])
        assert 0.4 <= confidence <= 0.6

    def test_higher_with_more_nodes(self) -> None:
        """More graph nodes should increase confidence."""
        gap = {"gap_type": "unsupported_process", "element_name": "test"}
        low_conf = _calculate_confidence(gap, {}, 5, [])
        high_conf = _calculate_confidence(gap, {}, 100, [])
        assert high_conf > low_conf

    def test_dimension_coverage_score_affects_confidence(self) -> None:
        """Lower coverage score should increase confidence."""
        gap_low = {"gap_type": "dimension_coverage", "coverage_score": 0.1, "element_name": "test"}
        gap_high = {"gap_type": "dimension_coverage", "coverage_score": 0.9, "element_name": "test"}
        conf_low = _calculate_confidence(gap_low, {}, 10, [])
        conf_high = _calculate_confidence(gap_high, {}, 10, [])
        assert conf_low > conf_high


class TestGetDimensionRemediation:
    """Tests for dimension remediation strategies."""

    def test_process_architecture(self) -> None:
        """Should return process-specific remediation."""
        strategy = _get_dimension_remediation("process_architecture", {"Process": 2, "Activity": 5})
        assert "process" in strategy.lower()
        assert "2" in strategy

    def test_unknown_dimension(self) -> None:
        """Unknown dimension should return generic strategy."""
        strategy = _get_dimension_remediation("unknown_dimension", {})
        assert "review" in strategy.lower()


class TestGenerateRecommendationsFallback:
    """Tests for heuristic fallback recommendations."""

    def test_prioritizes_by_severity(self) -> None:
        """Should sort by severity (high first)."""
        gaps = [
            {"gap_type": "a", "severity": "low", "recommendation": "low rec"},
            {"gap_type": "b", "severity": "high", "recommendation": "high rec"},
        ]
        recs = generate_recommendations(gaps)
        assert recs[0]["severity"] == "high"

    def test_skips_existing(self) -> None:
        """Should skip already-requested items."""
        gaps = [
            {"gap_type": "a", "severity": "high", "recommendation": "Existing Rec"},
        ]
        existing = [{"items": [{"item_name": "existing rec"}]}]
        recs = generate_recommendations(gaps, existing)
        assert len(recs) == 0


class TestBuildShelfRequestItems:
    """Tests for shelf request item generation."""

    def test_builds_from_auto_request(self) -> None:
        """Should create items for auto_request recommendations."""
        recs = [
            {"severity": "high", "gap_type": "missing", "recommendation": "Get docs", "auto_request": True},
            {"severity": "low", "gap_type": "minor", "recommendation": "Nice to have", "auto_request": False},
        ]
        items = build_shelf_request_items(recs, "eng-1")
        assert len(items) == 1
        assert items[0]["item_name"] == "Get docs"
        assert items[0]["priority"] == "high"
