"""Financial assumption management service (Story #354).

CRUD operations with version history tracking for financial assumptions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import FinancialAssumption, FinancialAssumptionType, FinancialAssumptionVersion


async def create_assumption(
    session: AsyncSession,
    engagement_id: UUID,
    data: dict[str, Any],
) -> FinancialAssumption:
    """Create a financial assumption with source/confidence validation.

    Either source_evidence_id or confidence_explanation must be provided.

    Raises:
        ValueError: If neither source_evidence_id nor confidence_explanation provided.
    """
    source_evidence_id = data.get("source_evidence_id")
    confidence_explanation = data.get("confidence_explanation")

    if not source_evidence_id and not confidence_explanation:
        raise ValueError("source_evidence_id or confidence_explanation is required")

    assumption = FinancialAssumption(
        engagement_id=engagement_id,
        assumption_type=data["assumption_type"],
        name=data["name"],
        value=data["value"],
        unit=data["unit"],
        confidence=data["confidence"],
        source_evidence_id=source_evidence_id,
        confidence_explanation=confidence_explanation,
        confidence_range=data.get("confidence_range"),
        notes=data.get("notes"),
    )
    session.add(assumption)
    return assumption


async def list_assumptions(
    session: AsyncSession,
    engagement_id: UUID,
    assumption_type: FinancialAssumptionType | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List assumptions for an engagement with optional type filter."""
    query = select(FinancialAssumption).where(FinancialAssumption.engagement_id == engagement_id)

    if assumption_type:
        query = query.where(FinancialAssumption.assumption_type == assumption_type)

    count_query = select(func.count()).select_from(query.with_only_columns(FinancialAssumption.id).subquery())
    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    query = query.offset(offset).limit(limit).order_by(FinancialAssumption.created_at.desc())
    result = await session.execute(query)
    items = list(result.scalars().all())

    return {"items": items, "total": total}


async def update_assumption(
    session: AsyncSession,
    assumption_id: UUID,
    data: dict[str, Any],
    user_id: UUID,
    engagement_id: UUID | None = None,
) -> FinancialAssumption:
    """Update a financial assumption and create version history entry.

    Captures the prior state in FinancialAssumptionVersion before applying changes.

    Raises:
        ValueError: If assumption not found or does not belong to engagement.
    """
    query = select(FinancialAssumption).where(FinancialAssumption.id == assumption_id)
    if engagement_id is not None:
        query = query.where(FinancialAssumption.engagement_id == engagement_id)
    result = await session.execute(query)
    assumption = result.scalar_one_or_none()
    if not assumption:
        raise ValueError("Assumption not found")

    # Snapshot current state before update
    version = FinancialAssumptionVersion(
        assumption_id=assumption.id,
        value=assumption.value,
        unit=assumption.unit,
        confidence=assumption.confidence,
        confidence_range=assumption.confidence_range,
        source_evidence_id=assumption.source_evidence_id,
        confidence_explanation=assumption.confidence_explanation,
        notes=assumption.notes,
        changed_by=user_id,
    )
    session.add(version)

    # Apply updates
    for field in (
        "value",
        "unit",
        "confidence",
        "confidence_range",
        "source_evidence_id",
        "confidence_explanation",
        "notes",
        "name",
    ):
        if field in data:
            setattr(assumption, field, data[field])

    assumption.updated_at = datetime.now(UTC)
    return assumption


async def get_assumption_history(
    session: AsyncSession,
    assumption_id: UUID,
    engagement_id: UUID | None = None,
) -> list[FinancialAssumptionVersion]:
    """Get version history for an assumption, most recent first.

    Raises:
        ValueError: If assumption not found or does not belong to engagement.
    """
    # Verify assumption exists and belongs to engagement
    verify_query = select(FinancialAssumption.id).where(FinancialAssumption.id == assumption_id)
    if engagement_id is not None:
        verify_query = verify_query.where(FinancialAssumption.engagement_id == engagement_id)
    verify_result = await session.execute(verify_query)
    if not verify_result.scalar_one_or_none():
        raise ValueError("Assumption not found")

    result = await session.execute(
        select(FinancialAssumptionVersion)
        .where(FinancialAssumptionVersion.assumption_id == assumption_id)
        .order_by(FinancialAssumptionVersion.changed_at.desc())
    )
    return list(result.scalars().all())
