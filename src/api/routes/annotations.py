"""SME annotation routes for gap analysis artifacts.

Provides CRUD operations for annotations attached to engagement
artifacts such as gap analysis results, process elements, and evidence items.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import Annotation, AuditAction, AuditLog, User
from src.core.permissions import require_engagement_access, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/annotations", tags=["annotations"])


# -- Schemas ------------------------------------------------------------------


class AnnotationCreate(BaseModel):
    """Schema for creating an annotation."""

    engagement_id: UUID
    target_type: str = Field(..., min_length=1, max_length=100)
    target_id: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)


class AnnotationUpdate(BaseModel):
    """Schema for updating an annotation (PATCH)."""

    content: str = Field(..., min_length=1)


class AnnotationResponse(BaseModel):
    """Schema for annotation responses."""

    model_config = {"from_attributes": True}

    id: UUID
    engagement_id: UUID
    target_type: str
    target_id: str
    author_id: str
    content: str
    created_at: datetime
    updated_at: datetime


class AnnotationList(BaseModel):
    """Schema for listing annotations."""

    items: list[AnnotationResponse]
    total: int


# -- Routes -------------------------------------------------------------------


@router.post("/", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    payload: AnnotationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Annotation:
    """Create a new annotation on an engagement artifact."""
    annotation = Annotation(
        engagement_id=payload.engagement_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        author_id=str(user.id) if hasattr(user, "id") else "system",
        content=payload.content,
    )
    session.add(annotation)

    audit = AuditLog(
        engagement_id=payload.engagement_id,
        action=AuditAction.ANNOTATION_CREATED,
        actor=str(user.id) if hasattr(user, "id") else "system",
        details=f"Created annotation on {payload.target_type}:{payload.target_id}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(annotation)
    return annotation


@router.get("/", response_model=AnnotationList)
async def list_annotations(
    engagement_id: UUID,
    target_type: str | None = None,
    target_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List annotations for an engagement with optional filters.

    Args:
        engagement_id: Required engagement scope.
        target_type: Filter by target type (e.g., 'gap', 'process_element').
        target_id: Filter by specific target ID.
        limit: Max results.
        offset: Pagination offset.
    """
    query = select(Annotation).where(Annotation.engagement_id == engagement_id)
    count_query = select(func.count()).select_from(Annotation).where(Annotation.engagement_id == engagement_id)

    if target_type is not None:
        query = query.where(Annotation.target_type == target_type)
        count_query = count_query.where(Annotation.target_type == target_type)
    if target_id is not None:
        query = query.where(Annotation.target_id == target_id)
        count_query = count_query.where(Annotation.target_id == target_id)

    query = query.order_by(Annotation.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    return {"items": items, "total": total}


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Annotation:
    """Get a single annotation by ID."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation {annotation_id} not found")
    return annotation


@router.patch("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: UUID,
    payload: AnnotationUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> Annotation:
    """Update an annotation's content."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation {annotation_id} not found")

    annotation.content = payload.content

    audit = AuditLog(
        engagement_id=annotation.engagement_id,
        action=AuditAction.ANNOTATION_UPDATED,
        actor=str(user.id) if hasattr(user, "id") else "system",
        details=f"Updated annotation {annotation_id}",
    )
    session.add(audit)

    await session.commit()
    await session.refresh(annotation)
    return annotation


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:update")),
) -> None:
    """Delete an annotation. Only the author may delete their own annotation."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation {annotation_id} not found")

    user_id = str(user.id) if hasattr(user, "id") else None
    if user_id is None or annotation.author_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete another user's annotation",
        )

    audit = AuditLog(
        engagement_id=annotation.engagement_id,
        action=AuditAction.ANNOTATION_DELETED,
        actor=str(user.id) if hasattr(user, "id") else "system",
        details=f"Deleted annotation {annotation_id}",
    )
    session.add(audit)

    await session.delete(annotation)
    await session.commit()
