"""RACI matrix API endpoints (Story #351).

Provides:
- GET  /api/v1/raci          — Query RACI matrix cells with pagination
- POST /api/v1/raci/derive   — Trigger RACI derivation from knowledge graph
- PATCH /api/v1/raci/{cell_id}/validate — SME validates a cell
- GET  /api/v1/raci/export   — Export matrix as CSV
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.auth import get_current_user
from src.core.models import User
from src.core.models.raci import RACICell, RACIStatus
from src.core.permissions import require_engagement_access
from src.pov.raci_service import RACIDerivationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/raci", tags=["raci"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RACICellResponse(BaseModel):
    """Response schema for a single RACI cell."""

    id: UUID
    engagement_id: UUID
    activity_id: str
    activity_name: str
    role_id: str
    role_name: str
    assignment: str
    status: str
    confidence: float
    source_edge_type: str | None = None
    validator_id: UUID | None = None
    validated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedRACIResponse(BaseModel):
    """Paginated response for RACI matrix queries."""

    items: list[RACICellResponse]
    total: int
    limit: int
    offset: int
    summary: dict[str, int] | None = None


class RACIDeriveResponse(BaseModel):
    """Response from RACI derivation."""

    cells_created: int
    cells_updated: int
    activities: int
    roles: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedRACIResponse)
async def list_raci_cells(
    engagement_id: UUID = Query(..., description="Engagement to query RACI matrix for"),
    assignment: str | None = Query(None, description="Filter by assignment (R/A/C/I)"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status (proposed/validated)"),
    activity_name: str | None = Query(None, description="Filter by activity name (partial match)"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Query RACI matrix cells for an engagement with filtering and pagination."""
    base_where = RACICell.engagement_id == engagement_id
    query = select(RACICell).where(base_where)
    count_query = select(func.count()).select_from(RACICell).where(base_where)

    if assignment is not None:
        query = query.where(RACICell.assignment == assignment.upper())
        count_query = count_query.where(RACICell.assignment == assignment.upper())
    if status_filter is not None:
        query = query.where(RACICell.status == status_filter)
        count_query = count_query.where(RACICell.status == status_filter)
    if activity_name is not None:
        query = query.where(RACICell.activity_name.ilike(f"%{activity_name}%"))
        count_query = count_query.where(RACICell.activity_name.ilike(f"%{activity_name}%"))

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(RACICell.activity_name, RACICell.role_name)
    query = query.limit(limit).offset(offset)

    result = await session.execute(query)
    items = result.scalars().all()

    # Summary counts
    proposed_count = await session.execute(
        select(func.count()).select_from(RACICell).where(base_where, RACICell.status == "proposed")
    )
    validated_count = await session.execute(
        select(func.count()).select_from(RACICell).where(base_where, RACICell.status == "validated")
    )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": {
            "proposed": proposed_count.scalar() or 0,
            "validated": validated_count.scalar() or 0,
        },
    }


@router.post("/derive", response_model=RACIDeriveResponse)
async def derive_raci_matrix(
    engagement_id: UUID = Query(..., description="Engagement to derive RACI matrix for"),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Trigger RACI matrix derivation from the knowledge graph.

    Queries PERFORMED_BY, GOVERNED_BY, NOTIFIED_BY, and REVIEWS edges
    to auto-derive R/A/C/I assignments. Creates new cells or updates
    existing ones. All cells start with status='proposed'.
    """
    neo4j_driver = request.app.state.neo4j_driver
    service = RACIDerivationService(neo4j_driver)
    matrix = await service.derive_matrix(str(engagement_id))

    cells_created = 0
    cells_updated = 0

    for derivation in matrix.cells:
        # Check for existing cell
        existing = await session.execute(
            select(RACICell).where(
                RACICell.engagement_id == engagement_id,
                RACICell.activity_id == derivation.activity_id,
                RACICell.role_id == derivation.role_id,
            )
        )
        cell = existing.scalar_one_or_none()

        if cell is not None:
            # Update assignment if it changed (only if still proposed)
            if cell.status == RACIStatus.PROPOSED and cell.assignment != derivation.assignment:
                cell.assignment = derivation.assignment
                cell.confidence = derivation.confidence
                cell.source_edge_type = derivation.source_edge_type
                cells_updated += 1
        else:
            cell = RACICell(
                engagement_id=engagement_id,
                activity_id=derivation.activity_id,
                activity_name=derivation.activity_name,
                role_id=derivation.role_id,
                role_name=derivation.role_name,
                assignment=derivation.assignment,
                status=RACIStatus.PROPOSED,
                confidence=derivation.confidence,
                source_edge_type=derivation.source_edge_type,
            )
            session.add(cell)
            cells_created += 1

    await session.commit()

    return {
        "cells_created": cells_created,
        "cells_updated": cells_updated,
        "activities": len(matrix.activities),
        "roles": len(matrix.roles),
    }


@router.patch("/{cell_id}/validate", response_model=RACICellResponse)
async def validate_raci_cell(
    cell_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """SME validates a RACI cell, changing status from 'proposed' to 'validated'.

    Loads the cell first, then verifies the user has access to the cell's
    engagement. Records the validator's user ID and timestamp for audit trail.
    """
    result = await session.execute(select(RACICell).where(RACICell.id == cell_id))
    cell = result.scalar_one_or_none()

    if cell is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RACI cell not found")

    # Verify engagement access using the cell's engagement_id
    await require_engagement_access(
        engagement_id=cell.engagement_id,
        request=request,
        user=current_user,
    )

    if cell.status == RACIStatus.VALIDATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cell is already validated",
        )

    cell.status = RACIStatus.VALIDATED
    cell.validator_id = current_user.id
    cell.validated_at = func.now()
    await session.commit()
    await session.refresh(cell)

    logger.info(
        "RACI cell %s validated by user %s (activity=%s, role=%s, assignment=%s)",
        cell_id,
        current_user.id,
        cell.activity_name,
        cell.role_name,
        cell.assignment,
    )

    return cell


@router.get("/export")
async def export_raci_csv(
    engagement_id: UUID = Query(..., description="Engagement to export RACI matrix for"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_engagement_access),
) -> StreamingResponse:
    """Export the RACI matrix as a CSV file.

    Rows are activities, columns are roles. Cell values are R/A/C/I or blank.
    """
    result = await session.execute(
        select(RACICell)
        .where(RACICell.engagement_id == engagement_id)
        .order_by(RACICell.activity_name, RACICell.role_name)
    )
    cells = result.scalars().all()

    # Build the matrix structure
    activities: dict[str, dict[str, str]] = {}
    roles: set[str] = set()

    for cell in cells:
        if cell.activity_name not in activities:
            activities[cell.activity_name] = {}
        activities[cell.activity_name][cell.role_name] = cell.assignment
        roles.add(cell.role_name)

    sorted_roles = sorted(roles)

    # Write CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Activity"] + sorted_roles)

    for activity_name in sorted(activities.keys()):
        row = [activity_name]
        for role_name in sorted_roles:
            row.append(activities[activity_name].get(role_name, ""))
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=raci_matrix.csv"},
    )
