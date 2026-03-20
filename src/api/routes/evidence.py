"""Evidence management routes.

Provides file upload, listing, validation, and fragment retrieval
for evidence items within engagements.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.config import Settings, get_settings
from src.core.models import (
    AuditAction,
    AuditLog,
    DataClassification,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    FragmentType,
    User,
    UserRole,
    ValidationStatus,
)
from src.core.permissions import (
    require_classification_access,
    require_engagement_access,
    require_permission,
    verify_engagement_member,
)
from src.core.services.gdpr_service import GdprComplianceService
from src.evidence.exceptions import EvidenceValidationError
from src.evidence.pipeline import ingest_evidence
from src.evidence.quality import score_evidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


# -- Request/Response Schemas ------------------------------------------------


class EvidenceResponse(BaseModel):
    """Schema for evidence item responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    name: str
    category: EvidenceCategory
    format: str
    content_hash: str | None = None
    download_url: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    metadata_json: dict | None = None
    source_date: Any | None = None
    completeness_score: float
    reliability_score: float
    freshness_score: float
    consistency_score: float
    quality_score: float | None = None
    duplicate_of_id: UUID | None = None
    validation_status: ValidationStatus
    classification: DataClassification = DataClassification.INTERNAL
    created_at: Any | None = None
    updated_at: Any | None = None


class EvidenceDetailResponse(EvidenceResponse):
    """Evidence response with fragment details."""

    fragment_count: int = 0


class FragmentResponse(BaseModel):
    """Schema for evidence fragment responses."""

    model_config = {"from_attributes": True}

    id: UUID
    evidence_id: UUID
    fragment_type: FragmentType
    content: str
    metadata_json: str | None = None
    created_at: Any | None = None


class EvidenceCatalogItem(BaseModel):
    """Compact schema for evidence catalog entries."""

    model_config = {"from_attributes": True}

    id: UUID
    title: str | None = None
    name: str
    category: EvidenceCategory
    creation_date: str | None = None
    quality_score: float | None = None
    detected_language: str | None = None
    validation_status: ValidationStatus
    file_size_bytes: int | None = None


class EvidenceCatalogResponse(BaseModel):
    """Paginated response for the evidence catalog API."""

    items: list[EvidenceCatalogItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class EvidenceList(BaseModel):
    """Schema for listing evidence items."""

    items: list[EvidenceResponse]
    total: int


class ValidationUpdate(BaseModel):
    """Schema for updating validation status."""

    validation_status: ValidationStatus
    actor: str = "system"


class BatchValidationRequest(BaseModel):
    """Schema for batch validation."""

    evidence_ids: list[UUID]
    validation_status: ValidationStatus
    actor: str = "system"


class BatchValidationResponse(BaseModel):
    """Schema for batch validation response."""

    updated_count: int
    errors: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    """Schema for evidence upload response."""

    evidence: EvidenceResponse
    fragment_count: int
    duplicate_of_id: UUID | None = None
    quality_scores: dict[str, float] | None = None
    warnings: list[str] = Field(default_factory=list)


# -- Routes -------------------------------------------------------------------


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    engagement_id: UUID = Form(...),
    category: EvidenceCategory | None = Form(None),
    metadata: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:create")),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Upload a file as evidence for an engagement.

    The file is stored locally, parsed for fragments, checked for duplicates,
    and quality scored automatically.

    Form fields:
    - file: The evidence file to upload
    - engagement_id: UUID of the engagement
    - category: Evidence category (auto-detected if not provided)
    - metadata: Optional JSON string with additional metadata
    """
    # Early Content-Length check to reject oversized uploads before buffering
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB.",
        )

    # Read file content
    file_content = await file.read()
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Parse metadata JSON if provided
    metadata_dict = None
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in metadata field",
            ) from None

    file_name = file.filename or "unknown"

    # Run the ingestion pipeline (with intelligence activation)
    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    try:
        evidence_item, fragments, duplicate_of_id = await ingest_evidence(
            session=session,
            engagement_id=engagement_id,
            file_content=file_content,
            file_name=file_name,
            category=category,
            metadata=metadata_dict,
            mime_type=file.content_type,
            neo4j_driver=neo4j_driver,
        )
    except EvidenceValidationError as exc:
        raise HTTPException(status_code=exc.status_hint, detail=str(exc)) from exc

    # Score quality
    quality_scores = await score_evidence(session, evidence_item)

    # Check for active DPA — soft warning if missing
    warnings: list[str] = []
    try:
        gdpr_service = GdprComplianceService(session)
        active_dpa = await gdpr_service.get_active_dpa(engagement_id)
        if active_dpa is None:
            warnings.append(
                "dpa_warning: No active Data Processing Agreement exists for this engagement. "
                "GDPR Article 28 requires a DPA before processing client data."
            )
    except (SQLAlchemyError, ValueError):
        logger.warning("Failed to check DPA status for engagement %s", engagement_id, exc_info=True)

    await session.commit()
    await session.refresh(evidence_item)

    return {
        "evidence": evidence_item,
        "fragment_count": len(fragments),
        "duplicate_of_id": duplicate_of_id,
        "quality_scores": quality_scores,
        "warnings": warnings,
    }


@router.get("/catalog", response_model=EvidenceCatalogResponse)
async def catalog_evidence(
    engagement_id: UUID = Query(...),
    category: EvidenceCategory | None = None,
    date_from: str | None = Query(None, description="ISO date lower bound (inclusive)"),
    date_to: str | None = Query(None, description="ISO date upper bound (inclusive)"),
    language: str | None = Query(None, max_length=10, description="ISO 639-1 language code filter"),
    q: str | None = Query(None, description="Full-text search query"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
    _: None = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Search the evidence catalog with filtering and pagination.

    Supports filtering by category, date range, language, and full-text search.
    Returns compact catalog items with pagination metadata.
    """
    query = select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)

    if category is not None:
        query = query.where(EvidenceItem.category == category)
        count_query = count_query.where(EvidenceItem.category == category)

    if date_from is not None:
        query = query.where(EvidenceItem.created_at >= date_from)
        count_query = count_query.where(EvidenceItem.created_at >= date_from)

    if date_to is not None:
        query = query.where(EvidenceItem.created_at <= date_to)
        count_query = count_query.where(EvidenceItem.created_at <= date_to)

    if language is not None:
        query = query.where(EvidenceItem.detected_language == language)
        count_query = count_query.where(EvidenceItem.detected_language == language)

    if q is not None:
        # Escape LIKE wildcards to prevent pattern injection
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped_q}%"
        query = query.where(EvidenceItem.name.ilike(like_pattern, escape="\\"))
        count_query = count_query.where(EvidenceItem.name.ilike(like_pattern, escape="\\"))

    query = query.offset(offset).limit(limit).order_by(EvidenceItem.created_at.desc())

    result = await session.execute(query)
    items = list(result.scalars().all())

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    catalog_items = []
    for item in items:
        em = item.extracted_metadata or {}
        catalog_items.append(
            {
                "id": item.id,
                "title": em.get("title"),
                "name": item.name,
                "category": item.category,
                "creation_date": em.get("creation_date"),
                "quality_score": item.quality_score,
                "detected_language": item.detected_language,
                "validation_status": item.validation_status,
                "file_size_bytes": item.size_bytes,
            }
        )

    return {
        "items": catalog_items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
    """Get evidence item details including fragment count."""
    # Fetch evidence item and fragment count in a single query
    combined_result = await session.execute(
        select(EvidenceItem, func.count(EvidenceFragment.id).label("fragment_count"))
        .outerjoin(EvidenceFragment, EvidenceFragment.evidence_id == EvidenceItem.id)
        .where(EvidenceItem.id == evidence_id)
        .group_by(EvidenceItem.id)
    )
    row = combined_result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    evidence, fragment_count = row
    await verify_engagement_member(session, user, evidence.engagement_id)
    require_classification_access(evidence.classification, user)

    return {
        **{
            "id": evidence.id,
            "engagement_id": evidence.engagement_id,
            "name": evidence.name,
            "category": evidence.category,
            "format": evidence.format,
            "content_hash": evidence.content_hash,
            "download_url": f"/evidence/{evidence.id}/download" if evidence.file_path else None,
            "size_bytes": evidence.size_bytes,
            "mime_type": evidence.mime_type,
            "metadata_json": evidence.metadata_json,
            "source_date": evidence.source_date,
            "completeness_score": evidence.completeness_score,
            "reliability_score": evidence.reliability_score,
            "freshness_score": evidence.freshness_score,
            "consistency_score": evidence.consistency_score,
            "quality_score": evidence.quality_score,
            "duplicate_of_id": evidence.duplicate_of_id,
            "validation_status": evidence.validation_status,
            "classification": evidence.classification,
            "created_at": evidence.created_at,
            "updated_at": evidence.updated_at,
        },
        "fragment_count": fragment_count,
    }


@router.get("/", response_model=EvidenceList)
async def list_evidence(
    engagement_id: UUID | None = None,
    category: EvidenceCategory | None = None,
    validation_status: ValidationStatus | None = None,
    classification: DataClassification | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
    """List evidence items with optional filtering.

    Query parameters:
    - engagement_id: Filter by engagement
    - category: Filter by evidence category
    - validation_status: Filter by validation status
    - classification: Filter by data sensitivity classification
    - limit: Maximum results (default 20)
    - offset: Number of results to skip (default 0)
    """
    query = select(EvidenceItem)
    count_query = select(func.count()).select_from(EvidenceItem)

    if engagement_id is not None:
        await verify_engagement_member(session, user, engagement_id)
        query = query.where(EvidenceItem.engagement_id == engagement_id)
        count_query = count_query.where(EvidenceItem.engagement_id == engagement_id)
    if category is not None:
        query = query.where(EvidenceItem.category == category)
        count_query = count_query.where(EvidenceItem.category == category)
    if validation_status is not None:
        query = query.where(EvidenceItem.validation_status == validation_status)
        count_query = count_query.where(EvidenceItem.validation_status == validation_status)
    if classification is not None:
        query = query.where(EvidenceItem.classification == classification)
        count_query = count_query.where(EvidenceItem.classification == classification)

    query = query.offset(offset).limit(limit).order_by(EvidenceItem.created_at.desc())

    result = await session.execute(query)
    items = list(result.scalars().all())

    # Classification filter: CLIENT_VIEWER role cannot see RESTRICTED data.
    # Applied to both query and count to avoid leaking the count of restricted items.
    if user.role == UserRole.CLIENT_VIEWER:
        items = [item for item in items if item.classification != DataClassification.RESTRICTED]
        count_query = count_query.where(EvidenceItem.classification != DataClassification.RESTRICTED)

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": items, "total": total}


@router.patch("/{evidence_id}/validate", response_model=EvidenceResponse)
async def update_validation_status(
    evidence_id: UUID,
    payload: ValidationUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:update")),
) -> EvidenceItem:
    """Update the validation status of an evidence item.

    Transitions evidence through the lifecycle:
    PENDING -> VALIDATED -> ACTIVE -> EXPIRED -> ARCHIVED
    """
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    await verify_engagement_member(session, user, evidence.engagement_id)
    old_status = evidence.validation_status
    evidence.validation_status = payload.validation_status

    # Audit log
    audit = AuditLog(
        engagement_id=evidence.engagement_id,
        action=AuditAction.EVIDENCE_VALIDATED,
        actor=payload.actor,
        details=json.dumps(
            {
                "evidence_id": str(evidence_id),
                "from_status": str(old_status),
                "to_status": str(payload.validation_status),
            }
        ),
    )
    session.add(audit)

    await session.commit()
    await session.refresh(evidence)
    return evidence


@router.post("/validate-batch", response_model=BatchValidationResponse)
async def batch_validate(
    payload: BatchValidationRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:update")),
) -> dict[str, Any]:
    """Batch update validation status for multiple evidence items."""
    updated_count = 0
    errors: list[str] = []

    # Bulk-fetch all evidence items in a single query (Fix N+1)
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id.in_(payload.evidence_ids)))
    evidence_map = {item.id: item for item in result.scalars().all()}

    # Identify missing items
    for eid in payload.evidence_ids:
        if eid not in evidence_map:
            errors.append(f"Evidence item {eid} not found")

    # Update found items
    for eid, evidence in evidence_map.items():
        old_status = evidence.validation_status
        evidence.validation_status = payload.validation_status

        audit = AuditLog(
            engagement_id=evidence.engagement_id,
            action=AuditAction.EVIDENCE_VALIDATED,
            actor=payload.actor,
            details=json.dumps(
                {
                    "evidence_id": str(eid),
                    "from_status": str(old_status),
                    "to_status": str(payload.validation_status),
                    "batch": True,
                }
            ),
        )
        session.add(audit)
        updated_count += 1

    await session.commit()
    return {"updated_count": updated_count, "errors": errors}


@router.get("/{evidence_id}/fragments", response_model=list[FragmentResponse])
async def get_fragments(
    evidence_id: UUID,
    fragment_type: FragmentType | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> list[EvidenceFragment]:
    """Get extracted fragments for an evidence item.

    Query parameters:
    - fragment_type: Optional filter by fragment type
    - limit: Maximum results to return (default 100, max 1000)
    - offset: Number of results to skip (default 0)
    """
    # Verify evidence exists and check engagement membership
    ev_result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id))
    evidence = ev_result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )
    await verify_engagement_member(session, user, evidence.engagement_id)
    require_classification_access(evidence.classification, user)

    query = select(EvidenceFragment).where(EvidenceFragment.evidence_id == evidence_id)
    if fragment_type is not None:
        query = query.where(EvidenceFragment.fragment_type == fragment_type)

    query = query.order_by(EvidenceFragment.created_at).limit(limit).offset(offset)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{evidence_id}/download")
async def download_evidence(
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> Response:
    """Download the raw file for an evidence item.

    SVG files are served with Content-Disposition: attachment to prevent
    browser rendering (XSS risk from untrusted SVG content).
    """
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    await verify_engagement_member(session, user, evidence.engagement_id)
    require_classification_access(evidence.classification, user)

    if not evidence.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No file available for this evidence item",
        )

    file_path = Path(evidence.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence file not found on storage",
        )

    content = file_path.read_bytes()

    mime_type = evidence.mime_type or "application/octet-stream"
    filename = file_path.name

    headers: dict[str, str] = {}
    # Force attachment download for SVG to prevent browser rendering of potentially
    # untrusted SVG content (SVG can contain executable JavaScript).
    if mime_type == "image/svg+xml" or filename.lower().endswith(".svg"):
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return Response(content=content, media_type=mime_type, headers=headers)
