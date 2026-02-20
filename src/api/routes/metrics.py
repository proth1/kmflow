"""Success metrics CRUD and aggregate routes.

Provides endpoints for managing success metric definitions,
recording metric readings, and retrieving aggregate summaries.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    AuditAction,
    AuditLog,
    MetricCategory,
    MetricReading,
    SuccessMetric,
    User,
)
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# -- Schemas ------------------------------------------------------------------


class SuccessMetricCreate(BaseModel):
    """Schema for creating a success metric definition."""

    name: str = Field(..., min_length=1, max_length=255)
    unit: str = Field(..., min_length=1, max_length=100)
    target_value: float
    category: MetricCategory
    description: str | None = None


class SuccessMetricResponse(BaseModel):
    """Schema for success metric responses."""

    model_config = {"from_attributes": True}

    id: UUID
    name: str
    unit: str
    target_value: float
    category: MetricCategory
    description: str | None
    created_at: Any


class SuccessMetricList(BaseModel):
    """Schema for listing success metrics."""

    items: list[SuccessMetricResponse]
    total: int


class MetricReadingCreate(BaseModel):
    """Schema for recording a metric reading."""

    metric_id: UUID
    engagement_id: UUID
    value: float
    notes: str | None = None


class MetricReadingResponse(BaseModel):
    """Schema for metric reading responses."""

    model_config = {"from_attributes": True}

    id: UUID
    metric_id: UUID
    engagement_id: UUID
    value: float
    recorded_at: Any
    notes: str | None


class MetricReadingList(BaseModel):
    """Schema for listing metric readings."""

    items: list[MetricReadingResponse]
    total: int


class MetricAggregateSummary(BaseModel):
    """Aggregate summary for a metric across an engagement."""

    metric_id: str
    metric_name: str
    unit: str
    target_value: float
    category: str
    reading_count: int
    latest_value: float | None
    avg_value: float | None
    min_value: float | None
    max_value: float | None
    on_target: bool


# -- Metric Definition Routes -------------------------------------------------


@router.post("/definitions", response_model=SuccessMetricResponse, status_code=status.HTTP_201_CREATED)
async def create_metric(
    payload: SuccessMetricCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> SuccessMetric:
    """Create a success metric definition."""
    metric = SuccessMetric(
        name=payload.name,
        unit=payload.unit,
        target_value=payload.target_value,
        category=payload.category,
        description=payload.description,
    )
    session.add(metric)

    audit = AuditLog(
        action=AuditAction.METRIC_DEFINED,
        actor=str(user.id),
        details=f"Defined metric: {payload.name} (target={payload.target_value} {payload.unit})",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(metric)
    return metric


@router.get("/definitions", response_model=SuccessMetricList)
async def list_metrics(
    category: MetricCategory | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List success metric definitions with optional category filter."""
    query = select(SuccessMetric)
    count_query = select(func.count()).select_from(SuccessMetric)

    if category is not None:
        query = query.where(SuccessMetric.category == category)
        count_query = count_query.where(SuccessMetric.category == category)

    query = query.order_by(SuccessMetric.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/definitions/{metric_id}", response_model=SuccessMetricResponse)
async def get_metric(
    metric_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> SuccessMetric:
    """Get a single metric definition by ID."""
    result = await session.execute(select(SuccessMetric).where(SuccessMetric.id == metric_id))
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Metric {metric_id} not found")
    return metric


# -- Metric Reading Routes ----------------------------------------------------


@router.post("/readings", response_model=MetricReadingResponse, status_code=status.HTTP_201_CREATED)
async def record_reading(
    payload: MetricReadingCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> MetricReading:
    """Record a new metric reading."""
    # Verify metric exists
    metric_result = await session.execute(select(SuccessMetric).where(SuccessMetric.id == payload.metric_id))
    if not metric_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Metric {payload.metric_id} not found")

    reading = MetricReading(
        metric_id=payload.metric_id,
        engagement_id=payload.engagement_id,
        value=payload.value,
        notes=payload.notes,
    )
    session.add(reading)

    audit = AuditLog(
        engagement_id=payload.engagement_id,
        action=AuditAction.METRIC_READING_RECORDED,
        actor=str(user.id),
        details=f"Recorded reading: metric={payload.metric_id}, value={payload.value}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(reading)
    return reading


@router.get("/readings", response_model=MetricReadingList)
async def list_readings(
    engagement_id: UUID,
    metric_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List metric readings for an engagement."""
    query = select(MetricReading).where(MetricReading.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(MetricReading).where(MetricReading.engagement_id == engagement_id)

    if metric_id is not None:
        query = query.where(MetricReading.metric_id == metric_id)
        count_query = count_query.where(MetricReading.metric_id == metric_id)

    query = query.order_by(MetricReading.recorded_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


# -- Aggregate Summary --------------------------------------------------------


@router.get("/summary/{engagement_id}")
async def get_metric_summary(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get aggregate metric summary for an engagement.

    Returns each metric definition with its latest, average, min, max
    values and whether the metric is on target.
    """
    # Get all metric definitions
    metrics_result = await session.execute(select(SuccessMetric).order_by(SuccessMetric.name))
    metrics = list(metrics_result.scalars().all())

    # Query 1: aggregates for all metrics in a single GROUP BY query
    agg_query = (
        select(
            MetricReading.metric_id,
            func.count(MetricReading.id).label("count"),
            func.avg(MetricReading.value).label("avg"),
            func.min(MetricReading.value).label("min"),
            func.max(MetricReading.value).label("max"),
        )
        .where(MetricReading.engagement_id == engagement_id)
        .group_by(MetricReading.metric_id)
    )
    agg_result = await session.execute(agg_query)
    agg_by_metric: dict[Any, Any] = {row.metric_id: row for row in agg_result}

    # Query 2: latest reading per metric using a window function subquery
    latest_subq = (
        select(
            MetricReading.metric_id,
            MetricReading.value,
            func.row_number()
            .over(
                partition_by=MetricReading.metric_id,
                order_by=MetricReading.recorded_at.desc(),
            )
            .label("rn"),
        )
        .where(MetricReading.engagement_id == engagement_id)
        .subquery()
    )
    latest_query = select(latest_subq.c.metric_id, latest_subq.c.value).where(latest_subq.c.rn == 1)
    latest_result = await session.execute(latest_query)
    latest_by_metric: dict[Any, float] = {row.metric_id: row.value for row in latest_result}

    summaries = []
    for metric in metrics:
        row = agg_by_metric.get(metric.id)
        latest = latest_by_metric.get(metric.id)

        on_target = latest is not None and latest >= metric.target_value

        summaries.append(
            {
                "metric_id": str(metric.id),
                "metric_name": metric.name,
                "unit": metric.unit,
                "target_value": metric.target_value,
                "category": str(metric.category),
                "reading_count": row.count if row else 0,
                "latest_value": float(latest) if latest is not None else None,
                "avg_value": round(float(row.avg), 3) if row and row.avg is not None else None,
                "min_value": float(row.min) if row and row.min is not None else None,
                "max_value": float(row.max) if row and row.max is not None else None,
                "on_target": on_target,
            }
        )

    return {
        "engagement_id": str(engagement_id),
        "metrics": summaries,
        "total": len(summaries),
        "on_target_count": sum(1 for s in summaries if s["on_target"]),
    }


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_metrics(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Seed the database with 15 standard success metric definitions."""
    from src.data.seed_metrics import get_metric_seeds

    seeds = get_metric_seeds()
    count = 0
    for seed_data in seeds:
        existing = await session.execute(select(SuccessMetric).where(SuccessMetric.name == seed_data["name"]))
        if existing.scalar_one_or_none() is None:
            metric = SuccessMetric(**seed_data)
            session.add(metric)
            count += 1

    if count > 0:
        audit = AuditLog(
            action=AuditAction.METRICS_SEEDED,
            actor=str(user.id),
            details=f"Seeded {count} metric definitions",
        )
        session.add(audit)

    await session.commit()
    return {"metrics_seeded": count}
