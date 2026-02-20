"""Monitoring job and baseline management routes.

Provides API for configuring monitoring jobs, creating baselines,
managing job lifecycle, and querying deviations and alerts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import (
    AlertSeverity,
    AlertStatus,
    AuditAction,
    AuditLog,
    DeviationCategory,
    MonitoringAlert,
    MonitoringJob,
    MonitoringSourceType,
    MonitoringStatus,
    ProcessBaseline,
    ProcessDeviation,
    User,
)
from src.core.permissions import require_engagement_access, require_permission
from src.monitoring.baseline import compute_process_hash, create_baseline_snapshot
from src.monitoring.config import validate_cron_expression, validate_monitoring_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


# -- Schemas ------------------------------------------------------------------


class MonitoringJobCreate(BaseModel):
    engagement_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    source_type: MonitoringSourceType
    connection_id: UUID | None = None
    baseline_id: UUID | None = None
    schedule_cron: str = "0 0 * * *"
    config: dict[str, Any] | None = None


class MonitoringJobUpdate(BaseModel):
    name: str | None = None
    schedule_cron: str | None = None
    config: dict[str, Any] | None = None
    status: MonitoringStatus | None = None


class MonitoringJobResponse(BaseModel):
    id: str
    engagement_id: str
    name: str
    source_type: str
    status: str
    connection_id: str | None = None
    baseline_id: str | None = None
    schedule_cron: str
    config: dict[str, Any] | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None
    error_message: str | None = None


class MonitoringJobList(BaseModel):
    items: list[MonitoringJobResponse]
    total: int


class BaselineCreate(BaseModel):
    engagement_id: UUID
    process_model_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    snapshot_data: dict[str, Any] | None = None


class BaselineResponse(BaseModel):
    id: str
    engagement_id: str
    process_model_id: str | None = None
    name: str
    element_count: int
    process_hash: str | None = None
    is_active: bool
    created_at: str


class BaselineList(BaseModel):
    items: list[BaselineResponse]
    total: int


class DeviationResponse(BaseModel):
    id: str
    engagement_id: str
    monitoring_job_id: str
    category: str
    description: str
    affected_element: str | None = None
    magnitude: float
    details: dict[str, Any] | None = None
    detected_at: str


class DeviationList(BaseModel):
    items: list[DeviationResponse]
    total: int


class AlertResponse(BaseModel):
    id: str
    engagement_id: str
    monitoring_job_id: str
    severity: str
    status: str
    title: str
    description: str
    deviation_ids: list[str] | None = None
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    created_at: str


class AlertList(BaseModel):
    items: list[AlertResponse]
    total: int


class AlertActionRequest(BaseModel):
    action: str = Field(..., pattern="^(acknowledge|resolve|dismiss)$")
    actor: str = "system"


class MonitoringStats(BaseModel):
    active_jobs: int
    total_deviations: int
    open_alerts: int
    critical_alerts: int


# -- Helper converters --------------------------------------------------------


def _job_to_response(job: MonitoringJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "engagement_id": str(job.engagement_id),
        "name": job.name,
        "source_type": job.source_type.value if isinstance(job.source_type, MonitoringSourceType) else job.source_type,
        "status": job.status.value if isinstance(job.status, MonitoringStatus) else job.status,
        "connection_id": str(job.connection_id) if job.connection_id else None,
        "baseline_id": str(job.baseline_id) if job.baseline_id else None,
        "schedule_cron": job.schedule_cron,
        "config": job.config_json,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "error_message": job.error_message,
    }


def _baseline_to_response(b: ProcessBaseline) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "engagement_id": str(b.engagement_id),
        "process_model_id": str(b.process_model_id) if b.process_model_id else None,
        "name": b.name,
        "element_count": b.element_count,
        "process_hash": b.process_hash,
        "is_active": b.is_active,
        "created_at": b.created_at.isoformat() if b.created_at else "",
    }


def _deviation_to_response(d: ProcessDeviation) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "engagement_id": str(d.engagement_id),
        "monitoring_job_id": str(d.monitoring_job_id),
        "category": d.category.value if isinstance(d.category, DeviationCategory) else d.category,
        "description": d.description,
        "affected_element": d.affected_element,
        "magnitude": d.magnitude,
        "details": d.details_json,
        "detected_at": d.detected_at.isoformat() if d.detected_at else "",
    }


def _alert_to_response(a: MonitoringAlert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "engagement_id": str(a.engagement_id),
        "monitoring_job_id": str(a.monitoring_job_id),
        "severity": a.severity.value if isinstance(a.severity, AlertSeverity) else a.severity,
        "status": a.status.value if isinstance(a.status, AlertStatus) else a.status,
        "title": a.title,
        "description": a.description,
        "deviation_ids": a.deviation_ids,
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else "",
    }


# -- Monitoring Job Routes ----------------------------------------------------


@router.post("/jobs", response_model=MonitoringJobResponse, status_code=status.HTTP_201_CREATED)
async def create_monitoring_job(
    payload: MonitoringJobCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:configure")),
) -> dict[str, Any]:
    """Create a new monitoring job."""
    if not validate_cron_expression(payload.schedule_cron):
        raise HTTPException(status_code=400, detail="Invalid cron expression")

    config_errors = validate_monitoring_config(payload.source_type, payload.config)
    if config_errors:
        raise HTTPException(status_code=400, detail="; ".join(config_errors))

    job = MonitoringJob(
        engagement_id=payload.engagement_id,
        name=payload.name,
        source_type=payload.source_type,
        status=MonitoringStatus.CONFIGURING,
        connection_id=payload.connection_id,
        baseline_id=payload.baseline_id,
        schedule_cron=payload.schedule_cron,
        config_json=payload.config,
    )
    session.add(job)

    audit = AuditLog(
        engagement_id=payload.engagement_id,
        action=AuditAction.MONITORING_CONFIGURED,
        actor=str(user.id),
        details=f"Created monitoring job: {payload.name}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(job)
    return _job_to_response(job)


@router.get("/jobs", response_model=MonitoringJobList)
async def list_monitoring_jobs(
    engagement_id: UUID | None = None,
    status_filter: MonitoringStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """List monitoring jobs with optional filters."""
    query = select(MonitoringJob)
    count_query = select(func.count(MonitoringJob.id))
    if engagement_id:
        query = query.where(MonitoringJob.engagement_id == engagement_id)
        count_query = count_query.where(MonitoringJob.engagement_id == engagement_id)
    if status_filter:
        query = query.where(MonitoringJob.status == status_filter)
        count_query = count_query.where(MonitoringJob.status == status_filter)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [_job_to_response(j) for j in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/jobs/{job_id}", response_model=MonitoringJobResponse)
async def get_monitoring_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """Get a monitoring job by ID."""
    result = await session.execute(select(MonitoringJob).where(MonitoringJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Monitoring job {job_id} not found")
    return _job_to_response(job)


@router.patch("/jobs/{job_id}", response_model=MonitoringJobResponse)
async def update_monitoring_job(
    job_id: UUID,
    payload: MonitoringJobUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:manage")),
) -> dict[str, Any]:
    """Update a monitoring job."""
    result = await session.execute(select(MonitoringJob).where(MonitoringJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Monitoring job {job_id} not found")

    if payload.name is not None:
        job.name = payload.name
    if payload.schedule_cron is not None:
        if not validate_cron_expression(payload.schedule_cron):
            raise HTTPException(status_code=400, detail="Invalid cron expression")
        job.schedule_cron = payload.schedule_cron
    if payload.config is not None:
        job.config_json = payload.config
    if payload.status is not None:
        job.status = payload.status

    await session.commit()
    await session.refresh(job)
    return _job_to_response(job)


@router.post("/jobs/{job_id}/activate", response_model=MonitoringJobResponse)
async def activate_monitoring_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:manage")),
) -> dict[str, Any]:
    """Activate a monitoring job."""
    result = await session.execute(select(MonitoringJob).where(MonitoringJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Monitoring job {job_id} not found")

    job.status = MonitoringStatus.ACTIVE

    audit = AuditLog(
        engagement_id=job.engagement_id,
        action=AuditAction.MONITORING_ACTIVATED,
        actor=str(user.id),
        details=f"Activated monitoring job: {job.name}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(job)
    return _job_to_response(job)


@router.post("/jobs/{job_id}/pause", response_model=MonitoringJobResponse)
async def pause_monitoring_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:manage")),
) -> dict[str, Any]:
    """Pause a monitoring job."""
    result = await session.execute(select(MonitoringJob).where(MonitoringJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Monitoring job {job_id} not found")

    job.status = MonitoringStatus.PAUSED
    await session.commit()
    await session.refresh(job)
    return _job_to_response(job)


@router.post("/jobs/{job_id}/stop", response_model=MonitoringJobResponse)
async def stop_monitoring_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:manage")),
) -> dict[str, Any]:
    """Stop a monitoring job."""
    result = await session.execute(select(MonitoringJob).where(MonitoringJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Monitoring job {job_id} not found")

    job.status = MonitoringStatus.STOPPED

    audit = AuditLog(
        engagement_id=job.engagement_id,
        action=AuditAction.MONITORING_STOPPED,
        actor=str(user.id),
        details=f"Stopped monitoring job: {job.name}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(job)
    return _job_to_response(job)


# -- Baseline Routes ----------------------------------------------------------


@router.post("/baselines", response_model=BaselineResponse, status_code=status.HTTP_201_CREATED)
async def create_baseline(
    payload: BaselineCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:configure")),
) -> dict[str, Any]:
    """Create a process baseline snapshot."""
    snapshot = payload.snapshot_data or {}
    if snapshot:
        snapshot = create_baseline_snapshot(snapshot)

    process_hash = compute_process_hash(snapshot) if snapshot else None
    element_count = len(snapshot.get("elements", [])) if snapshot else 0

    baseline = ProcessBaseline(
        engagement_id=payload.engagement_id,
        process_model_id=payload.process_model_id,
        name=payload.name,
        snapshot_data=snapshot,
        element_count=element_count,
        process_hash=process_hash,
        is_active=True,
    )
    session.add(baseline)

    audit = AuditLog(
        engagement_id=payload.engagement_id,
        action=AuditAction.BASELINE_CREATED,
        actor=str(user.id),
        details=f"Created baseline: {payload.name} ({element_count} elements)",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(baseline)
    return _baseline_to_response(baseline)


@router.get("/baselines", response_model=BaselineList)
async def list_baselines(
    engagement_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """List process baselines."""
    query = select(ProcessBaseline)
    count_query = select(func.count(ProcessBaseline.id))
    if engagement_id:
        query = query.where(ProcessBaseline.engagement_id == engagement_id)
        count_query = count_query.where(ProcessBaseline.engagement_id == engagement_id)
    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    items = [_baseline_to_response(b) for b in result.scalars().all()]
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/baselines/{baseline_id}", response_model=BaselineResponse)
async def get_baseline(
    baseline_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """Get a baseline by ID."""
    result = await session.execute(select(ProcessBaseline).where(ProcessBaseline.id == baseline_id))
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline {baseline_id} not found")
    return _baseline_to_response(baseline)


# -- Deviation Routes ---------------------------------------------------------


@router.get("/deviations", response_model=DeviationList)
async def list_deviations(
    engagement_id: UUID | None = None,
    job_id: UUID | None = None,
    category: DeviationCategory | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """List process deviations with filters."""
    query = select(ProcessDeviation)
    if engagement_id:
        query = query.where(ProcessDeviation.engagement_id == engagement_id)
    if job_id:
        query = query.where(ProcessDeviation.monitoring_job_id == job_id)
    if category:
        query = query.where(ProcessDeviation.category == category)
    query = query.order_by(ProcessDeviation.detected_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    items = [_deviation_to_response(d) for d in result.scalars().all()]

    count_query = select(func.count(ProcessDeviation.id))
    if engagement_id:
        count_query = count_query.where(ProcessDeviation.engagement_id == engagement_id)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


@router.get("/deviations/{deviation_id}", response_model=DeviationResponse)
async def get_deviation(
    deviation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """Get a deviation by ID."""
    result = await session.execute(select(ProcessDeviation).where(ProcessDeviation.id == deviation_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail=f"Deviation {deviation_id} not found")
    return _deviation_to_response(dev)


# -- Alert Routes -------------------------------------------------------------


@router.get("/alerts", response_model=AlertList)
async def list_alerts(
    engagement_id: UUID | None = None,
    status_filter: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """List monitoring alerts with filters."""
    query = select(MonitoringAlert)
    if engagement_id:
        query = query.where(MonitoringAlert.engagement_id == engagement_id)
    if status_filter:
        query = query.where(MonitoringAlert.status == status_filter)
    if severity:
        query = query.where(MonitoringAlert.severity == severity)
    query = query.order_by(MonitoringAlert.created_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    items = [_alert_to_response(a) for a in result.scalars().all()]

    count_query = select(func.count(MonitoringAlert.id))
    if engagement_id:
        count_query = count_query.where(MonitoringAlert.engagement_id == engagement_id)
    if status_filter:
        count_query = count_query.where(MonitoringAlert.status == status_filter)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
) -> dict[str, Any]:
    """Get an alert by ID."""
    result = await session.execute(select(MonitoringAlert).where(MonitoringAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return _alert_to_response(alert)


@router.post("/alerts/{alert_id}/action", response_model=AlertResponse)
async def alert_action(
    alert_id: UUID,
    payload: AlertActionRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:manage")),
) -> dict[str, Any]:
    """Perform an action on an alert (acknowledge, resolve, dismiss)."""
    result = await session.execute(select(MonitoringAlert).where(MonitoringAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    now = datetime.now(UTC)
    if payload.action == "acknowledge":
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = payload.actor
        alert.acknowledged_at = now
    elif payload.action == "resolve":
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = now
    elif payload.action == "dismiss":
        alert.status = AlertStatus.DISMISSED

    audit_action = {
        "acknowledge": AuditAction.ALERT_ACKNOWLEDGED,
        "resolve": AuditAction.ALERT_RESOLVED,
        "dismiss": AuditAction.ALERT_RESOLVED,
    }.get(payload.action, AuditAction.ALERT_ACKNOWLEDGED)
    audit = AuditLog(
        engagement_id=alert.engagement_id,
        action=audit_action,
        actor=payload.actor,
        details=f"Alert {alert_id} action: {payload.action}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(alert)
    return _alert_to_response(alert)


# -- Stats Route --------------------------------------------------------------


@router.get("/stats/{engagement_id}", response_model=MonitoringStats)
async def get_monitoring_stats(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("monitoring:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get monitoring statistics for an engagement."""
    active_q = await session.execute(
        select(func.count(MonitoringJob.id)).where(
            MonitoringJob.engagement_id == engagement_id,
            MonitoringJob.status == MonitoringStatus.ACTIVE,
        )
    )
    active_jobs = active_q.scalar() or 0

    dev_q = await session.execute(
        select(func.count(ProcessDeviation.id)).where(
            ProcessDeviation.engagement_id == engagement_id,
        )
    )
    total_deviations = dev_q.scalar() or 0

    open_q = await session.execute(
        select(func.count(MonitoringAlert.id)).where(
            MonitoringAlert.engagement_id == engagement_id,
            MonitoringAlert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
        )
    )
    open_alerts = open_q.scalar() or 0

    crit_q = await session.execute(
        select(func.count(MonitoringAlert.id)).where(
            MonitoringAlert.engagement_id == engagement_id,
            MonitoringAlert.severity == AlertSeverity.CRITICAL,
            MonitoringAlert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
        )
    )
    critical_alerts = crit_q.scalar() or 0

    return {
        "active_jobs": active_jobs,
        "total_deviations": total_deviations,
        "open_alerts": open_alerts,
        "critical_alerts": critical_alerts,
    }
