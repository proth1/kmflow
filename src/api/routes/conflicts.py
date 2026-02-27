"""Conflict resolution workflow routes.

Provides the SME review queue, resolution, escalation, and disagreement
report API for ConflictObjects detected by the consistency engine.

Implements Story #388: Disagreement Resolution Workflow.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas.conflict import (
    ConflictAssignRequest,
    ConflictEscalateRequest,
    ConflictListResponse,
    ConflictObjectRead,
    ConflictResolveRequest,
)
from src.core.models import AuditAction, AuditLog
from src.core.models.conflict import ConflictObject, MismatchType, ResolutionStatus, ResolutionType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["conflicts"])

# Default escalation threshold: 48 hours
ESCALATION_THRESHOLD_HOURS = 48


def _conflict_to_read(obj: ConflictObject) -> ConflictObjectRead:
    """Convert a ConflictObject ORM instance to a read schema."""
    return ConflictObjectRead(
        id=str(obj.id),
        engagement_id=str(obj.engagement_id),
        mismatch_type=obj.mismatch_type.value
        if isinstance(obj.mismatch_type, MismatchType)
        else str(obj.mismatch_type),
        resolution_type=obj.resolution_type.value
        if isinstance(obj.resolution_type, ResolutionType)
        else (str(obj.resolution_type) if obj.resolution_type else None),
        resolution_status=obj.resolution_status.value
        if isinstance(obj.resolution_status, ResolutionStatus)
        else str(obj.resolution_status),
        source_a_id=str(obj.source_a_id) if obj.source_a_id else None,
        source_b_id=str(obj.source_b_id) if obj.source_b_id else None,
        severity=obj.severity,
        escalation_flag=obj.escalation_flag,
        resolution_notes=obj.resolution_notes,
        conflict_detail=obj.conflict_detail,
        resolution_details=obj.resolution_details,
        resolver_id=str(obj.resolver_id) if obj.resolver_id else None,
        assigned_to=str(obj.assigned_to) if obj.assigned_to else None,
        created_at=obj.created_at.isoformat() if obj.created_at else "",
        resolved_at=obj.resolved_at.isoformat() if obj.resolved_at else None,
    )


async def _write_audit_entry(
    session: AsyncSession,
    *,
    conflict_id: uuid.UUID,
    engagement_id: uuid.UUID,
    action: AuditAction,
    actor_id: uuid.UUID,
    details: str | None = None,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
) -> None:
    """Write an immutable audit log entry for a conflict action."""
    entry = AuditLog(
        id=uuid.uuid4(),
        engagement_id=engagement_id,
        action=action,
        actor=str(actor_id),
        user_id=actor_id,
        resource_type="conflict_object",
        resource_id=conflict_id,
        details=details,
        before_value=before_value,
        after_value=after_value,
    )
    session.add(entry)


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{engagement_id}/conflicts
# ---------------------------------------------------------------------------


@router.get(
    "/engagements/{engagement_id}/conflicts",
    response_model=ConflictListResponse,
    summary="List conflicts for an engagement",
)
async def list_conflicts(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    mismatch_type: str | None = Query(None, description="Filter by mismatch type"),
    resolution_status: str | None = Query(None, description="Filter by resolution status"),
    severity_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum severity"),
    severity_max: float | None = Query(None, ge=0.0, le=1.0, description="Maximum severity"),
    escalated: bool | None = Query(None, description="Filter escalated conflicts"),
    assigned_to: str | None = Query(None, description="Filter by assigned SME user ID"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Return conflicts for an engagement with filtering and pagination.

    Supports filtering by mismatch type, resolution status, severity range,
    escalation flag, and assigned SME. Returns paginated results.
    """
    base_filter = ConflictObject.engagement_id == engagement_id
    filters = [base_filter]

    if mismatch_type:
        filters.append(ConflictObject.mismatch_type == mismatch_type)
    if resolution_status:
        filters.append(ConflictObject.resolution_status == resolution_status)
    if severity_min is not None:
        filters.append(ConflictObject.severity >= severity_min)
    if severity_max is not None:
        filters.append(ConflictObject.severity <= severity_max)
    if escalated is not None:
        filters.append(ConflictObject.escalation_flag == escalated)
    if assigned_to:
        filters.append(ConflictObject.assigned_to == uuid.UUID(assigned_to))

    # Count total
    count_q = select(func.count()).select_from(ConflictObject).where(*filters)
    total_result = await session.execute(count_q)
    total = total_result.scalar() or 0

    # Fetch page
    query = (
        select(ConflictObject)
        .where(*filters)
        .order_by(ConflictObject.severity.desc(), ConflictObject.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    conflicts = result.scalars().all()

    return {
        "items": [_conflict_to_read(c) for c in conflicts],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# PATCH /api/v1/conflicts/{conflict_id}/resolve
# ---------------------------------------------------------------------------


@router.patch(
    "/conflicts/{conflict_id}/resolve",
    response_model=ConflictObjectRead,
    summary="Resolve a conflict",
)
async def resolve_conflict(
    conflict_id: uuid.UUID,
    body: ConflictResolveRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resolve a conflict with a resolution type, notes, and resolver ID.

    Updates the conflict status to RESOLVED, persists resolver info and
    resolved_at timestamp, and writes an immutable audit log entry.
    """
    result = await session.execute(select(ConflictObject).where(ConflictObject.id == conflict_id))
    conflict = result.scalar_one_or_none()
    if not conflict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")

    if conflict.resolution_status == ResolutionStatus.RESOLVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict already resolved")

    before = {
        "resolution_status": conflict.resolution_status.value,
        "resolution_type": conflict.resolution_type.value if conflict.resolution_type else None,
        "resolver_id": str(conflict.resolver_id) if conflict.resolver_id else None,
    }

    conflict.resolution_status = ResolutionStatus.RESOLVED
    conflict.resolution_type = body.resolution_type
    conflict.resolution_notes = body.resolution_notes
    conflict.resolver_id = body.resolver_id
    conflict.resolved_at = datetime.now(UTC)

    after = {
        "resolution_status": ResolutionStatus.RESOLVED.value,
        "resolution_type": body.resolution_type.value,
        "resolver_id": str(body.resolver_id),
        "resolved_at": conflict.resolved_at.isoformat(),
    }

    await _write_audit_entry(
        session,
        conflict_id=conflict_id,
        engagement_id=conflict.engagement_id,
        action=AuditAction.CONFLICT_RESOLVED,
        actor_id=body.resolver_id,
        details=f"Resolved as {body.resolution_type.value}",
        before_value=before,
        after_value=after,
    )

    await session.commit()
    await session.refresh(conflict)
    return _conflict_to_read(conflict).model_dump()


# ---------------------------------------------------------------------------
# PATCH /api/v1/conflicts/{conflict_id}/assign
# ---------------------------------------------------------------------------


@router.patch(
    "/conflicts/{conflict_id}/assign",
    response_model=ConflictObjectRead,
    summary="Assign a conflict to an SME reviewer",
)
async def assign_conflict(
    conflict_id: uuid.UUID,
    body: ConflictAssignRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Assign a conflict to an SME reviewer for resolution."""
    result = await session.execute(select(ConflictObject).where(ConflictObject.id == conflict_id))
    conflict = result.scalar_one_or_none()
    if not conflict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")

    if conflict.resolution_status == ResolutionStatus.RESOLVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot assign a resolved conflict")

    before_assigned = str(conflict.assigned_to) if conflict.assigned_to else None
    conflict.assigned_to = body.assigned_to

    await _write_audit_entry(
        session,
        conflict_id=conflict_id,
        engagement_id=conflict.engagement_id,
        action=AuditAction.CONFLICT_ASSIGNED,
        actor_id=body.assigned_to,
        details=f"Assigned to {body.assigned_to}",
        before_value={"assigned_to": before_assigned},
        after_value={"assigned_to": str(body.assigned_to)},
    )

    await session.commit()
    await session.refresh(conflict)
    return _conflict_to_read(conflict).model_dump()


# ---------------------------------------------------------------------------
# PATCH /api/v1/conflicts/{conflict_id}/escalate
# ---------------------------------------------------------------------------


@router.patch(
    "/conflicts/{conflict_id}/escalate",
    response_model=ConflictObjectRead,
    summary="Escalate a conflict",
)
async def escalate_conflict(
    conflict_id: uuid.UUID,
    body: ConflictEscalateRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Manually escalate a conflict to the engagement lead."""
    result = await session.execute(select(ConflictObject).where(ConflictObject.id == conflict_id))
    conflict = result.scalar_one_or_none()
    if not conflict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")

    if conflict.resolution_status == ResolutionStatus.RESOLVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot escalate a resolved conflict")

    conflict.escalation_flag = True
    conflict.resolution_status = ResolutionStatus.ESCALATED
    if body.escalation_notes:
        existing = conflict.resolution_notes or ""
        conflict.resolution_notes = f"{existing}\n[ESCALATED] {body.escalation_notes}".strip()

    await _write_audit_entry(
        session,
        conflict_id=conflict_id,
        engagement_id=conflict.engagement_id,
        action=AuditAction.CONFLICT_ESCALATED,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # system
        details=body.escalation_notes or "Manually escalated",
        after_value={"escalation_flag": True, "resolution_status": ResolutionStatus.ESCALATED.value},
    )

    await session.commit()
    await session.refresh(conflict)
    return _conflict_to_read(conflict).model_dump()


# ---------------------------------------------------------------------------
# POST /api/v1/conflicts/escalation-check
# ---------------------------------------------------------------------------


@router.post(
    "/conflicts/escalation-check",
    summary="Run escalation check for overdue conflicts",
)
async def run_escalation_check(
    session: AsyncSession = Depends(get_session),
    threshold_hours: int = Query(ESCALATION_THRESHOLD_HOURS, ge=1, description="Hours before escalation"),
) -> dict[str, Any]:
    """Check for conflicts overdue beyond the threshold and escalate them.

    Marks unresolved, unescalated conflicts older than threshold_hours as
    escalated and writes audit entries for each.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=threshold_hours)

    query = select(ConflictObject).where(
        ConflictObject.resolution_status == ResolutionStatus.UNRESOLVED,
        ConflictObject.escalation_flag.is_(False),
        ConflictObject.created_at < cutoff,
    )
    result = await session.execute(query)
    overdue = result.scalars().all()

    escalated_ids: list[str] = []
    for conflict in overdue:
        conflict.escalation_flag = True
        conflict.resolution_status = ResolutionStatus.ESCALATED

        await _write_audit_entry(
            session,
            conflict_id=conflict.id,
            engagement_id=conflict.engagement_id,
            action=AuditAction.CONFLICT_ESCALATED,
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            details=f"Auto-escalated: unresolved for >{threshold_hours}h",
            after_value={"escalation_flag": True, "resolution_status": ResolutionStatus.ESCALATED.value},
        )
        escalated_ids.append(str(conflict.id))

    if overdue:
        await session.commit()

    return {
        "escalated_count": len(escalated_ids),
        "escalated_ids": escalated_ids,
        "threshold_hours": threshold_hours,
    }
