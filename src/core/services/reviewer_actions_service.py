"""Structured reviewer actions service (Story #353).

Implements CONFIRM, CORRECT, REJECT, DEFER actions with
corresponding knowledge graph write-back operations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.conflict import ConflictObject, MismatchType, ResolutionStatus
from src.core.models.pov import EvidenceGrade
from src.core.models.validation_decision import ReviewerAction, ValidationDecision
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)

# Evidence grade promotion mapping: current -> promoted
GRADE_PROMOTION: dict[EvidenceGrade, EvidenceGrade] = {
    EvidenceGrade.U: EvidenceGrade.D,
    EvidenceGrade.D: EvidenceGrade.C,
    EvidenceGrade.C: EvidenceGrade.B,
    EvidenceGrade.B: EvidenceGrade.A,
    EvidenceGrade.A: EvidenceGrade.A,  # Already max
}

# Domain constants
CONFIDENCE_BOOST = 0.1
REJECT_SEVERITY = 0.8


class ReviewerActionsService:
    """Handles structured reviewer actions with graph write-back."""

    def __init__(
        self,
        graph: KnowledgeGraphService,
        session: AsyncSession,
    ) -> None:
        self._graph = graph
        self._session = session

    async def submit_decision(
        self,
        *,
        engagement_id: uuid.UUID,
        review_pack_id: uuid.UUID,
        element_id: str,
        action: ReviewerAction,
        reviewer_id: uuid.UUID,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a reviewer decision and execute graph write-back.

        Routes to the appropriate handler based on action type.
        """
        handlers = {
            ReviewerAction.CONFIRM: self._handle_confirm,
            ReviewerAction.CORRECT: self._handle_correct,
            ReviewerAction.REJECT: self._handle_reject,
            ReviewerAction.DEFER: self._handle_defer,
        }

        handler = handlers[action]
        write_back_result = await handler(
            element_id=element_id,
            engagement_id=engagement_id,
            reviewer_id=reviewer_id,
            payload=payload or {},
        )

        # Persist the decision
        decision = ValidationDecision(
            engagement_id=engagement_id,
            review_pack_id=review_pack_id,
            element_id=element_id,
            action=action.value,
            reviewer_id=reviewer_id,
            payload=payload,
            graph_write_back_result=write_back_result,
        )
        self._session.add(decision)
        await self._session.flush()

        logger.info(
            "Decision submitted: action=%s, element=%s, reviewer=%s",
            action.value,
            element_id,
            reviewer_id,
        )

        return {
            "decision_id": str(decision.id),
            "action": action.value,
            "element_id": element_id,
            "graph_write_back": write_back_result,
            "decision_at": decision.decision_at.isoformat() if decision.decision_at else datetime.now(UTC).isoformat(),
        }

    async def _handle_confirm(
        self,
        *,
        element_id: str,
        engagement_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """CONFIRM: Promote evidence grade and increase confidence.

        Grade promotion: C->B, B->A (capped at A).
        """
        # Get current grade from Neo4j (scoped to engagement + labeled)
        result = await self._graph.run_query(
            """
            MATCH (a:Assertion {id: $element_id, engagement_id: $engagement_id})
            RETURN a.evidence_grade AS grade, a.confidence_score AS confidence
            """,
            {
                "element_id": element_id,
                "engagement_id": str(engagement_id),
            },
        )

        if not result:
            raise ValueError(f"Assertion {element_id} not found in graph")

        current_grade = result[0].get("grade", "C")
        current_confidence = result[0].get("confidence", 0.5)

        # Promote grade
        try:
            grade_enum = EvidenceGrade(current_grade)
        except ValueError:
            grade_enum = EvidenceGrade.C
        new_grade = GRADE_PROMOTION[grade_enum]

        # Confidence boost from confirmation
        new_confidence = min(1.0, current_confidence + CONFIDENCE_BOOST)

        # Update in Neo4j (scoped to engagement + labeled)
        await self._graph.run_write_query(
            """
            MATCH (a:Assertion {id: $element_id, engagement_id: $engagement_id})
            SET a.evidence_grade = $new_grade,
                a.confidence_score = $new_confidence,
                a.confirmed_at = datetime(),
                a.confirmed_by = $reviewer_id
            """,
            {
                "element_id": element_id,
                "engagement_id": str(engagement_id),
                "new_grade": new_grade.value,
                "new_confidence": new_confidence,
                "reviewer_id": str(reviewer_id),
            },
        )

        return {
            "action": "confirm",
            "previous_grade": current_grade,
            "new_grade": new_grade.value,
            "previous_confidence": current_confidence,
            "new_confidence": new_confidence,
        }

    async def _handle_correct(
        self,
        *,
        element_id: str,
        engagement_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """CORRECT: Create superseding assertion with SUPERSEDES edge.

        Retracts original assertion, creates new one with corrected data.
        """
        corrected_data = payload.get("corrected_data", {})
        correction_note = payload.get("correction_note", "")
        new_assertion_id = str(uuid.uuid4()).replace("-", "")[:16]

        # Validate corrected_data keys (prevent Cypher injection via property names)
        allowed_properties = frozenset(
            {
                "name",
                "description",
                "performing_role",
                "process_area",
                "frequency",
                "duration",
                "inputs",
                "outputs",
                "notes",
            }
        )
        safe_data = {k: v for k, v in corrected_data.items() if k in allowed_properties}

        # Create new assertion and SUPERSEDES edge, retract original (scoped)
        await self._graph.run_write_query(
            """
            MATCH (original {id: $element_id, engagement_id: $engagement_id})
            SET original.retracted_at = datetime(),
                original.retracted_reason = $correction_note

            CREATE (new_assertion:Assertion {
                id: $new_id,
                engagement_id: $engagement_id,
                corrected_from: $element_id,
                created_at: datetime()
            })

            MERGE (new_assertion)-[:SUPERSEDES]->(original)
            """,
            {
                "element_id": element_id,
                "new_id": new_assertion_id,
                "engagement_id": str(engagement_id),
                "correction_note": correction_note,
            },
        )

        # Apply corrected data properties to new assertion
        if safe_data:
            set_clauses = ", ".join(f"a.{k} = ${k}" for k in safe_data)
            await self._graph.run_write_query(
                f"""
                MATCH (a:Assertion {{id: $new_id, engagement_id: $engagement_id}})
                SET {set_clauses}
                """,
                {"new_id": new_assertion_id, "engagement_id": str(engagement_id), **safe_data},
            )

        return {
            "action": "correct",
            "original_element_id": element_id,
            "new_assertion_id": new_assertion_id,
            "retracted": True,
            "supersedes_edge_created": True,
        }

    async def _handle_reject(
        self,
        *,
        element_id: str,
        engagement_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """REJECT: Mark assertion as rejected and create ConflictObject."""
        rejection_reason = payload.get("rejection_reason", "")

        # Mark as rejected in Neo4j (scoped to engagement + labeled)
        await self._graph.run_write_query(
            """
            MATCH (a:Assertion {id: $element_id, engagement_id: $engagement_id})
            SET a.rejected = true,
                a.rejected_at = datetime(),
                a.rejection_reason = $reason
            """,
            {
                "element_id": element_id,
                "engagement_id": str(engagement_id),
                "reason": rejection_reason,
            },
        )

        # Create ConflictObject in PostgreSQL
        conflict = ConflictObject(
            engagement_id=engagement_id,
            mismatch_type=MismatchType.EXISTENCE_MISMATCH,
            resolution_status=ResolutionStatus.UNRESOLVED,
            severity=REJECT_SEVERITY,
            escalation_flag=True,
            conflict_detail={
                "element_id": element_id,
                "action": "reject",
                "rejection_reason": rejection_reason,
                "rejected_at": datetime.now(UTC).isoformat(),
            },
        )
        self._session.add(conflict)
        await self._session.flush()

        # Create ConflictObject node in Neo4j
        conflict_node_id = str(conflict.id).replace("-", "")[:16]
        await self._graph.run_write_query(
            """
            CREATE (co:ConflictObject {
                id: $conflict_id,
                mismatch_type: $mismatch_type,
                severity: $severity,
                engagement_id: $engagement_id,
                created_at: datetime()
            })
            WITH co
            MATCH (a:Assertion {id: $element_id, engagement_id: $engagement_id})
            MERGE (co)-[:INVOLVES]->(a)
            """,
            {
                "conflict_id": conflict_node_id,
                "mismatch_type": MismatchType.EXISTENCE_MISMATCH.value,
                "severity": REJECT_SEVERITY,
                "engagement_id": str(engagement_id),
                "element_id": element_id,
            },
        )

        return {
            "action": "reject",
            "element_id": element_id,
            "conflict_id": str(conflict.id),
            "rejection_reason": rejection_reason,
        }

    async def _handle_defer(
        self,
        *,
        element_id: str,
        engagement_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """DEFER: Add element to Dark Room backlog (no graph modification)."""
        defer_reason = payload.get("defer_reason", "")

        return {
            "action": "defer",
            "element_id": element_id,
            "deferred_to_dark_room": True,
            "defer_reason": defer_reason,
        }
