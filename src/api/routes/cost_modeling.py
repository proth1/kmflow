"""Cost-per-role and volume forecast modeling routes (Story #359).

Engagement-scoped CRUD for role rates and volume forecasts,
plus cost computation endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.financial.cost_modeler import (
    compute_fte_savings,
    compute_quarterly_projections,
    compute_staffing_cost,
    compute_volume_cost,
)
from src.core.models import RoleRateAssumption, User, VolumeForecast
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cost-modeling"])


# ── Schemas ────────────────────────────────────────────────────────────


class RoleRateCreate(BaseModel):
    """Create a role rate assumption."""

    role_name: str = Field(..., min_length=1, max_length=256)
    hourly_rate: float = Field(..., gt=0)
    annual_rate: float | None = None
    rate_variance_pct: float = Field(0.0, ge=0.0, le=100.0)


class VolumeForecastCreate(BaseModel):
    """Create a volume forecast."""

    name: str = Field(..., min_length=1, max_length=256)
    baseline_volume: int = Field(..., gt=0)
    variance_pct: float = Field(0.0, ge=0.0, le=100.0)
    seasonal_factors: dict[str, float] | None = None


class StaffingCostRequest(BaseModel):
    """Request payload for staffing cost computation."""

    task_assignments: list[dict[str, Any]]


class VolumeCostRequest(BaseModel):
    """Request payload for volume-based cost computation."""

    forecast_id: UUID
    per_transaction_cost: float = Field(..., gt=0)


class QuarterlyProjectionRequest(BaseModel):
    """Request payload for quarterly projection computation."""

    forecast_id: UUID
    per_transaction_cost: float = Field(..., gt=0)


class FteSavingsRequest(BaseModel):
    """Request payload for FTE savings computation."""

    as_is_tasks: list[dict[str, Any]]
    to_be_tasks: list[dict[str, Any]]


# ── Role Rate Routes ──────────────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/role-rates",
    status_code=status.HTTP_201_CREATED,
)
async def create_role_rate(
    engagement_id: UUID,
    payload: RoleRateCreate,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Create a role rate assumption for an engagement."""
    rate = RoleRateAssumption(
        engagement_id=engagement_id,
        role_name=payload.role_name,
        hourly_rate=payload.hourly_rate,
        annual_rate=payload.annual_rate,
        rate_variance_pct=payload.rate_variance_pct,
    )
    session.add(rate)
    await session.commit()
    await session.refresh(rate)
    return _rate_to_dict(rate)


@router.get("/engagements/{engagement_id}/role-rates")
async def list_role_rates(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List role rate assumptions for an engagement."""
    result = await session.execute(
        select(RoleRateAssumption)
        .where(RoleRateAssumption.engagement_id == engagement_id)
        .order_by(RoleRateAssumption.role_name)
    )
    items = list(result.scalars().all())
    return {"items": [_rate_to_dict(r) for r in items], "total": len(items)}


# ── Volume Forecast Routes ───────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/volume-forecasts",
    status_code=status.HTTP_201_CREATED,
)
async def create_volume_forecast(
    engagement_id: UUID,
    payload: VolumeForecastCreate,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Create a volume forecast for an engagement."""
    forecast = VolumeForecast(
        engagement_id=engagement_id,
        name=payload.name,
        baseline_volume=payload.baseline_volume,
        variance_pct=payload.variance_pct,
        seasonal_factors=payload.seasonal_factors,
    )
    session.add(forecast)
    await session.commit()
    await session.refresh(forecast)
    return _forecast_to_dict(forecast)


@router.get("/engagements/{engagement_id}/volume-forecasts")
async def list_volume_forecasts(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List volume forecasts for an engagement."""
    result = await session.execute(
        select(VolumeForecast)
        .where(VolumeForecast.engagement_id == engagement_id)
        .order_by(VolumeForecast.name)
    )
    items = list(result.scalars().all())
    return {"items": [_forecast_to_dict(f) for f in items], "total": len(items)}


# ── Cost Computation Routes ──────────────────────────────────────────


@router.post("/engagements/{engagement_id}/cost-modeling/staffing")
async def compute_staffing(
    engagement_id: UUID,
    payload: StaffingCostRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute staffing cost range from role rates and task assignments."""
    result = await session.execute(
        select(RoleRateAssumption).where(RoleRateAssumption.engagement_id == engagement_id)
    )
    rates = list(result.scalars().all())
    if not rates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No role rates defined")

    role_rates = [
        {"role_name": r.role_name, "hourly_rate": r.hourly_rate, "rate_variance_pct": r.rate_variance_pct}
        for r in rates
    ]
    return compute_staffing_cost(role_rates, payload.task_assignments)


@router.post("/engagements/{engagement_id}/cost-modeling/volume")
async def compute_volume(
    engagement_id: UUID,
    payload: VolumeCostRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute processing cost range from volume forecast variance."""
    forecast = await _get_forecast(session, payload.forecast_id, engagement_id)
    return compute_volume_cost(
        forecast.baseline_volume, forecast.variance_pct, payload.per_transaction_cost
    )


@router.post("/engagements/{engagement_id}/cost-modeling/quarterly")
async def compute_quarterly(
    engagement_id: UUID,
    payload: QuarterlyProjectionRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute quarterly cost projections with seasonal adjustments."""
    forecast = await _get_forecast(session, payload.forecast_id, engagement_id)
    if not forecast.seasonal_factors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Forecast has no seasonal factors defined",
        )
    return compute_quarterly_projections(
        forecast.baseline_volume, forecast.variance_pct, forecast.seasonal_factors, payload.per_transaction_cost
    )


@router.post("/engagements/{engagement_id}/cost-modeling/fte-savings")
async def compute_fte(
    engagement_id: UUID,
    payload: FteSavingsRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Compute FTE savings delta between as-is and to-be task sets."""
    result = await session.execute(
        select(RoleRateAssumption).where(RoleRateAssumption.engagement_id == engagement_id)
    )
    rates = list(result.scalars().all())
    if not rates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No role rates defined")

    role_rates = [
        {"role_name": r.role_name, "hourly_rate": r.hourly_rate, "rate_variance_pct": r.rate_variance_pct}
        for r in rates
    ]
    return compute_fte_savings(role_rates, payload.as_is_tasks, payload.to_be_tasks)


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_forecast(session: AsyncSession, forecast_id: UUID, engagement_id: UUID) -> VolumeForecast:
    """Load a volume forecast scoped to engagement, or 404."""
    result = await session.execute(
        select(VolumeForecast)
        .where(VolumeForecast.id == forecast_id)
        .where(VolumeForecast.engagement_id == engagement_id)
    )
    forecast = result.scalar_one_or_none()
    if not forecast:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volume forecast not found")
    return forecast


def _rate_to_dict(r: RoleRateAssumption) -> dict[str, Any]:
    """Serialize a RoleRateAssumption."""
    return {
        "id": str(r.id),
        "engagement_id": str(r.engagement_id),
        "role_name": r.role_name,
        "hourly_rate": r.hourly_rate,
        "annual_rate": r.annual_rate,
        "rate_variance_pct": r.rate_variance_pct,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _forecast_to_dict(f: VolumeForecast) -> dict[str, Any]:
    """Serialize a VolumeForecast."""
    return {
        "id": str(f.id),
        "engagement_id": str(f.engagement_id),
        "name": f.name,
        "baseline_volume": f.baseline_volume,
        "variance_pct": f.variance_pct,
        "seasonal_factors": f.seasonal_factors,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
