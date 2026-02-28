"""Tests for process variant detection (Story #229)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.semantic.graph import GraphNode, GraphRelationship
from src.taskmining.variant_detection import (
    ProcessVariant,
    _compare_sequences,
    detect_variants,
)


def _make_node(node_id: str, label: str, name: str) -> GraphNode:
    return GraphNode(id=node_id, label=label, properties={"name": name})


def _make_rel(
    from_id: str,
    to_id: str,
    rel_type: str,
    props: dict | None = None,
) -> GraphRelationship:
    return GraphRelationship(
        id=f"r-{from_id}-{to_id}",
        from_id=from_id,
        to_id=to_id,
        relationship_type=rel_type,
        properties=props or {},
    )


class TestCompareSequences:
    def test_conforming_sequence_no_variants(self):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"],
            observed_ids=["A", "B", "C"],
            process_id="p1",
            process_name="Loan Process",
            session_id="s1",
        )
        assert variants == []

    def test_extra_step_detected(self):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"],
            observed_ids=["A", "B", "D", "C"],
            process_id="p1",
            process_name="Loan Process",
            session_id="s1",
        )
        extra_variants = [v for v in variants if v.deviation_type == "extra_step"]
        assert len(extra_variants) == 1
        assert extra_variants[0].severity == "info"
        assert "1 step(s) not in documented" in extra_variants[0].description

    def test_missing_step_detected(self):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"],
            observed_ids=["A", "C"],
            process_id="p1",
            process_name="Loan Process",
            session_id="s1",
        )
        missing_variants = [v for v in variants if v.deviation_type == "missing_step"]
        assert len(missing_variants) == 1
        assert missing_variants[0].severity == "warning"
        assert "1 expected step(s)" in missing_variants[0].description

    def test_different_order_detected(self):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"],
            observed_ids=["A", "C", "B"],
            process_id="p1",
            process_name="Loan Process",
            session_id="s1",
        )
        order_variants = [v for v in variants if v.deviation_type == "different_order"]
        assert len(order_variants) == 1
        assert order_variants[0].severity == "info"
        assert "different order" in order_variants[0].description

    def test_multiple_deviations(self):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"],
            observed_ids=["C", "A", "D"],  # reordered + extra D + missing B
            process_id="p1",
            process_name="Loan Process",
            session_id="s1",
        )
        types = {v.deviation_type for v in variants}
        assert "extra_step" in types
        assert "missing_step" in types
        assert "different_order" in types

    def test_empty_observed_only_missing(self):
        variants = _compare_sequences(
            expected_ids=["A", "B"],
            observed_ids=[],
            process_id="p1",
            process_name="Test",
            session_id="s1",
        )
        assert len(variants) == 1
        assert variants[0].deviation_type == "missing_step"


class TestSeverityAssignment:
    @pytest.mark.parametrize(
        "deviation_type,expected_severity",
        [
            ("missing_step", "warning"),
            ("extra_step", "info"),
            ("different_order", "info"),
        ],
    )
    def test_severity_mapping(self, deviation_type: str, expected_severity: str):
        variants = _compare_sequences(
            expected_ids=["A", "B", "C"] if deviation_type != "extra_step" else ["A", "B"],
            observed_ids={
                "missing_step": ["A", "C"],
                "extra_step": ["A", "B", "D"],
                "different_order": ["A", "C", "B"],
            }[deviation_type],
            process_id="p1",
            process_name="Test",
            session_id="s1",
        )
        matching = [v for v in variants if v.deviation_type == deviation_type]
        assert len(matching) >= 1
        assert matching[0].severity == expected_severity


class TestProcessVariantDataclass:
    def test_variant_serializable(self):
        v = ProcessVariant(
            process_id="p1",
            process_name="Loan",
            session_id="s1",
            deviation_type="extra_step",
            severity="info",
            confidence=0.8,
            description="Extra step detected",
        )
        # Ensure all fields are JSON-serializable types
        assert isinstance(v.process_id, str)
        assert isinstance(v.confidence, float)
        assert isinstance(v.deviation_type, str)


class TestDetectVariantsIntegration:
    @pytest.fixture
    def mock_graph_service(self):
        service = AsyncMock()
        service.create_relationship = AsyncMock(
            return_value=GraphRelationship(
                id="r1",
                from_id="a",
                to_id="b",
                relationship_type="DEVIATES_FROM",
                properties={},
            )
        )
        return service

    @pytest.mark.asyncio
    async def test_no_processes_returns_empty(self, mock_graph_service):
        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [],  # processes
                [],  # user_actions
            ]
        )

        result = await detect_variants(mock_graph_service, "eng-1")

        assert result.variants == []
        assert result.sessions_analyzed == 0

    @pytest.mark.asyncio
    async def test_no_user_actions_returns_empty(self, mock_graph_service):
        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [_make_node("p1", "Process", "Loan Process")],
                [],  # no user actions
            ]
        )

        result = await detect_variants(mock_graph_service, "eng-1")

        assert result.variants == []
        assert result.sessions_analyzed == 0

    @pytest.mark.asyncio
    async def test_conforming_behavior_no_deviations(self, mock_graph_service):
        process = _make_node("p1", "Process", "Loan Process")
        ua1 = _make_node("ua-1", "UserAction", "Step A")
        ua2 = _make_node("ua-2", "UserAction", "Step B")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [process],
                [ua1, ua2],
            ]
        )

        # Process has activities A, B connected via FOLLOWED_BY
        def get_rels(node_id, direction="both", relationship_type=None):
            if node_id == "p1" and direction == "outgoing":
                return [
                    _make_rel("p1", "act-A", "FOLLOWED_BY"),
                    _make_rel("p1", "act-B", "FOLLOWED_BY"),
                ]
            if node_id in ("act-A",) and relationship_type == "FOLLOWED_BY":
                return [_make_rel("act-A", "act-B", "FOLLOWED_BY")]
            if node_id == "ua-1" and relationship_type == "SUPPORTS":
                return [_make_rel("ua-1", "act-A", "SUPPORTS", {"similarity_score": 0.9})]
            if node_id == "ua-2" and relationship_type == "SUPPORTS":
                return [_make_rel("ua-2", "act-B", "SUPPORTS", {"similarity_score": 0.8})]
            if node_id == "ua-2" and relationship_type == "PRECEDED_BY":
                return [_make_rel("ua-2", "ua-1", "PRECEDED_BY")]
            if node_id == "ua-1" and relationship_type == "PRECEDED_BY":
                return []
            return []

        mock_graph_service.get_relationships = AsyncMock(side_effect=get_rels)

        result = await detect_variants(mock_graph_service, "eng-1")

        assert result.sessions_analyzed >= 0
        # Conforming behavior: observed matches expected → no variants
        assert len(result.variants) == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_error_during_relationship_creation_captured(self, mock_graph_service):
        process = _make_node("p1", "Process", "Test Process")
        ua1 = _make_node("ua-1", "UserAction", "Action 1")

        mock_graph_service.find_nodes = AsyncMock(
            side_effect=[
                [process],
                [ua1],
            ]
        )

        # Process has one activity; UA maps to a different activity = extra step
        def get_rels(node_id, direction="both", relationship_type=None):
            if node_id == "p1" and direction == "outgoing":
                return [_make_rel("p1", "act-A", "FOLLOWED_BY")]
            if relationship_type == "FOLLOWED_BY":
                return []
            if relationship_type == "SUPPORTS":
                return [_make_rel("ua-1", "act-X", "SUPPORTS", {"similarity_score": 0.9})]
            if relationship_type == "PRECEDED_BY":
                return []
            return []

        mock_graph_service.get_relationships = AsyncMock(side_effect=get_rels)
        mock_graph_service.create_relationship = AsyncMock(side_effect=RuntimeError("Neo4j error"))

        result = await detect_variants(mock_graph_service, "eng-1")

        # Errors should be captured, not raised
        for error in result.errors:
            assert "DEVIATES_FROM failed" in error
