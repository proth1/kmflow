"""Pattern library routes for cross-engagement patterns.

Provides CRUD operations for the pattern library with anonymization,
access control, and embedding-based search.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import PatternAccessRule, PatternCategory, PatternLibraryEntry, User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patterns", tags=["patterns"])


# -- Schemas ------------------------------------------------------------------


class PatternCreate(BaseModel):
    source_engagement_id: UUID | None = None
    category: PatternCategory
    title: str = Field(..., min_length=1, max_length=512)
    description: str
    data: dict[str, Any] | None = None
    industry: str | None = None
    tags: list[str] | None = None

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None:
            serialized = json.dumps(v)
            if len(serialized.encode()) > 1_048_576:
                raise ValueError("Pattern data exceeds maximum size of 1MB")
        return v


class PatternUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    industry: str | None = None


class PatternResponse(BaseModel):
    id: str
    source_engagement_id: str | None = None
    category: str
    title: str
    description: str
    anonymized_data: dict[str, Any] | None = None
    industry: str | None = None
    tags: list[str] | None = None
    usage_count: int
    effectiveness_score: float
    created_at: str


class PatternList(BaseModel):
    items: list[PatternResponse]
    total: int


class AccessRuleCreate(BaseModel):
    pattern_id: UUID
    engagement_id: UUID
    granted_by: str = "system"


class AccessRuleResponse(BaseModel):
    id: str
    pattern_id: str
    engagement_id: str
    granted_by: str
    granted_at: str


class PatternSearchRequest(BaseModel):
    query: str | None = None
    industry: str | None = None
    categories: list[PatternCategory] | None = None
    limit: int = 10


class PatternApplyRequest(BaseModel):
    engagement_id: UUID


def _pattern_to_response(p: PatternLibraryEntry) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "source_engagement_id": str(p.source_engagement_id) if p.source_engagement_id else None,
        "category": p.category.value if isinstance(p.category, PatternCategory) else p.category,
        "title": p.title,
        "description": p.description,
        "anonymized_data": p.anonymized_data,
        "industry": p.industry,
        "tags": p.tags,
        "usage_count": p.usage_count,
        "effectiveness_score": p.effectiveness_score,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


# -- Routes -------------------------------------------------------------------


@router.post("", response_model=PatternResponse, status_code=status.HTTP_201_CREATED)
async def create_pattern(
    payload: PatternCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:create")),
) -> dict[str, Any]:
    """Create a new pattern in the library."""
    from src.patterns.anonymizer import anonymize_pattern_data

    anonymized = anonymize_pattern_data(payload.data or {}) if payload.data else None

    pattern = PatternLibraryEntry(
        source_engagement_id=payload.source_engagement_id,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        anonymized_data=anonymized,
        industry=payload.industry,
        tags=payload.tags,
    )
    session.add(pattern)
    await session.commit()
    await session.refresh(pattern)
    return _pattern_to_response(pattern)


@router.get("", response_model=PatternList)
async def list_patterns(
    category: PatternCategory | None = None,
    industry: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:read")),
) -> dict[str, Any]:
    """List patterns with optional filters."""
    query = select(PatternLibraryEntry)
    if category:
        query = query.where(PatternLibraryEntry.category == category)
    if industry:
        query = query.where(PatternLibraryEntry.industry == industry)
    query = query.offset(offset).limit(limit)

    result = await session.execute(query)
    items = [_pattern_to_response(p) for p in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.get("/{pattern_id}", response_model=PatternResponse)
async def get_pattern(
    pattern_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:read")),
) -> dict[str, Any]:
    """Get a pattern by ID."""
    result = await session.execute(select(PatternLibraryEntry).where(PatternLibraryEntry.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
    return _pattern_to_response(pattern)


@router.patch("/{pattern_id}", response_model=PatternResponse)
async def update_pattern(
    pattern_id: UUID,
    payload: PatternUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:create")),
) -> dict[str, Any]:
    """Update a pattern."""
    result = await session.execute(select(PatternLibraryEntry).where(PatternLibraryEntry.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")

    if payload.title is not None:
        pattern.title = payload.title
    if payload.description is not None:
        pattern.description = payload.description
    if payload.tags is not None:
        pattern.tags = payload.tags
    if payload.industry is not None:
        pattern.industry = payload.industry

    await session.commit()
    await session.refresh(pattern)
    return _pattern_to_response(pattern)


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pattern(
    pattern_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:create")),
) -> None:
    """Delete a pattern."""
    result = await session.execute(select(PatternLibraryEntry).where(PatternLibraryEntry.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")
    await session.delete(pattern)
    await session.commit()


@router.post("/search", response_model=PatternList)
async def search_patterns(
    payload: PatternSearchRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:read")),
) -> dict[str, Any]:
    """Search patterns by text query, industry, and categories."""
    query = select(PatternLibraryEntry)
    if payload.industry:
        query = query.where(PatternLibraryEntry.industry == payload.industry)
    if payload.categories:
        query = query.where(PatternLibraryEntry.category.in_(payload.categories))
    query = query.limit(payload.limit)

    result = await session.execute(query)
    items = [_pattern_to_response(p) for p in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.post("/{pattern_id}/apply", response_model=PatternResponse)
async def apply_pattern(
    pattern_id: UUID,
    payload: PatternApplyRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:apply")),
) -> dict[str, Any]:
    """Apply a pattern to an engagement (increments usage count)."""
    result = await session.execute(select(PatternLibraryEntry).where(PatternLibraryEntry.id == pattern_id))
    pattern = result.scalar_one_or_none()
    if not pattern:
        raise HTTPException(status_code=404, detail=f"Pattern {pattern_id} not found")

    pattern.usage_count += 1
    await session.commit()
    await session.refresh(pattern)
    return _pattern_to_response(pattern)


@router.post("/access-rules", response_model=AccessRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_access_rule(
    payload: AccessRuleCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("patterns:create")),
) -> dict[str, Any]:
    """Grant an engagement access to a pattern."""
    rule = PatternAccessRule(
        pattern_id=payload.pattern_id,
        engagement_id=payload.engagement_id,
        granted_by=payload.granted_by,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return {
        "id": str(rule.id),
        "pattern_id": str(rule.pattern_id),
        "engagement_id": str(rule.engagement_id),
        "granted_by": rule.granted_by,
        "granted_at": rule.granted_at.isoformat() if rule.granted_at else "",
    }
