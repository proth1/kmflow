"""Evidence management routes.

Provides file upload, listing, validation, and fragment retrieval
for evidence items within engagements.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AuditAction,
    AuditLog,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    FragmentType,
    User,
    ValidationStatus,
)
from src.core.permissions import require_permission
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
    file_path: str | None = None
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


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


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

    # Score quality
    quality_scores = await score_evidence(session, evidence_item)

    await session.commit()
    await session.refresh(evidence_item)

    return {
        "evidence": evidence_item,
        "fragment_count": len(fragments),
        "duplicate_of_id": duplicate_of_id,
        "quality_scores": quality_scores,
    }


@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(
    evidence_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
    """Get evidence item details including fragment count."""
    result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    # Count fragments
    frag_count_result = await session.execute(
        select(func.count()).select_from(EvidenceFragment).where(EvidenceFragment.evidence_id == evidence_id)
    )
    fragment_count = frag_count_result.scalar() or 0

    return {
        **{
            "id": evidence.id,
            "engagement_id": evidence.engagement_id,
            "name": evidence.name,
            "category": evidence.category,
            "format": evidence.format,
            "content_hash": evidence.content_hash,
            "file_path": evidence.file_path,
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
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> dict[str, Any]:
    """List evidence items with optional filtering.

    Query parameters:
    - engagement_id: Filter by engagement
    - category: Filter by evidence category
    - validation_status: Filter by validation status
    - limit: Maximum results (default 20)
    - offset: Number of results to skip (default 0)
    """
    query = select(EvidenceItem)
    count_query = select(func.count()).select_from(EvidenceItem)

    if engagement_id is not None:
        query = query.where(EvidenceItem.engagement_id == engagement_id)
        count_query = count_query.where(EvidenceItem.engagement_id == engagement_id)
    if category is not None:
        query = query.where(EvidenceItem.category == category)
        count_query = count_query.where(EvidenceItem.category == category)
    if validation_status is not None:
        query = query.where(EvidenceItem.validation_status == validation_status)
        count_query = count_query.where(EvidenceItem.validation_status == validation_status)

    query = query.offset(offset).limit(limit).order_by(EvidenceItem.created_at.desc())

    result = await session.execute(query)
    items = list(result.scalars().all())

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

    for eid in payload.evidence_ids:
        result = await session.execute(select(EvidenceItem).where(EvidenceItem.id == eid))
        evidence = result.scalar_one_or_none()
        if not evidence:
            errors.append(f"Evidence item {eid} not found")
            continue

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
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("evidence:read")),
) -> list[EvidenceFragment]:
    """Get extracted fragments for an evidence item.

    Query parameters:
    - fragment_type: Optional filter by fragment type
    """
    # Verify evidence exists
    ev_result = await session.execute(select(EvidenceItem.id).where(EvidenceItem.id == evidence_id))
    if not ev_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence item {evidence_id} not found",
        )

    query = select(EvidenceFragment).where(EvidenceFragment.evidence_id == evidence_id)
    if fragment_type is not None:
        query = query.where(EvidenceFragment.fragment_type == fragment_type)

    query = query.order_by(EvidenceFragment.created_at)

    result = await session.execute(query)
    return list(result.scalars().all())
