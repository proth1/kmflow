"""Gap-targeted probe generation and retrieval routes.

Provides endpoints for generating and listing knowledge-gap-targeted
survey probes, prioritized by estimated confidence uplift.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import Engagement, User
from src.core.permissions import require_engagement_access, require_permission
from src.semantic.gap_probe_generator import GapProbeGenerator
from src.semantic.graph import KnowledgeGraphService

router = APIRouter(prefix="/api/v1/engagements", tags=["gap-probes"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GapProbeEntry(BaseModel):
    """A single gap-targeted probe."""

    id: str
    activity_id: str
    form_number: int
    form_name: str
    probe_type: str
    probe_text: str
    brightness: str
    estimated_uplift: float


class GapProbesResponse(BaseModel):
    """Response for gap probes listing."""

    engagement_id: UUID
    total_probes: int
    probes: list[GapProbeEntry]


class GenerateProbesResponse(BaseModel):
    """Response for probe generation."""

    engagement_id: UUID
    probes_generated: int
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{engagement_id}/gap-probes/generate",
    response_model=GenerateProbesResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_gap_probes(
    engagement_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Generate gap-targeted probes for an engagement.

    Analyzes knowledge form coverage gaps for Dim and Dark activities
    and generates prioritized survey probes.
    """
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    generator = GapProbeGenerator(graph_service)

    probes = await generator.generate_probes(str(engagement_id))

    return {
        "engagement_id": engagement_id,
        "probes_generated": len(probes),
        "message": f"Generated {len(probes)} gap-targeted probes",
    }


@router.get(
    "/{engagement_id}/gap-probes",
    response_model=GapProbesResponse,
)
async def list_gap_probes(
    engagement_id: UUID,
    request: Request,
    limit: int = Query(20, ge=1, le=200, description="Maximum probes to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """List gap-targeted probes for an engagement.

    Probes are sorted by estimated confidence uplift in descending order.
    Use limit/offset for pagination.
    """
    eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
    if not eng_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")

    graph_service = KnowledgeGraphService(request.app.state.neo4j_driver)
    generator = GapProbeGenerator(graph_service)

    all_probes = await generator.generate_probes(str(engagement_id))
    paginated = all_probes[offset: offset + limit]

    return {
        "engagement_id": engagement_id,
        "total_probes": len(all_probes),
        "probes": paginated,
    }
