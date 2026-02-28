"""LLM Audit Trail service (Story #386).

Provides querying, hallucination flagging, stats computation, and
immutability enforcement for LLM interaction audit logs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.models.llm_audit import LLMAuditLog
from src.core.models.simulation import AlternativeSuggestion, SimulationScenario, SuggestionDisposition


class AuditLogImmutableError(Exception):
    """Raised when attempting to modify immutable audit log fields."""


# Fields that cannot be modified after creation
_IMMUTABLE_FIELDS = frozenset({
    "prompt_text", "response_text", "evidence_ids",
    "prompt_tokens", "completion_tokens", "model_name",
    "scenario_id", "user_id", "created_at",
})


@event.listens_for(Session, "before_flush")
def _enforce_immutability(session: Session, flush_context: Any, instances: Any) -> None:
    """Prevent modification of immutable LLMAuditLog fields."""
    for obj in session.dirty:
        if not isinstance(obj, LLMAuditLog):
            continue
        insp = inspect(obj)
        for field in _IMMUTABLE_FIELDS:
            hist = insp.attrs[field].history
            if hist.has_changes():
                raise AuditLogImmutableError(
                    f"Cannot modify immutable field '{field}' on LLMAuditLog"
                )


class LLMAuditService:
    """Service for LLM audit trail operations."""

    IMMUTABLE_FIELDS = _IMMUTABLE_FIELDS

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_engagement(
        self,
        *,
        engagement_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List LLM audit entries for an engagement with date range filter.

        Args:
            engagement_id: The engagement to query.
            from_date: Start of date range (inclusive).
            to_date: End of date range (inclusive).
            limit: Max items per page.
            offset: Items to skip.

        Returns:
            Paginated list with total count.
        """
        # Get scenario IDs for this engagement
        scenario_ids_query = select(SimulationScenario.id).where(
            SimulationScenario.engagement_id == engagement_id
        )

        base = select(LLMAuditLog).where(
            LLMAuditLog.scenario_id.in_(scenario_ids_query)
        )

        if from_date:
            base = base.where(LLMAuditLog.created_at >= from_date)
        if to_date:
            base = base.where(LLMAuditLog.created_at <= to_date)

        # Count
        count_q = select(func.count()).select_from(base.subquery())
        count_result = await self._session.execute(count_q)
        total = count_result.scalar() or 0

        # Fetch
        query = base.order_by(LLMAuditLog.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(query)
        logs = result.scalars().all()

        items = [self._serialize(log) for log in logs]

        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def flag_hallucination(
        self,
        *,
        audit_log_id: uuid.UUID,
        reason: str,
        flagged_by: uuid.UUID,
    ) -> dict[str, Any]:
        """Flag an audit log entry as containing a hallucination.

        Args:
            audit_log_id: The audit log entry to flag.
            reason: Reason text for the hallucination flag.
            flagged_by: User ID of the person flagging.

        Returns:
            Updated audit log entry.

        Raises:
            ValueError: If audit log not found.
        """
        result = await self._session.execute(
            select(LLMAuditLog).where(LLMAuditLog.id == audit_log_id)
        )
        log = result.scalar_one_or_none()
        if log is None:
            raise ValueError(f"LLM audit log {audit_log_id} not found")

        if log.hallucination_flagged:
            raise ValueError(
                f"LLM audit log {audit_log_id} is already flagged as a hallucination"
            )

        log.hallucination_flagged = True
        log.hallucination_reason = reason
        log.flagged_at = datetime.now(UTC)
        log.flagged_by_user_id = flagged_by
        await self._session.flush()
        await self._session.commit()

        return self._serialize(log)

    async def get_stats(
        self,
        *,
        engagement_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute acceptance/modification/rejection rates from audit entries.

        Args:
            engagement_id: The engagement to compute stats for.
            from_date: Start of date range.
            to_date: End of date range.

        Returns:
            Stats dict with counts and rates.
        """
        # Get scenario IDs for this engagement
        scenario_ids_query = select(SimulationScenario.id).where(
            SimulationScenario.engagement_id == engagement_id
        )

        # Get audit log IDs in range
        audit_base = select(LLMAuditLog.id).where(
            LLMAuditLog.scenario_id.in_(scenario_ids_query)
        )
        if from_date:
            audit_base = audit_base.where(LLMAuditLog.created_at >= from_date)
        if to_date:
            audit_base = audit_base.where(LLMAuditLog.created_at <= to_date)

        # Count total audit entries
        count_q = select(func.count()).select_from(audit_base.subquery())
        count_result = await self._session.execute(count_q)
        total_entries = count_result.scalar() or 0

        # Count suggestions by disposition
        suggestion_base = (
            select(
                AlternativeSuggestion.disposition,
                func.count().label("cnt"),
            )
            .where(AlternativeSuggestion.scenario_id.in_(scenario_ids_query))
            .group_by(AlternativeSuggestion.disposition)
        )
        sugg_result = await self._session.execute(suggestion_base)
        disposition_counts: dict[str, int] = {}
        for row in sugg_result:
            disp = row[0].value if hasattr(row[0], "value") else str(row[0]) if row[0] else "pending"
            disposition_counts[disp] = row[1]

        total_suggestions = sum(disposition_counts.values())
        accepted = disposition_counts.get(SuggestionDisposition.ACCEPTED.value, 0)
        modified = disposition_counts.get(SuggestionDisposition.MODIFIED.value, 0)
        rejected = disposition_counts.get(SuggestionDisposition.REJECTED.value, 0)

        # Hallucination count (with same date filter)
        halluc_base = (
            select(LLMAuditLog.id)
            .where(
                LLMAuditLog.scenario_id.in_(scenario_ids_query),
                LLMAuditLog.hallucination_flagged.is_(True),
            )
        )
        if from_date:
            halluc_base = halluc_base.where(LLMAuditLog.created_at >= from_date)
        if to_date:
            halluc_base = halluc_base.where(LLMAuditLog.created_at <= to_date)
        halluc_q = select(func.count()).select_from(halluc_base.subquery())
        halluc_result = await self._session.execute(halluc_q)
        hallucination_count = halluc_result.scalar() or 0

        return {
            "total_entries": total_entries,
            "total_suggestions": total_suggestions,
            "accepted_count": accepted,
            "modified_count": modified,
            "rejected_count": rejected,
            "hallucination_flagged_count": hallucination_count,
            "acceptance_rate": round(accepted / total_suggestions * 100, 1) if total_suggestions else 0.0,
            "modification_rate": round(modified / total_suggestions * 100, 1) if total_suggestions else 0.0,
            "rejection_rate": round(rejected / total_suggestions * 100, 1) if total_suggestions else 0.0,
        }

    @staticmethod
    def _serialize(log: LLMAuditLog) -> dict[str, Any]:
        """Serialize an audit log entry."""
        return {
            "id": str(log.id),
            "scenario_id": str(log.scenario_id),
            "user_id": str(log.user_id) if log.user_id else None,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "model_name": log.model_name,
            "evidence_ids": log.evidence_ids,
            "error_message": log.error_message,
            "hallucination_flagged": log.hallucination_flagged,
            "hallucination_reason": log.hallucination_reason,
            "flagged_at": log.flagged_at.isoformat() if log.flagged_at else None,
            "flagged_by_user_id": str(log.flagged_by_user_id) if log.flagged_by_user_id else None,
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
