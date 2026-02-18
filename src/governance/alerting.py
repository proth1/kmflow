"""Governance SLA breach alerting integration.

Checks quality SLA compliance for all DataCatalogEntry records in an
engagement and creates MonitoringAlert records for any breaches detected.

This module bridges the governance framework (Phase D) with the monitoring
and alerting system (Phase 3) so that SLA violations surface as actionable
alerts in the dashboard.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AlertSeverity,
    AlertStatus,
    DataCatalogEntry,
    MonitoringAlert,
    MonitoringJob,
    MonitoringSourceType,
    MonitoringStatus,
)
from src.governance.quality import SLAResult, check_quality_sla

logger = logging.getLogger(__name__)

# Sentinel monitoring job name used by governance alerting so that alerts
# created here can be traced back to a purpose-built pseudo-job.
_GOVERNANCE_JOB_NAME = "__governance_sla_checker__"


async def _get_or_create_governance_job(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> MonitoringJob:
    """Get or create a sentinel MonitoringJob for governance SLA alerts.

    Because MonitoringAlert requires a non-null monitoring_job_id FK, we
    maintain one pseudo-job per engagement that acts as the "source" for
    all governance-driven alerts.

    Args:
        session: Async database session.
        engagement_id: The engagement scope.

    Returns:
        The existing or newly created MonitoringJob.
    """
    result = await session.execute(
        select(MonitoringJob).where(
            MonitoringJob.engagement_id == engagement_id,
            MonitoringJob.name == _GOVERNANCE_JOB_NAME,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    job = MonitoringJob(
        engagement_id=engagement_id,
        name=_GOVERNANCE_JOB_NAME,
        source_type=MonitoringSourceType.FILE_WATCH,
        status=MonitoringStatus.ACTIVE,
        schedule_cron="0 * * * *",  # hourly
        config_json={"purpose": "governance_sla_alerting"},
    )
    session.add(job)
    await session.flush()
    logger.info(
        "Created governance monitoring job %s for engagement %s",
        job.id,
        engagement_id,
    )
    return job


def _make_dedup_key(catalog_entry_id: uuid.UUID, violation_metric: str) -> str:
    """Build a stable deduplication key for an SLA alert.

    The same catalog entry + metric combination produces the same key,
    so re-running the checker will not produce duplicate NEW alerts.
    """
    raw = f"sla:{catalog_entry_id}:{violation_metric}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def check_and_alert_sla_breaches(
    session: AsyncSession,
    engagement_id: str,
) -> list[dict[str, Any]]:
    """Check quality SLAs for all catalog entries and create alerts for breaches.

    For each DataCatalogEntry in the engagement:
    1. Runs :func:`~src.governance.quality.check_quality_sla`.
    2. If the SLA is failing, creates a :class:`~src.core.models.MonitoringAlert`
       for each violation (using dedup_key to avoid duplicates for alerts
       already in NEW status).
    3. Returns a list of serialised alert dicts for the caller.

    Args:
        session: Async database session.
        engagement_id: The engagement UUID as a string.

    Returns:
        List of dicts describing created MonitoringAlert records.
    """
    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        logger.error("Invalid engagement_id: %s", engagement_id)
        return []

    # Fetch all catalog entries for the engagement
    rows = await session.execute(
        select(DataCatalogEntry).where(
            DataCatalogEntry.engagement_id == eng_uuid
        )
    )
    entries: list[DataCatalogEntry] = list(rows.scalars().all())

    if not entries:
        logger.info(
            "No catalog entries found for engagement %s; nothing to check.",
            engagement_id,
        )
        return []

    # Get or create the sentinel monitoring job
    governance_job = await _get_or_create_governance_job(session, eng_uuid)

    created_alerts: list[dict[str, Any]] = []

    for entry in entries:
        sla_result: SLAResult = await check_quality_sla(session, entry)

        if sla_result.passing:
            logger.debug(
                "Catalog entry %s (%s): SLA passing.",
                entry.id,
                entry.dataset_name,
            )
            continue

        # Create one alert per violation so each can be acknowledged
        # independently, with dedup to avoid flooding on repeated checks.
        for violation in sla_result.violations:
            dedup_key = _make_dedup_key(entry.id, violation.metric)

            # Skip if an open (NEW) alert already exists for this breach
            existing_alert = await session.execute(
                select(MonitoringAlert).where(
                    MonitoringAlert.dedup_key == dedup_key,
                    MonitoringAlert.status == AlertStatus.NEW,
                )
            )
            if existing_alert.scalar_one_or_none() is not None:
                logger.debug(
                    "Dedup: open alert already exists for %s / %s",
                    entry.dataset_name,
                    violation.metric,
                )
                continue

            alert = MonitoringAlert(
                engagement_id=eng_uuid,
                monitoring_job_id=governance_job.id,
                severity=AlertSeverity.MEDIUM,
                status=AlertStatus.NEW,
                title=(
                    f"SLA breach: {entry.dataset_name} — {violation.metric}"
                ),
                description=violation.message,
                deviation_ids=[],
                dedup_key=dedup_key,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(alert)
            await session.flush()

            alert_dict = {
                "id": str(alert.id),
                "engagement_id": str(alert.engagement_id),
                "monitoring_job_id": str(alert.monitoring_job_id),
                "severity": alert.severity.value,
                "status": alert.status.value,
                "title": alert.title,
                "description": alert.description,
                "dedup_key": alert.dedup_key,
                "catalog_entry_id": str(entry.id),
                "catalog_entry_name": entry.dataset_name,
                "violation_metric": violation.metric,
                "violation_threshold": violation.threshold,
                "violation_actual": violation.actual,
                "created_at": alert.created_at.isoformat(),
            }
            created_alerts.append(alert_dict)
            logger.info(
                "Created SLA breach alert %s for catalog entry %s (%s)",
                alert.id,
                entry.dataset_name,
                violation.metric,
            )

    return created_alerts
