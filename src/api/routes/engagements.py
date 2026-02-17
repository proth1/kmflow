"""Engagement management routes.

Provides CRUD operations for consulting engagements.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import Engagement, EngagementStatus

router = APIRouter(prefix="/api/v1/engagements", tags=["engagements"])


# ── Request/Response Schemas ────────────────────────────────────


class EngagementCreate(BaseModel):
    """Schema for creating an engagement."""

    name: str = Field(..., min_length=1, max_length=255)
    client: str = Field(..., min_length=1, max_length=255)
    business_area: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class EngagementResponse(BaseModel):
    """Schema for engagement responses."""

    model_config = {"from_attributes": True}

    id: UUID
    name: str
    client: str
    business_area: str
    description: str | None
    status: EngagementStatus


class EngagementList(BaseModel):
    """Schema for listing engagements."""

    items: list[EngagementResponse]
    total: int


# ── Dependency ──────────────────────────────────────────────────


async def get_session(request: Any) -> AsyncSession:  # noqa: ANN401
    """Get database session from app state.

    This is a simplified dependency. In a full implementation,
    this would be injected via FastAPI's dependency injection system.
    """
    from starlette.requests import Request

    req: Request = request
    session_factory = req.app.state.db_session_factory
    async with session_factory() as session:
        yield session  # type: ignore[misc]


# ── Routes ──────────────────────────────────────────────────────


@router.post("/", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    payload: EngagementCreate,
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Create a new consulting engagement."""
    engagement = Engagement(
        name=payload.name,
        client=payload.client,
        business_area=payload.business_area,
        description=payload.description,
    )
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


@router.get("/", response_model=EngagementList)
async def list_engagements(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List engagements with pagination."""
    query = select(Engagement).offset(offset).limit(limit)
    result = await session.execute(query)
    engagements = list(result.scalars().all())

    count_query = select(__import__("sqlalchemy").func.count()).select_from(Engagement)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return {"items": engagements, "total": total}


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Engagement:
    """Get a specific engagement by ID."""
    result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Engagement {engagement_id} not found",
        )
    return engagement
