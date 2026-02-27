"""Data governance API routes.

Exposes catalog management, policy evaluation, SLA checking, and
governance package export for the KMFlow data governance framework.

All write operations require ``governance:write``.
All read operations require ``governance:read``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.audit import log_audit
from src.core.models import (
    AuditAction,
    DataCatalogEntry,
    DataClassification,
    DataLayer,
    Engagement,
    EvidenceItem,
    GapFinding,
    GovernanceGapStatus,
    Regulation,
    User,
)
from src.core.permissions import require_engagement_access, require_permission
from src.datalake.backend import get_storage_backend
from src.datalake.silver import SilverLayerWriter
from src.governance.alerting import check_and_alert_sla_breaches
from src.governance.catalog import DataCatalogService
from src.governance.export import export_governance_package
from src.governance.gap_detection import GovernanceGapDetectionService
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
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
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
    if body.engagement_id:
        await log_audit(
            session, body.engagement_id, AuditAction.ENGAGEMENT_UPDATED,
            f"Created catalog entry: {body.dataset_name}", actor=str(user.id),
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
    if entry.engagement_id:
        await log_audit(
            session, entry.engagement_id, AuditAction.ENGAGEMENT_UPDATED,
            f"Updated catalog entry: {entry.dataset_name}", actor=str(user.id),
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
    # Fetch entry first to get engagement_id for audit
    entry = await svc.get_entry(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalog entry {entry_id} not found",
        )
    if entry.engagement_id:
        await log_audit(
            session, entry.engagement_id, AuditAction.ENGAGEMENT_UPDATED,
            f"Deleted catalog entry: {entry.dataset_name}", actor=str(user.id),
        )
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

    # Batch-fetch all evidence items for this engagement once (avoids N+1).
    evidence_query = select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    evidence_result = await session.execute(evidence_query)
    evidence_items: list[EvidenceItem] = list(evidence_result.scalars().all())

    entry_statuses: list[dict[str, Any]] = []
    passing_count = 0

    for entry in entries:
        sla_result: SLAResult = await check_quality_sla(session, entry, evidence_items=evidence_items)
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


# ---------------------------------------------------------------------------
# Gap detection schemas
# ---------------------------------------------------------------------------


class GapDetectRequest(BaseModel):
    """Request body for triggering gap detection."""

    auto_generate_shelf_requests: bool = False


class GapFindingResponse(BaseModel):
    """Response for a single gap finding."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    engagement_id: uuid.UUID
    activity_id: uuid.UUID
    regulation_id: uuid.UUID | None
    gap_type: str
    severity: str
    status: str
    description: str | None
    resolved_at: datetime | None
    created_at: datetime


class GapDetectionResultResponse(BaseModel):
    """Response for a gap detection run."""

    engagement_id: uuid.UUID
    new_gaps: int
    resolved_gaps: int
    total_open: int
    findings: list[GapFindingResponse]


class GapListResponse(BaseModel):
    """Response for listing gap findings."""

    engagement_id: uuid.UUID
    findings: list[GapFindingResponse]
    total: int


# ---------------------------------------------------------------------------
# Gap detection routes
# ---------------------------------------------------------------------------


@router.post(
    "/engagements/{engagement_id}/governance-gaps/detect",
    response_model=GapDetectionResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def detect_governance_gaps(
    engagement_id: uuid.UUID,
    body: GapDetectRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:write")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Detect governance gaps in an engagement's process activities.

    Cross-references active regulations and their obligations against
    process activities to identify where controls are mandated but absent.
    Optionally auto-generates shelf data request items for detected gaps.
    """
    # Verify engagement exists
    eng_result = await session.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Fetch regulations for this engagement
    reg_result = await session.execute(
        select(Regulation).where(Regulation.engagement_id == engagement_id)
    )
    regulations = list(reg_result.scalars().all())

    reg_dicts = [
        {
            "id": str(r.id),
            "name": r.name,
            "obligations": r.obligations,
        }
        for r in regulations
    ]

    # Run gap detection via graph service
    from src.semantic.graph import KnowledgeGraphService

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    detector = GovernanceGapDetectionService(graph_service)
    new_gap_data = await detector.detect_gaps(str(engagement_id), reg_dicts)

    # Fetch existing open gaps for resolution check
    existing_result = await session.execute(
        select(GapFinding).where(
            GapFinding.engagement_id == engagement_id,
            GapFinding.status == GovernanceGapStatus.OPEN,
        )
    )
    existing_open = list(existing_result.scalars().all())

    existing_open_dicts = [
        {"id": str(g.id), "activity_id": str(g.activity_id)}
        for g in existing_open
    ]

    # Resolve gaps that are now covered
    resolved_ids = await detector.resolve_covered_gaps(
        str(engagement_id), existing_open_dicts
    )
    resolved_count = 0
    now = datetime.now(UTC)
    for gap in existing_open:
        if str(gap.id) in resolved_ids:
            gap.status = GovernanceGapStatus.RESOLVED
            gap.resolved_at = now
            resolved_count += 1

    # Deduplicate: don't re-create gaps for activities that already have open findings
    existing_activity_ids = {
        str(g.activity_id) for g in existing_open if g.status == GovernanceGapStatus.OPEN
    }
    new_findings: list[GapFinding] = []
    for gd in new_gap_data:
        if gd["activity_id"] in existing_activity_ids:
            continue
        finding = GapFinding(
            engagement_id=engagement_id,
            activity_id=uuid.UUID(gd["activity_id"]),
            regulation_id=uuid.UUID(gd["regulation_id"]) if gd.get("regulation_id") else None,
            gap_type=gd["gap_type"],
            severity=gd["severity"],
            status=gd["status"],
            description=gd["description"],
        )
        session.add(finding)
        new_findings.append(finding)

    await log_audit(
        session,
        engagement_id,
        AuditAction.ENGAGEMENT_UPDATED,
        f"Gap detection: {len(new_findings)} new, {resolved_count} resolved",
        actor=str(user.id),
    )

    await session.commit()

    # Refresh to get IDs and timestamps
    for f in new_findings:
        await session.refresh(f)

    # Count total open after this run
    open_count_result = await session.execute(
        select(GapFinding).where(
            GapFinding.engagement_id == engagement_id,
            GapFinding.status == GovernanceGapStatus.OPEN,
        )
    )
    total_open = len(list(open_count_result.scalars().all()))

    return {
        "engagement_id": engagement_id,
        "new_gaps": len(new_findings),
        "resolved_gaps": resolved_count,
        "total_open": total_open,
        "findings": [
            {
                "id": f.id,
                "engagement_id": f.engagement_id,
                "activity_id": f.activity_id,
                "regulation_id": f.regulation_id,
                "gap_type": f.gap_type.value if hasattr(f.gap_type, "value") else str(f.gap_type),
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                "description": f.description,
                "resolved_at": f.resolved_at,
                "created_at": f.created_at,
            }
            for f in new_findings
        ],
    }


@router.get(
    "/engagements/{engagement_id}/governance-gaps",
    response_model=GapListResponse,
)
async def list_governance_gaps(
    engagement_id: uuid.UUID,
    gap_status: str | None = Query(None, alias="status", description="Filter by status: OPEN or RESOLVED"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("governance:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List governance gap findings for an engagement.

    Filter by status (OPEN/RESOLVED) or return all. Paginated.
    """
    # Verify engagement exists
    eng_result = await session.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    if not eng_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )

    # Build query
    query = (
        select(GapFinding)
        .where(GapFinding.engagement_id == engagement_id)
        .order_by(GapFinding.created_at.desc())
    )

    if gap_status:
        normalized = gap_status.lower()
        if normalized in ("open", "resolved"):
            query = query.where(GapFinding.status == normalized)

    # Count total
    from sqlalchemy import func as sa_func

    count_query = (
        select(sa_func.count())
        .select_from(GapFinding)
        .where(GapFinding.engagement_id == engagement_id)
    )
    if gap_status:
        normalized = gap_status.lower()
        if normalized in ("open", "resolved"):
            count_query = count_query.where(GapFinding.status == normalized)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # Fetch page
    result = await session.execute(query.offset(offset).limit(limit))
    findings = list(result.scalars().all())

    return {
        "engagement_id": engagement_id,
        "findings": [
            {
                "id": f.id,
                "engagement_id": f.engagement_id,
                "activity_id": f.activity_id,
                "regulation_id": f.regulation_id,
                "gap_type": f.gap_type.value if hasattr(f.gap_type, "value") else str(f.gap_type),
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                "description": f.description,
                "resolved_at": f.resolved_at,
                "created_at": f.created_at,
            }
            for f in findings
        ],
        "total": total,
    }
