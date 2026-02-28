"""BDD tests for Structured Reviewer Actions (Story #353).

Tests all five acceptance scenarios from the GitHub issue.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models.conflict import ConflictObject, MismatchType
from src.core.models.pov import EvidenceGrade
from src.core.models.validation_decision import ReviewerAction, ValidationDecision
from src.core.services.reviewer_actions_service import (
    GRADE_PROMOTION,
    ReviewerActionsService,
)

ENGAGEMENT_ID = uuid.uuid4()
REVIEW_PACK_ID = uuid.uuid4()
REVIEWER_ID = uuid.uuid4()


def _make_service(
    query_results: list[dict] | None = None,
) -> tuple[ReviewerActionsService, AsyncMock, AsyncMock]:
    """Create service with mocked graph and session."""
    graph = AsyncMock()
    graph.run_query = AsyncMock(return_value=query_results or [])
    graph.run_write_query = AsyncMock(return_value=None)

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    service = ReviewerActionsService(graph=graph, session=session)
    return service, graph, session


# ── Scenario 1: CONFIRM Action — Evidence Grade Promotion ──────────────


class TestConfirmAction:
    """Given an SME reviews an activity assertion with evidence grade C
    When the SME submits a CONFIRM action for that assertion
    Then the evidence grade is promoted from C to B
      And the confidence score for the element increases accordingly
      And a ValidationDecision entity is created with action=CONFIRM
    """

    @pytest.mark.asyncio
    async def test_promotes_grade_c_to_b(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "C", "confidence": 0.5}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_001",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        assert result["action"] == "confirm"
        wb = result["graph_write_back"]
        assert wb["previous_grade"] == "C"
        assert wb["new_grade"] == "B"

    @pytest.mark.asyncio
    async def test_promotes_grade_b_to_a(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "B", "confidence": 0.7}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_002",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        wb = result["graph_write_back"]
        assert wb["new_grade"] == "A"

    @pytest.mark.asyncio
    async def test_caps_at_grade_a(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "A", "confidence": 0.9}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_003",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        wb = result["graph_write_back"]
        assert wb["new_grade"] == "A"

    @pytest.mark.asyncio
    async def test_increases_confidence_by_0_1(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "C", "confidence": 0.5}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_004",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        wb = result["graph_write_back"]
        assert wb["previous_confidence"] == 0.5
        assert wb["new_confidence"] == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_confidence_capped_at_1(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "B", "confidence": 0.95}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_005",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        wb = result["graph_write_back"]
        assert wb["new_confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_persists_validation_decision(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "C", "confidence": 0.5}]
        )

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_006",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, ValidationDecision)
        assert added.action == "confirm"
        assert added.engagement_id == ENGAGEMENT_ID

    @pytest.mark.asyncio
    async def test_writes_to_graph_with_engagement_scope(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "C", "confidence": 0.5}]
        )

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_007",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        # Both read and write queries must include engagement_id
        read_call = graph.run_query.call_args
        assert "engagement_id" in read_call[0][0]  # Cypher query text
        assert str(ENGAGEMENT_ID) in str(read_call[0][1].values())

        write_call = graph.run_write_query.call_args
        assert "engagement_id" in write_call[0][0]


# ── Scenario 2: CORRECT Action — Superseding Assertion ─────────────────


class TestCorrectAction:
    """Given an SME identifies an error in an activity assertion
    When the SME submits a CORRECT action with corrected data
    Then a new assertion is created in the knowledge graph
      And a SUPERSEDES edge links the new assertion to the original
      And the original assertion is retracted with retracted_at
      And a ValidationDecision entity is created with action=CORRECT
    """

    @pytest.mark.asyncio
    async def test_creates_superseding_assertion(self) -> None:
        service, graph, session = _make_service()

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_010",
            action=ReviewerAction.CORRECT,
            reviewer_id=REVIEWER_ID,
            payload={
                "corrected_data": {"name": "Fixed Name"},
                "correction_note": "Typo in activity name",
            },
        )

        wb = result["graph_write_back"]
        assert wb["action"] == "correct"
        assert wb["retracted"] is True
        assert wb["supersedes_edge_created"] is True
        assert wb["original_element_id"] == "elem_010"
        assert wb["new_assertion_id"]  # non-empty

    @pytest.mark.asyncio
    async def test_retracts_original(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_011",
            action=ReviewerAction.CORRECT,
            reviewer_id=REVIEWER_ID,
            payload={"correction_note": "Wrong role"},
        )

        # First write query should set retracted_at on original
        first_write = graph.run_write_query.call_args_list[0]
        cypher = first_write[0][0]
        assert "retracted_at" in cypher
        assert "SUPERSEDES" in cypher

    @pytest.mark.asyncio
    async def test_applies_safe_corrected_properties(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_012",
            action=ReviewerAction.CORRECT,
            reviewer_id=REVIEWER_ID,
            payload={
                "corrected_data": {"name": "Corrected", "description": "Updated desc"},
            },
        )

        # Should have 2 write calls: create+supersede, then apply properties
        assert graph.run_write_query.call_count == 2
        second_write = graph.run_write_query.call_args_list[1]
        cypher = second_write[0][0]
        assert "a.name" in cypher
        assert "a.description" in cypher

    @pytest.mark.asyncio
    async def test_rejects_unsafe_property_names(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_013",
            action=ReviewerAction.CORRECT,
            reviewer_id=REVIEWER_ID,
            payload={
                "corrected_data": {"malicious_key": "DROP DATABASE"},
            },
        )

        # Only 1 write call (create+supersede), no property application
        assert graph.run_write_query.call_count == 1

    @pytest.mark.asyncio
    async def test_persists_decision_with_correct_action(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_014",
            action=ReviewerAction.CORRECT,
            reviewer_id=REVIEWER_ID,
        )

        added = session.add.call_args[0][0]
        assert isinstance(added, ValidationDecision)
        assert added.action == "correct"


# ── Scenario 3: REJECT Action — ConflictObject Creation ────────────────


class TestRejectAction:
    """Given an SME determines an activity assertion is incorrect
    When the SME submits a REJECT action with a rejection reason
    Then the assertion is marked as rejected in the knowledge graph
      And a ConflictObject is created capturing the rejection and reason
      And a ValidationDecision entity is created with action=REJECT
    """

    @pytest.mark.asyncio
    async def test_marks_rejected_in_graph(self) -> None:
        service, graph, session = _make_service()

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_020",
            action=ReviewerAction.REJECT,
            reviewer_id=REVIEWER_ID,
            payload={"rejection_reason": "Data is fabricated"},
        )

        wb = result["graph_write_back"]
        assert wb["action"] == "reject"
        assert wb["rejection_reason"] == "Data is fabricated"

        # First write should mark rejected with engagement scoping
        first_write = graph.run_write_query.call_args_list[0]
        cypher = first_write[0][0]
        assert "rejected" in cypher
        assert "engagement_id" in cypher

    @pytest.mark.asyncio
    async def test_creates_conflict_object_in_postgres(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_021",
            action=ReviewerAction.REJECT,
            reviewer_id=REVIEWER_ID,
            payload={"rejection_reason": "Invalid assertion"},
        )

        # session.add called twice: ConflictObject + ValidationDecision
        assert session.add.call_count == 2
        conflict = session.add.call_args_list[0][0][0]
        assert isinstance(conflict, ConflictObject)
        assert conflict.mismatch_type == MismatchType.EXISTENCE_MISMATCH
        assert conflict.severity == 0.8
        assert conflict.escalation_flag is True

    @pytest.mark.asyncio
    async def test_creates_conflict_node_in_neo4j(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_022",
            action=ReviewerAction.REJECT,
            reviewer_id=REVIEWER_ID,
        )

        # Second write creates ConflictObject node with INVOLVES edge
        second_write = graph.run_write_query.call_args_list[1]
        cypher = second_write[0][0]
        assert "ConflictObject" in cypher
        assert "INVOLVES" in cypher
        assert "engagement_id" in cypher

    @pytest.mark.asyncio
    async def test_returns_conflict_id(self) -> None:
        service, graph, session = _make_service()

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_023",
            action=ReviewerAction.REJECT,
            reviewer_id=REVIEWER_ID,
        )

        assert "conflict_id" in result["graph_write_back"]


# ── Scenario 4: DEFER Action — Dark Room Backlog ──────────────────────


class TestDeferAction:
    """Given an SME cannot validate an activity assertion at this time
    When the SME submits a DEFER action
    Then the element is added to the Dark Room backlog
      And no modification is made to the existing assertion
      And a ValidationDecision entity is created with action=DEFER
    """

    @pytest.mark.asyncio
    async def test_no_graph_modification(self) -> None:
        service, graph, session = _make_service()

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_030",
            action=ReviewerAction.DEFER,
            reviewer_id=REVIEWER_ID,
            payload={"defer_reason": "Need more evidence"},
        )

        wb = result["graph_write_back"]
        assert wb["action"] == "defer"
        assert wb["deferred_to_dark_room"] is True

        # No graph write operations for DEFER
        graph.run_write_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_persists_decision(self) -> None:
        service, graph, session = _make_service()

        await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_031",
            action=ReviewerAction.DEFER,
            reviewer_id=REVIEWER_ID,
        )

        added = session.add.call_args[0][0]
        assert isinstance(added, ValidationDecision)
        assert added.action == "defer"

    @pytest.mark.asyncio
    async def test_returns_defer_reason(self) -> None:
        service, graph, session = _make_service()

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_032",
            action=ReviewerAction.DEFER,
            reviewer_id=REVIEWER_ID,
            payload={"defer_reason": "Awaiting client response"},
        )

        assert result["graph_write_back"]["defer_reason"] == "Awaiting client response"


# ── Scenario 5: Decision API Response ─────────────────────────────────


class TestDecisionResponse:
    """Given a valid review pack with pending items
    When a decision is submitted
    Then the response includes decision_id, action, element_id,
      graph write-back result, and decision timestamp
    """

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self) -> None:
        service, graph, session = _make_service(
            query_results=[{"grade": "C", "confidence": 0.5}]
        )

        result = await service.submit_decision(
            engagement_id=ENGAGEMENT_ID,
            review_pack_id=REVIEW_PACK_ID,
            element_id="elem_040",
            action=ReviewerAction.CONFIRM,
            reviewer_id=REVIEWER_ID,
        )

        assert "decision_id" in result
        assert result["action"] == "confirm"
        assert result["element_id"] == "elem_040"
        assert "graph_write_back" in result
        assert "decision_at" in result


# ── Grade Promotion Mapping ───────────────────────────────────────────


class TestGradePromotion:
    """Verify the evidence grade promotion mapping is correct."""

    def test_u_promotes_to_d(self) -> None:
        assert GRADE_PROMOTION[EvidenceGrade.U] == EvidenceGrade.D

    def test_d_promotes_to_c(self) -> None:
        assert GRADE_PROMOTION[EvidenceGrade.D] == EvidenceGrade.C

    def test_c_promotes_to_b(self) -> None:
        assert GRADE_PROMOTION[EvidenceGrade.C] == EvidenceGrade.B

    def test_b_promotes_to_a(self) -> None:
        assert GRADE_PROMOTION[EvidenceGrade.B] == EvidenceGrade.A

    def test_a_stays_at_a(self) -> None:
        assert GRADE_PROMOTION[EvidenceGrade.A] == EvidenceGrade.A
