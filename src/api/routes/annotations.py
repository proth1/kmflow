"""SME annotation routes for gap analysis artifacts.

Provides CRUD operations for annotations attached to engagement
artifacts such as gap analysis results, process elements, and evidence items.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Annotation, User
from src.core.permissions import require_permission

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
    created_at: Any
    updated_at: Any


class AnnotationList(BaseModel):
    """Schema for listing annotations."""

    items: list[AnnotationResponse]
    total: int


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


# -- Routes -------------------------------------------------------------------


@router.post("/", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    payload: AnnotationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
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
    user: User = Depends(require_permission("engagement:read")),
) -> Annotation:
    """Update an annotation's content."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation {annotation_id} not found")

    annotation.content = payload.content
    await session.commit()
    await session.refresh(annotation)
    return annotation


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> None:
    """Delete an annotation."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation {annotation_id} not found")

    await session.delete(annotation)
    await session.commit()
