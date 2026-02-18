"""Tests for graph-aware gap scanner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.gap_scanner import scan_evidence_gaps, scan_evidence_gaps_graph


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


class TestScanEvidenceGapsGraph:
    """Tests for the Neo4j graph-based gap scanner."""

    @pytest.mark.asyncio
    async def test_empty_graph_reports_all_dimension_gaps(self) -> None:
        """Empty graph should flag all dimensions as gaps."""
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=_MockResult([]))

        mock_driver = _make_neo4j_driver(mock_session)

        result = await scan_evidence_gaps_graph("eng-1", mock_driver)

        assert result["engagement_id"] == "eng-1"
        assert result["summary"]["total_nodes"] == 0
        assert result["summary"]["total_relationships"] == 0
        assert result["summary"]["dimensions_below_threshold"] > 0
        dimension_gaps = [g for g in result["gaps"] if g["gap_type"] == "dimension_coverage"]
        assert len(dimension_gaps) > 0

    @pytest.mark.asyncio
    async def test_detects_orphaned_nodes(self) -> None:
        """Should identify nodes with no relationships."""
        mock_session = AsyncMock()

        call_count = [0]
        results_sequence = [
            _MockResult([{"label": "Activity", "count": 5}]),               # nodes by label
            _MockResult([{"rel_type": "CO_OCCURS_WITH", "count": 3}]),      # rels by type
            _MockResult([{"id": "o1", "name": "Orphan Activity", "label": "Activity"}]),  # orphans
            _MockResult([]),                                                 # unsupported
        ]

        async def mock_run(query, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(results_sequence):
                return results_sequence[idx]
            return _MockResult([])

        mock_session.run = mock_run
        mock_driver = _make_neo4j_driver(mock_session)

        result = await scan_evidence_gaps_graph("eng-1", mock_driver)

        orphan_gaps = [g for g in result["gaps"] if g["gap_type"] == "orphaned_node"]
        assert len(orphan_gaps) == 1
        assert orphan_gaps[0]["element_name"] == "Orphan Activity"

    @pytest.mark.asyncio
    async def test_detects_missing_bridge_types(self) -> None:
        """Should flag bridge relationship types that don't exist."""
        mock_session = AsyncMock()

        call_count = [0]
        results_sequence = [
            _MockResult([]),                                            # nodes by label
            _MockResult([{"rel_type": "CO_OCCURS_WITH", "count": 5}]), # rels by type (only CO_OCCURS_WITH)
            _MockResult([]),                                            # orphans
            _MockResult([]),                                            # unsupported
        ]

        async def mock_run(query, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(results_sequence):
                return results_sequence[idx]
            return _MockResult([])

        mock_session.run = mock_run
        mock_driver = _make_neo4j_driver(mock_session)

        result = await scan_evidence_gaps_graph("eng-1", mock_driver)

        bridge_gaps = [g for g in result["gaps"] if g["gap_type"] == "missing_bridge_type"]
        bridge_names = {g["element_name"] for g in bridge_gaps}
        assert "SUPPORTED_BY" in bridge_names
        assert "GOVERNED_BY" in bridge_names


class TestScanEvidenceGapsFallback:
    """Tests for the heuristic fallback gap scanner."""

    def test_missing_evidence(self) -> None:
        """Should detect unsupported process elements."""
        gaps = scan_evidence_gaps(
            evidence_items=[{"id": "ev-1", "category": "documents", "quality_score": 0.8}],
            process_elements=[
                {"name": "Review Invoice", "evidence_ids": []},
            ],
        )
        assert any(g["gap_type"] == "missing_evidence" for g in gaps)

    def test_single_source(self) -> None:
        """Should detect single-source evidence."""
        gaps = scan_evidence_gaps(
            evidence_items=[{"id": "ev-1", "category": "documents", "quality_score": 0.8}],
            process_elements=[
                {"name": "Review Invoice", "evidence_ids": ["ev-1"]},
            ],
        )
        assert any(g["gap_type"] == "single_source" for g in gaps)

    def test_missing_category(self) -> None:
        """Should detect missing evidence categories."""
        gaps = scan_evidence_gaps(
            evidence_items=[{"id": "ev-1", "category": "documents", "quality_score": 0.8}],
            process_elements=[],
        )
        missing_cats = [g for g in gaps if g["gap_type"] == "missing_category"]
        assert len(missing_cats) > 0

    def test_weak_evidence(self) -> None:
        """Should detect low quality evidence."""
        gaps = scan_evidence_gaps(
            evidence_items=[{"id": "ev-1", "category": "documents", "quality_score": 0.3, "name": "bad doc"}],
            process_elements=[],
        )
        assert any(g["gap_type"] == "weak_evidence" for g in gaps)
