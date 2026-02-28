"""BDD tests for Story #372: Sequence and Role Conflict Detection.

Covers all 4 acceptance scenarios:
1. Sequence mismatch creates SEQUENCE_MISMATCH ConflictObject
2. Role mismatch creates ROLE_MISMATCH ConflictObject
3. No false positives when sequences agree
4. Severity scoring based on source weights and recency
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ConflictObject, MismatchType
from src.semantic.conflict_detection import (
    DetectionResult,
    RoleConflictDetector,
    SequenceConflictDetector,
    compute_severity,
    run_conflict_detection,
    severity_label,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_service(records: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock graph service that returns specified records."""
    svc = MagicMock()
    svc.run_query = AsyncMock(return_value=records or [])
    return svc


def _make_session(existing_conflict: ConflictObject | None = None) -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_conflict
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ===========================================================================
# Scenario 1: Sequence mismatch creates SEQUENCE_MISMATCH ConflictObject
# ===========================================================================


class TestSequenceMismatch:
    """Given Source A establishes X→Y and Source B establishes Y→X."""

    @pytest.mark.asyncio
    async def test_contradictory_sequence_detected(self) -> None:
        """A ConflictObject of type=SEQUENCE_MISMATCH is created."""
        src_a = str(uuid.uuid4())
        src_b = str(uuid.uuid4())
        graph = _make_graph_service(
            [
                {
                    "activity_a": "Review Application",
                    "activity_b": "Approve Application",
                    "source_a_id": src_a,
                    "source_b_id": src_b,
                    "weight_a": 0.8,
                    "weight_b": 0.6,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert len(conflicts) == 1
        assert conflicts[0].mismatch_type == MismatchType.SEQUENCE_MISMATCH

    @pytest.mark.asyncio
    async def test_conflict_linked_to_both_sources(self) -> None:
        """ConflictObject references both source evidence records."""
        src_a = str(uuid.uuid4())
        src_b = str(uuid.uuid4())
        graph = _make_graph_service(
            [
                {
                    "activity_a": "X",
                    "activity_b": "Y",
                    "source_a_id": src_a,
                    "source_b_id": src_b,
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert conflicts[0].source_a_id == src_a
        assert conflicts[0].source_b_id == src_b

    @pytest.mark.asyncio
    async def test_conflict_has_edge_data(self) -> None:
        """ConflictObject is linked to both conflicting PRECEDES edges."""
        graph = _make_graph_service(
            [
                {
                    "activity_a": "X",
                    "activity_b": "Y",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert conflicts[0].edge_a_data["from"] == "X"
        assert conflicts[0].edge_a_data["to"] == "Y"
        assert conflicts[0].edge_b_data["from"] == "Y"
        assert conflicts[0].edge_b_data["to"] == "X"

    @pytest.mark.asyncio
    async def test_conflict_detail_describes_contradiction(self) -> None:
        """Detail string describes the contradictory sequence."""
        graph = _make_graph_service(
            [
                {
                    "activity_a": "Step1",
                    "activity_b": "Step2",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert "Step1" in conflicts[0].detail
        assert "Step2" in conflicts[0].detail

    @pytest.mark.asyncio
    async def test_sequence_cypher_uses_engagement_filter(self) -> None:
        """Cypher query filters by engagement_id."""
        graph = _make_graph_service([])
        detector = SequenceConflictDetector(graph)
        await detector.detect("eng-123")

        graph.run_query.assert_called_once()
        call_args = graph.run_query.call_args
        assert call_args[0][1]["engagement_id"] == "eng-123"


# ===========================================================================
# Scenario 2: Role mismatch creates ROLE_MISMATCH ConflictObject
# ===========================================================================


class TestRoleMismatch:
    """Given different sources assign different roles to same activity."""

    @pytest.mark.asyncio
    async def test_role_mismatch_detected(self) -> None:
        """ConflictObject of type=ROLE_MISMATCH is created."""
        graph = _make_graph_service(
            [
                {
                    "activity_name": "Verify Application",
                    "role_a": "Analyst",
                    "role_b": "Manager",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.7,
                    "weight_b": 0.9,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = RoleConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert len(conflicts) == 1
        assert conflicts[0].mismatch_type == MismatchType.ROLE_MISMATCH

    @pytest.mark.asyncio
    async def test_role_conflict_references_activity_and_roles(self) -> None:
        """Conflict references the activity node and both role assignments."""
        graph = _make_graph_service(
            [
                {
                    "activity_name": "Verify Application",
                    "role_a": "Analyst",
                    "role_b": "Manager",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = RoleConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert conflicts[0].edge_a_data["activity"] == "Verify Application"
        assert conflicts[0].edge_a_data["role"] == "Analyst"
        assert conflicts[0].edge_b_data["role"] == "Manager"

    @pytest.mark.asyncio
    async def test_role_severity_reflects_weight_differential(self) -> None:
        """Severity reflects the authority weight differential."""
        graph = _make_graph_service(
            [
                {
                    "activity_name": "Check",
                    "role_a": "Jr Analyst",
                    "role_b": "Sr Manager",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.3,
                    "weight_b": 0.9,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = RoleConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        # High weight differential → lower severity
        assert conflicts[0].severity_score < 0.5

    @pytest.mark.asyncio
    async def test_role_detail_includes_both_roles(self) -> None:
        """Detail string includes activity name and both roles."""
        graph = _make_graph_service(
            [
                {
                    "activity_name": "Submit Report",
                    "role_a": "Clerk",
                    "role_b": "Supervisor",
                    "source_a_id": str(uuid.uuid4()),
                    "source_b_id": str(uuid.uuid4()),
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )

        detector = RoleConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert "Submit Report" in conflicts[0].detail
        assert "Clerk" in conflicts[0].detail
        assert "Supervisor" in conflicts[0].detail


# ===========================================================================
# Scenario 3: No false positives when sequences agree
# ===========================================================================


class TestNoFalsePositives:
    """Given two sources agree on the sequence X→Y→Z."""

    @pytest.mark.asyncio
    async def test_no_conflicts_when_sequences_agree(self) -> None:
        """No SEQUENCE_MISMATCH created when sources agree."""
        # Empty records = no contradictory edges found
        graph = _make_graph_service([])
        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_no_conflicts_when_roles_agree(self) -> None:
        """No ROLE_MISMATCH created when role assignments match."""
        graph = _make_graph_service([])
        detector = RoleConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_detection_result_zero_conflicts(self) -> None:
        """Detection result confirms 0 conflicts."""
        graph = _make_graph_service([])
        session = _make_session()
        result = await run_conflict_detection(graph, session, str(uuid.uuid4()))

        assert result.total_conflicts == 0

    @pytest.mark.asyncio
    async def test_graph_error_returns_empty(self) -> None:
        """Graph query failure returns empty conflicts, not crash."""
        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=ConnectionError("Neo4j down"))

        detector = SequenceConflictDetector(graph)
        conflicts = await detector.detect("eng-001")

        assert len(conflicts) == 0


# ===========================================================================
# Scenario 4: Severity scoring based on source weights and recency
# ===========================================================================


class TestSeverityScoring:
    """Given conflicts with varying source weights and recency."""

    def test_equal_weights_high_severity(self) -> None:
        """Similar-authority sources → higher severity (genuinely ambiguous)."""
        score = compute_severity(0.5, 0.5)
        assert score >= 0.8  # Near 1.0 when weights are equal

    def test_high_weight_differential_low_severity(self) -> None:
        """High weight differential → lower severity (less ambiguous)."""
        score = compute_severity(0.9, 0.3)
        assert score < 0.5

    def test_recency_reduces_severity(self) -> None:
        """Recent high-authority source reduces severity."""
        now = datetime.now(UTC)
        recent = now - timedelta(days=1)
        old = now - timedelta(days=90)

        score_recent = compute_severity(0.8, 0.5, created_a=recent, created_b=old)
        score_old = compute_severity(0.8, 0.5, created_a=old, created_b=old)

        assert score_recent < score_old

    def test_severity_bounded_0_to_1(self) -> None:
        """Severity score is always between 0 and 1."""
        for wa in [0.0, 0.5, 1.0]:
            for wb in [0.0, 0.5, 1.0]:
                score = compute_severity(wa, wb)
                assert 0.0 <= score <= 1.0

    def test_severity_label_critical(self) -> None:
        """Score >= 0.8 maps to 'critical'."""
        assert severity_label(0.95) == "critical"
        assert severity_label(0.8) == "critical"

    def test_severity_label_high(self) -> None:
        """Score 0.6-0.79 maps to 'high'."""
        assert severity_label(0.7) == "high"
        assert severity_label(0.6) == "high"

    def test_severity_label_medium(self) -> None:
        """Score 0.4-0.59 maps to 'medium'."""
        assert severity_label(0.5) == "medium"
        assert severity_label(0.4) == "medium"

    def test_severity_label_low(self) -> None:
        """Score < 0.4 maps to 'low'."""
        assert severity_label(0.3) == "low"
        assert severity_label(0.1) == "low"

    def test_severity_symmetry(self) -> None:
        """Severity is symmetric: compute_severity(a, b) == compute_severity(b, a)."""
        score_ab = compute_severity(0.7, 0.3)
        score_ba = compute_severity(0.3, 0.7)
        assert score_ab == score_ba


# ===========================================================================
# Pipeline integration tests
# ===========================================================================


class TestConflictDetectionPipeline:
    """Test the full detection pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_persists_new_conflicts(self) -> None:
        """New conflicts are persisted as ConflictObjects."""
        src_a = str(uuid.uuid4())
        src_b = str(uuid.uuid4())
        eng_id = str(uuid.uuid4())

        graph = _make_graph_service(
            [
                {
                    "activity_a": "X",
                    "activity_b": "Y",
                    "source_a_id": src_a,
                    "source_b_id": src_b,
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )
        session = _make_session(existing_conflict=None)

        result = await run_conflict_detection(graph, session, eng_id)

        assert result.total_conflicts >= 1
        assert session.add.called
        assert session.flush.called

    @pytest.mark.asyncio
    async def test_pipeline_idempotent_no_duplicates(self) -> None:
        """Re-running does not create duplicate ConflictObjects."""
        src_a = str(uuid.uuid4())
        src_b = str(uuid.uuid4())
        eng_id = str(uuid.uuid4())

        graph = _make_graph_service(
            [
                {
                    "activity_a": "X",
                    "activity_b": "Y",
                    "source_a_id": src_a,
                    "source_b_id": src_b,
                    "weight_a": 0.5,
                    "weight_b": 0.5,
                    "created_a": None,
                    "created_b": None,
                }
            ]
        )
        # Existing conflict found
        existing = MagicMock(spec=ConflictObject)
        session = _make_session(existing_conflict=existing)

        await run_conflict_detection(graph, session, eng_id)

        # Should not add new objects since existing found
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_detection_result_structure(self) -> None:
        """DetectionResult has correct structure."""
        result = DetectionResult(engagement_id="eng-1")
        assert result.total_conflicts == 0
        assert result.sequence_conflicts_found == 0
        assert result.role_conflicts_found == 0

    @pytest.mark.asyncio
    async def test_pipeline_combines_sequence_and_role(self) -> None:
        """Pipeline detects both sequence and role mismatches."""
        eng_id = str(uuid.uuid4())

        # Graph returns results for both queries
        call_count = 0

        async def mock_run_query(query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if "PRECEDES" in query and "PRECEDES" in query.split("WITH")[1]:
                # Sequence query
                return [
                    {
                        "activity_a": "A",
                        "activity_b": "B",
                        "source_a_id": str(uuid.uuid4()),
                        "source_b_id": str(uuid.uuid4()),
                        "weight_a": 0.5,
                        "weight_b": 0.5,
                        "created_a": None,
                        "created_b": None,
                    }
                ]
            elif "PERFORMED_BY" in query:
                # Role query
                return [
                    {
                        "activity_name": "Check",
                        "role_a": "Analyst",
                        "role_b": "Manager",
                        "source_a_id": str(uuid.uuid4()),
                        "source_b_id": str(uuid.uuid4()),
                        "weight_a": 0.5,
                        "weight_b": 0.5,
                        "created_a": None,
                        "created_b": None,
                    }
                ]
            return []

        graph = MagicMock()
        graph.run_query = AsyncMock(side_effect=mock_run_query)
        session = _make_session(existing_conflict=None)

        result = await run_conflict_detection(graph, session, eng_id)

        assert result.total_conflicts == 2
        types = {c.mismatch_type for c in result.conflicts}
        assert MismatchType.SEQUENCE_MISMATCH in types
        assert MismatchType.ROLE_MISMATCH in types
