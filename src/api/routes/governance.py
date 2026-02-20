"""Data governance API routes.

Exposes catalog management, policy evaluation, SLA checking, and
governance package export for the KMFlow data governance framework.

All write operations require ``governance:write``.
All read operations require ``governance:read``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import DataCatalogEntry, DataClassification, DataLayer, User
from src.core.permissions import require_engagement_access, require_permission
from src.datalake.backend import get_storage_backend
from src.datalake.silver import SilverLayerWriter
from src.governance.alerting import check_and_alert_sla_breaches
from src.governance.catalog import DataCatalogService
from src.governance.export import export_governance_package
from src.governance.migration import MigrationResult, migrate_engagement
from src.governance.policy import PolicyEngine, PolicyViolation
from src.governance.quality import SLAResult, check_quality_sla

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/governance",
    tags=["governance"],
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class CatalogEntryCreate(BaseModel):
    """Request body for creating a catalog entry."""

    dataset_name: str
    dataset_type: str
    layer: DataLayer
    engagement_id: uuid.UUID | None = None
    schema_definition: dict[str, Any] | None = None
    owner: str | None = None
    classification: DataClassification = DataClassification.INTERNAL
    quality_sla: dict[str, Any] | None = None
    retention_days: int | None = None
    description: str | None = None


class CatalogEntryUpdate(BaseModel):
    """Request body for updating a catalog entry (all fields optional)."""

    dataset_name: str | None = None
    dataset_type: str | None = None
    layer: DataLayer | None = None
    schema_definition: dict[str, Any] | None = None
    owner: str | None = None
    classification: DataClassification | None = None
    quality_sla: dict[str, Any] | None = None
    retention_days: int | None = None
    description: str | None = None


class CatalogEntryResponse(BaseModel):
    """Response schema for a data catalog entry."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    dataset_name: str
    dataset_type: str
    layer: DataLayer
    engagement_id: uuid.UUID | None
    schema_definition: dict[str, Any] | None
    owner: str | None
    classification: DataClassification
    quality_sla: dict[str, Any] | None
    retention_days: int | None
    description: str | None
    row_count: int | None
    size_bytes: int | None
    delta_table_path: str | None
    created_at: datetime
    updated_at: datetime


class PolicyViolationResponse(BaseModel):
    """Response schema for a single policy violation."""

    policy_name: str
    severity: str
    message: str
    entry_id: uuid.UUID


class PolicyEvaluateRequest(BaseModel):
    """Request body for policy evaluation."""

    entry_id: uuid.UUID


class PolicyEvaluateResponse(BaseModel):
    """Response schema for a policy evaluation run."""

    entry_id: uuid.UUID
    compliant: bool
    violation_count: int
    violations: list[PolicyViolationResponse]


class SLAViolationResponse(BaseModel):
    """Response schema for a quality SLA violation."""

    metric: str
    threshold: float
    actual: float
    message: str


class SLACheckResponse(BaseModel):
    """Response schema for a quality SLA check."""

    entry_id: uuid.UUID
    passing: bool
    evidence_count: int
    checked_at: datetime
    violations: list[SLAViolationResponse]


# ---------------------------------------------------------------------------
# Catalog routes
# ---------------------------------------------------------------------------


class CatalogEntryList(BaseModel):
    """Response schema for listing catalog entries."""

    items: list[CatalogEntryResponse]
    total: int


@router.get("/catalog", response_model=CatalogEntryList)
async def list_catalog_entries(
    engagement_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
) -> dict[str, Any]:
    """List all data catalog entries.

    Optionally filter by engagement_id. Supports pagination via
    ``limit`` and ``offset`` query parameters.
    """
    from sqlalchemy import func, select as sa_select

    svc = DataCatalogService(session)
    items = await svc.list_entries(
        engagement_id=engagement_id,
        limit=limit,
        offset=offset,
    )
    count_query = sa_select(func.count()).select_from(DataCatalogEntry)
    if engagement_id is not None:
        count_query = count_query.where(DataCatalogEntry.engagement_id == engagement_id)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.post(
    "/catalog",
    response_model=CatalogEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_catalog_entry(
    body: CatalogEntryCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
) -> DataCatalogEntry:
    """Create a new data catalog entry."""
    svc = DataCatalogService(session)
    entry = await svc.create_entry(
        dataset_name=body.dataset_name,
        dataset_type=body.dataset_type,
        layer=body.layer,
        engagement_id=body.engagement_id,
        schema_definition=body.schema_definition,
        owner=body.owner,
        classification=body.classification,
        quality_sla=body.quality_sla,
        retention_days=body.retention_days,
        description=body.description,
    )
    await session.commit()
    return entry


@router.get("/catalog/{entry_id}", response_model=CatalogEntryResponse)
async def get_catalog_entry(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
) -> DataCatalogEntry:
    """Get a single data catalog entry by ID."""
    svc = DataCatalogService(session)
    entry = await svc.get_entry(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {entry_id} not found",
        )
    return entry


@router.put("/catalog/{entry_id}", response_model=CatalogEntryResponse)
async def update_catalog_entry(
    entry_id: uuid.UUID,
    body: CatalogEntryUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
) -> DataCatalogEntry:
    """Update fields on an existing catalog entry.

    Only fields present in the request body are updated.
    """
    svc = DataCatalogService(session)
    updates = body.model_dump(exclude_none=True)
    entry = await svc.update_entry(entry_id, **updates)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {entry_id} not found",
        )
    await session.commit()
    return entry


@router.delete("/catalog/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_entry(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
) -> None:
    """Delete a data catalog entry."""
    svc = DataCatalogService(session)
    deleted = await svc.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {entry_id} not found",
        )
    await session.commit()


# ---------------------------------------------------------------------------
# Policy routes
# ---------------------------------------------------------------------------


@router.get("/policies")
async def list_policies(
    user: User = Depends(require_permission("governance:read")),
) -> dict[str, Any]:
    """Return the active governance policy definitions.

    Returns the raw YAML policy dict loaded from the default policy file.
    Clients can inspect retention limits, classification requirements, and
    naming conventions in effect.
    """
    engine = PolicyEngine()
    return {
        "policy_file": str(engine.policy_file),
        "policies": engine.policies,
    }


@router.post("/policies/evaluate", response_model=PolicyEvaluateResponse)
async def evaluate_policies(
    body: PolicyEvaluateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
) -> dict[str, Any]:
    """Evaluate active governance policies against a catalog entry.

    Returns a list of violations (empty = fully compliant).
    """
    svc = DataCatalogService(session)
    entry = await svc.get_entry(body.entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {body.entry_id} not found",
        )

    engine = PolicyEngine()
    violations: list[PolicyViolation] = engine.evaluate(entry)

    return {
        "entry_id": entry.id,
        "compliant": len(violations) == 0,
        "violation_count": len(violations),
        "violations": [
            {
                "policy_name": v.policy_name,
                "severity": v.severity,
                "message": v.message,
                "entry_id": v.entry_id,
            }
            for v in violations
        ],
    }


# ---------------------------------------------------------------------------
# Export route
# ---------------------------------------------------------------------------


@router.get("/export/{engagement_id}")
async def export_governance(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Response:
    """Export a governance package ZIP for an engagement.

    Returns a ZIP archive containing:
    - ``catalog.json``: All catalog entries for this engagement.
    - ``policies.yaml``: Active policy definitions.
    - ``lineage_summary.json``: Evidence lineage chains.
    - ``quality_report.json``: SLA compliance results.
    """
    pkg_bytes = await export_governance_package(session, engagement_id)

    filename = f"governance_{engagement_id}.zip"
    return Response(
        content=pkg_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pkg_bytes)),
        },
    )


# ---------------------------------------------------------------------------
# Quality SLA route
# ---------------------------------------------------------------------------


@router.get("/quality/{entry_id}", response_model=SLACheckResponse)
async def check_entry_quality_sla(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
) -> dict[str, Any]:
    """Check quality SLA compliance for a catalog entry.

    Evaluates evidence items in the entry's engagement scope against
    the ``quality_sla`` thresholds defined on the catalog entry.

    Returns passing status, violation details, and count of evidence
    items evaluated.
    """
    svc = DataCatalogService(session)
    entry = await svc.get_entry(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {entry_id} not found",
        )

    result: SLAResult = await check_quality_sla(session, entry)

    return {
        "entry_id": entry_id,
        "passing": result.passing,
        "evidence_count": result.evidence_count,
        "checked_at": result.checked_at,
        "violations": [
            {
                "metric": v.metric,
                "threshold": v.threshold,
                "actual": v.actual,
                "message": v.message,
            }
            for v in result.violations
        ],
    }


# ---------------------------------------------------------------------------
# Migration schemas and routes
# ---------------------------------------------------------------------------


class MigrationResultResponse(BaseModel):
    """Response schema for a migration run."""

    engagement_id: str
    items_processed: int
    items_skipped: int
    items_failed: int
    bronze_written: int
    silver_written: int
    catalog_entries_created: int
    lineage_records_created: int
    errors: list[str]
    dry_run: bool


@router.post(
    "/migrate/{engagement_id}",
    response_model=MigrationResultResponse,
    status_code=status.HTTP_200_OK,
)
async def trigger_migration(
    engagement_id: uuid.UUID,
    dry_run: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
    _engagement_user: User = Depends(require_engagement_access),
) -> MigrationResult:
    """Trigger bulk migration of evidence data to Delta Lake layers.

    Migrates all EvidenceItem records for the engagement into the Bronze
    and Silver Delta tables retroactively. Creates EvidenceLineage and
    DataCatalogEntry records if absent.

    Pass ``?dry_run=true`` to simulate without writing.
    """
    storage_backend = get_storage_backend("local")
    silver_writer = SilverLayerWriter()

    result = await migrate_engagement(
        session=session,
        engagement_id=str(engagement_id),
        storage_backend=storage_backend,
        silver_writer=silver_writer,
        dry_run=dry_run,
    )
    return result


# ---------------------------------------------------------------------------
# Alerting routes
# ---------------------------------------------------------------------------


@router.post(
    "/alerts/{engagement_id}",
    status_code=status.HTTP_200_OK,
)
async def check_sla_and_create_alerts(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
    _engagement_user: User = Depends(require_engagement_access),
) -> list[dict[str, Any]]:
    """Check quality SLAs for all catalog entries and create alerts for breaches.

    For each DataCatalogEntry in the engagement, evaluates the quality SLA
    and creates a MonitoringAlert for every violation found. Uses dedup keys
    to avoid creating duplicate alerts when an open alert already exists.

    Returns the list of newly created alert records.
    """
    alerts = await check_and_alert_sla_breaches(
        session=session,
        engagement_id=str(engagement_id),
    )
    await session.commit()
    return alerts


# ---------------------------------------------------------------------------
# Governance health dashboard route
# ---------------------------------------------------------------------------


class CatalogEntrySLAStatus(BaseModel):
    """SLA status for a single catalog entry."""

    entry_id: uuid.UUID
    name: str
    classification: str
    sla_passing: bool
    violation_count: int


class GovernanceHealthResponse(BaseModel):
    """Aggregate governance health summary for an engagement."""

    engagement_id: uuid.UUID
    total_entries: int
    passing_count: int
    failing_count: int
    compliance_percentage: float
    entries: list[CatalogEntrySLAStatus]


@router.get(
    "/health/{engagement_id}",
    response_model=GovernanceHealthResponse,
)
async def get_governance_health(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Return SLA compliance summary for all catalog entries in an engagement.

    Evaluates the quality SLA for every DataCatalogEntry associated with
    the engagement and returns aggregate pass/fail counts along with
    per-entry detail.
    """
    svc = DataCatalogService(session)
    entries = await svc.list_entries(engagement_id=engagement_id)

    entry_statuses: list[dict[str, Any]] = []
    passing_count = 0

    for entry in entries:
        sla_result: SLAResult = await check_quality_sla(session, entry)
        if sla_result.passing:
            passing_count += 1

        entry_statuses.append(
            {
                "entry_id": entry.id,
                "name": entry.dataset_name,
                "classification": entry.classification.value
                if hasattr(entry.classification, "value")
                else str(entry.classification),
                "sla_passing": sla_result.passing,
                "violation_count": len(sla_result.violations),
            }
        )

    total = len(entries)
    failing_count = total - passing_count
    compliance_pct = (passing_count / total * 100.0) if total > 0 else 100.0

    return {
        "engagement_id": engagement_id,
        "total_entries": total,
        "passing_count": passing_count,
        "failing_count": failing_count,
        "compliance_percentage": round(compliance_pct, 2),
        "entries": entry_statuses,
    }
