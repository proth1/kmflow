"""BDD tests for I/O Mismatch and Control Gap Detection (Story #378).

Covers 3 acceptance scenarios:
1. I/O mismatch creates IO_MISMATCH ConflictObject
2. Control gap detected where policy requires governance
3. Shelf data request auto-generated for CONTROL_GAP

Plus unit tests for severity, idempotency, pipeline integration,
and shelf request deduplication.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import (
    MismatchType,
    ShelfDataRequest,
    ShelfRequestStatus,
)
from src.semantic.conflict_detection import (
    ControlGapDetector,
    DetectionResult,
    IOMismatchDetector,
    _activity_criticality,
    _create_shelf_requests_for_control_gaps,
    run_conflict_detection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = str(uuid.uuid4())
SOURCE_A = str(uuid.uuid4())
SOURCE_B = str(uuid.uuid4())


def _make_graph_service() -> MagicMock:
    """Create a mock graph service."""
    svc = MagicMock()
    svc.run_query = AsyncMock(return_value=[])
    return svc


def _make_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# ===========================================================================
# Scenario 1: I/O mismatch creates IO_MISMATCH ConflictObject
# ===========================================================================


class TestScenario1IOMismatch:
    """I/O mismatch detection when upstream output doesn't match downstream input."""

    @pytest.mark.asyncio
    async def test_io_mismatch_detected(self) -> None:
        """Given upstream 'Draft Report Preparation' does not produce 'Approved Report'
        And downstream 'Report Approval' consumes 'Approved Report'
        When the I/O mismatch detector runs
        Then an IO_MISMATCH ConflictObject is created."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "upstream_name": "Draft Report Preparation",
                    "downstream_name": "Report Approval",
                    "unmatched_artifact": "Approved Report",
                    "source_upstream": SOURCE_A,
                    "source_downstream": SOURCE_B,
                },
            ]
        )

        detector = IOMismatchDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 1
        assert conflicts[0].mismatch_type == MismatchType.IO_MISMATCH

    @pytest.mark.asyncio
    async def test_io_mismatch_references_artifacts(self) -> None:
        """Conflict references both activities and the unmatched artifact."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "upstream_name": "Draft Report Preparation",
                    "downstream_name": "Report Approval",
                    "unmatched_artifact": "Approved Report",
                    "source_upstream": SOURCE_A,
                    "source_downstream": SOURCE_B,
                },
            ]
        )

        detector = IOMismatchDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        detail = conflicts[0].conflict_detail
        assert detail["unmatched_artifact"] == "Approved Report"
        assert detail["upstream_activity"] == "Draft Report Preparation"
        assert detail["downstream_activity"] == "Report Approval"

    @pytest.mark.asyncio
    async def test_io_mismatch_severity_set(self) -> None:
        """Severity is set based on criticality of downstream activity."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "upstream_name": "Draft Report Preparation",
                    "downstream_name": "Report Approval",
                    "unmatched_artifact": "Approved Report",
                    "source_upstream": SOURCE_A,
                    "source_downstream": SOURCE_B,
                },
            ]
        )

        detector = IOMismatchDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert conflicts[0].severity_score == 0.7
        assert conflicts[0].severity_label == "high"

    @pytest.mark.asyncio
    async def test_io_no_mismatch_when_artifacts_match(self) -> None:
        """No conflicts when upstream output matches downstream input."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(return_value=[])

        detector = IOMismatchDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_io_mismatch_handles_graph_error(self) -> None:
        """Detector returns empty list on graph query failure."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(side_effect=Exception("Neo4j error"))

        detector = IOMismatchDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 0


# ===========================================================================
# Scenario 2: Control gap detected where policy requires governance
# ===========================================================================


class TestScenario2ControlGap:
    """Control gap detection for activities missing required GOVERNED_BY edges."""

    @pytest.mark.asyncio
    async def test_control_gap_detected(self) -> None:
        """Given 'Process Payment' has no GOVERNED_BY edge
        And a ControlRequirement exists for financial processing
        When the control gap detector runs
        Then a CONTROL_GAP ConflictObject is created."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "activity_name": "Process Payment",
                    "requirement_name": "Financial Governance Requirement",
                    "required_control": "Financial Processing Control",
                    "policy_source_id": SOURCE_B,
                    "criticality": None,
                    "activity_source_id": SOURCE_A,
                },
            ]
        )

        detector = ControlGapDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 1
        assert conflicts[0].mismatch_type == MismatchType.CONTROL_GAP

    @pytest.mark.asyncio
    async def test_control_gap_references_policy(self) -> None:
        """Conflict references the policy evidence that specifies the requirement."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "activity_name": "Process Payment",
                    "requirement_name": "Financial Governance Requirement",
                    "required_control": "Financial Processing Control",
                    "policy_source_id": SOURCE_B,
                    "criticality": None,
                    "activity_source_id": SOURCE_A,
                },
            ]
        )

        detector = ControlGapDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert conflicts[0].source_b_id == SOURCE_B
        detail = conflicts[0].conflict_detail
        assert detail["policy_source_id"] == SOURCE_B
        assert detail["required_control"] == "Financial Processing Control"

    @pytest.mark.asyncio
    async def test_control_gap_high_severity_for_financial(self) -> None:
        """Severity is high for financial processing activities."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "activity_name": "Process Payment",
                    "requirement_name": "Financial Governance Requirement",
                    "required_control": "Financial Processing Control",
                    "policy_source_id": SOURCE_B,
                    "criticality": None,
                    "activity_source_id": SOURCE_A,
                },
            ]
        )

        detector = ControlGapDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        # "payment" keyword → 0.9 severity
        assert conflicts[0].severity_score == 0.9
        assert conflicts[0].severity_label == "critical"

    @pytest.mark.asyncio
    async def test_control_gap_explicit_criticality(self) -> None:
        """When criticality is set on the ControlRequirement, use it directly."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(
            return_value=[
                {
                    "activity_name": "General Activity",
                    "requirement_name": "General Requirement",
                    "required_control": "Operational Control",
                    "policy_source_id": SOURCE_B,
                    "criticality": 0.75,
                    "activity_source_id": SOURCE_A,
                },
            ]
        )

        detector = ControlGapDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert conflicts[0].severity_score == 0.75

    @pytest.mark.asyncio
    async def test_control_gap_handles_graph_error(self) -> None:
        """Detector returns empty list on graph query failure."""
        graph = _make_graph_service()
        graph.run_query = AsyncMock(side_effect=Exception("Neo4j error"))

        detector = ControlGapDetector(graph)
        conflicts = await detector.detect(ENGAGEMENT_ID)

        assert len(conflicts) == 0


# ===========================================================================
# Scenario 3: Shelf data request auto-generated for CONTROL_GAP
# ===========================================================================


class TestScenario3ShelfDataRequest:
    """Shelf data request auto-generation for control gaps."""

    @pytest.mark.asyncio
    async def test_shelf_request_created(self) -> None:
        """Given a CONTROL_GAP for 'Process Payment'
        When the auto shelf request generator runs
        Then a shelf data request is created."""
        session = _make_session()
        from src.semantic.conflict_detection import DetectedConflict

        gap_conflict = DetectedConflict(
            mismatch_type=MismatchType.CONTROL_GAP,
            engagement_id=ENGAGEMENT_ID,
            source_a_id=SOURCE_A,
            source_b_id=SOURCE_B,
            severity_score=0.9,
            severity_label="critical",
            detail="Control gap: 'Process Payment'",
            conflict_detail={
                "activity": "Process Payment",
                "required_control": "Financial Processing Control",
            },
        )

        eng_uuid = uuid.UUID(ENGAGEMENT_ID)
        count = await _create_shelf_requests_for_control_gaps(session, eng_uuid, [gap_conflict])

        assert count == 1
        session.add.assert_called_once()
        added_request = session.add.call_args[0][0]
        assert isinstance(added_request, ShelfDataRequest)

    @pytest.mark.asyncio
    async def test_shelf_request_title_format(self) -> None:
        """Request title follows 'Evidence required: governance control for [X]' pattern."""
        session = _make_session()
        from src.semantic.conflict_detection import DetectedConflict

        gap_conflict = DetectedConflict(
            mismatch_type=MismatchType.CONTROL_GAP,
            engagement_id=ENGAGEMENT_ID,
            source_a_id=SOURCE_A,
            source_b_id=SOURCE_B,
            severity_score=0.9,
            severity_label="critical",
            detail="",
            conflict_detail={
                "activity": "Process Payment",
                "required_control": "Financial Processing Control",
            },
        )

        eng_uuid = uuid.UUID(ENGAGEMENT_ID)
        await _create_shelf_requests_for_control_gaps(session, eng_uuid, [gap_conflict])

        added_request = session.add.call_args[0][0]
        assert added_request.title == "Evidence required: governance control for [Process Payment]"

    @pytest.mark.asyncio
    async def test_shelf_request_body_specifies_evidence_types(self) -> None:
        """Request body specifies what evidence types would satisfy the gap."""
        session = _make_session()
        from src.semantic.conflict_detection import DetectedConflict

        gap_conflict = DetectedConflict(
            mismatch_type=MismatchType.CONTROL_GAP,
            engagement_id=ENGAGEMENT_ID,
            source_a_id=SOURCE_A,
            source_b_id=SOURCE_B,
            severity_score=0.9,
            severity_label="critical",
            detail="",
            conflict_detail={
                "activity": "Process Payment",
                "required_control": "Financial Processing Control",
            },
        )

        eng_uuid = uuid.UUID(ENGAGEMENT_ID)
        await _create_shelf_requests_for_control_gaps(session, eng_uuid, [gap_conflict])

        added_request = session.add.call_args[0][0]
        body = added_request.description
        assert "control register" in body.lower()
        assert "audit report" in body.lower()
        assert "policy procedure" in body.lower()

    @pytest.mark.asyncio
    async def test_shelf_request_status_open(self) -> None:
        """Shelf data request is created with OPEN status."""
        session = _make_session()
        from src.semantic.conflict_detection import DetectedConflict

        gap_conflict = DetectedConflict(
            mismatch_type=MismatchType.CONTROL_GAP,
            engagement_id=ENGAGEMENT_ID,
            source_a_id=SOURCE_A,
            source_b_id=SOURCE_B,
            severity_score=0.9,
            severity_label="critical",
            detail="",
            conflict_detail={
                "activity": "Process Payment",
                "required_control": "Financial Processing Control",
            },
        )

        eng_uuid = uuid.UUID(ENGAGEMENT_ID)
        await _create_shelf_requests_for_control_gaps(session, eng_uuid, [gap_conflict])

        added_request = session.add.call_args[0][0]
        assert added_request.status == ShelfRequestStatus.OPEN

    @pytest.mark.asyncio
    async def test_shelf_request_deduplicated(self) -> None:
        """Duplicate shelf requests are not created."""
        session = _make_session()
        from src.semantic.conflict_detection import DetectedConflict

        # Session returns existing request with same title
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()
        session.execute = AsyncMock(return_value=existing_result)

        gap_conflict = DetectedConflict(
            mismatch_type=MismatchType.CONTROL_GAP,
            engagement_id=ENGAGEMENT_ID,
            source_a_id=SOURCE_A,
            source_b_id=SOURCE_B,
            severity_score=0.9,
            severity_label="critical",
            detail="",
            conflict_detail={
                "activity": "Process Payment",
                "required_control": "Financial Processing Control",
            },
        )

        eng_uuid = uuid.UUID(ENGAGEMENT_ID)
        count = await _create_shelf_requests_for_control_gaps(session, eng_uuid, [gap_conflict])

        assert count == 0
        session.add.assert_not_called()


# ===========================================================================
# Activity criticality scoring
# ===========================================================================


class TestActivityCriticality:
    """Test keyword-based activity criticality scoring."""

    def test_financial_keyword(self) -> None:
        assert _activity_criticality("Process Financial Transaction") == 0.9

    def test_payment_keyword(self) -> None:
        assert _activity_criticality("Process Payment") == 0.9

    def test_approval_keyword(self) -> None:
        assert _activity_criticality("Manager Approval") == 0.8

    def test_compliance_keyword(self) -> None:
        assert _activity_criticality("Compliance Review") == 0.8

    def test_unknown_keyword(self) -> None:
        assert _activity_criticality("Send Email") == 0.6

    def test_none_activity(self) -> None:
        assert _activity_criticality(None) == 0.6

    def test_multi_keyword_returns_highest(self) -> None:
        """When multiple keywords match, return the highest criticality."""
        # "financial" (0.9) + "compliance" (0.8) + "audit" (0.75) → max = 0.9
        assert _activity_criticality("Financial Compliance Audit") == 0.9


# ===========================================================================
# Pipeline integration
# ===========================================================================


class TestPipelineIntegration:
    """Test that the full pipeline runs all 6 detectors."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_io_and_control_gap_detectors(self) -> None:
        """Pipeline includes I/O mismatch and control gap detection."""
        graph = _make_graph_service()
        session = _make_session()

        async def _mock_query(query: str, params: dict) -> list:
            # Match on query content instead of call ordering
            if "CONSUMES" in query and "NOT EXISTS" in query:
                return [
                    {
                        "upstream_name": "Prepare Report",
                        "downstream_name": "Review Report",
                        "unmatched_artifact": "Final",
                        "source_upstream": SOURCE_A,
                        "source_downstream": SOURCE_B,
                    },
                ]
            if "ControlRequirement" in query:
                return [
                    {
                        "activity_name": "Process Payment",
                        "requirement_name": "Financial Control",
                        "required_control": "Governance",
                        "policy_source_id": SOURCE_B,
                        "criticality": None,
                        "activity_source_id": SOURCE_A,
                    },
                ]
            return []

        graph.run_query = AsyncMock(side_effect=_mock_query)

        result = await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        assert result.io_conflicts_found == 1
        assert result.control_gap_conflicts_found == 1
        assert result.total_conflicts >= 2

    @pytest.mark.asyncio
    async def test_pipeline_creates_shelf_requests_for_gaps(self) -> None:
        """Pipeline auto-generates shelf requests for control gaps."""
        graph = _make_graph_service()
        session = _make_session()

        async def _mock_query(query: str, params: dict) -> list:
            if "ControlRequirement" in query:
                return [
                    {
                        "activity_name": "Process Payment",
                        "requirement_name": "Financial Control",
                        "required_control": "Governance",
                        "policy_source_id": SOURCE_B,
                        "criticality": None,
                        "activity_source_id": SOURCE_A,
                    },
                ]
            return []

        graph.run_query = AsyncMock(side_effect=_mock_query)

        result = await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        assert result.shelf_requests_created == 1

    @pytest.mark.asyncio
    async def test_pipeline_persists_io_and_gap_conflicts(self) -> None:
        """Pipeline persists IO_MISMATCH and CONTROL_GAP ConflictObjects."""
        graph = _make_graph_service()
        session = _make_session()

        async def _mock_query(query: str, params: dict) -> list:
            if "CONSUMES" in query and "NOT EXISTS" in query:
                return [
                    {
                        "upstream_name": "A",
                        "downstream_name": "B",
                        "unmatched_artifact": "Y",
                        "source_upstream": SOURCE_A,
                        "source_downstream": SOURCE_B,
                    },
                ]
            return []

        graph.run_query = AsyncMock(side_effect=_mock_query)

        await run_conflict_detection(graph, session, ENGAGEMENT_ID)

        # session.add should have been called for the IO conflict
        assert session.add.call_count >= 1


# ===========================================================================
# DetectionResult field tests
# ===========================================================================


class TestDetectionResultFields:
    """Verify new fields on DetectionResult."""

    def test_io_conflicts_found_default(self) -> None:
        result = DetectionResult(engagement_id="test")
        assert result.io_conflicts_found == 0

    def test_control_gap_conflicts_found_default(self) -> None:
        result = DetectionResult(engagement_id="test")
        assert result.control_gap_conflicts_found == 0

    def test_shelf_requests_created_default(self) -> None:
        result = DetectionResult(engagement_id="test")
        assert result.shelf_requests_created == 0
