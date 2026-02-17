"""Executive report generation routes.

Provides endpoints for generating engagement summaries, gap analysis,
and governance overlay reports in HTML format.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import User
from src.core.permissions import require_permission
from src.core.reports import ReportEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# -- Dependency ---------------------------------------------------------------


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


# -- Routes -------------------------------------------------------------------


@router.get("/{engagement_id}/summary")
async def get_engagement_summary(
    engagement_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Any:
    """Generate engagement summary report.

    Args:
        engagement_id: The engagement to report on.
        format: Response format ('json' or 'html').
    """
    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))

    if format == "html":
        html = engine.render_html(report)
        return HTMLResponse(content=html)

    return {
        "engagement": report.engagement,
        "report_type": report.report_type,
        "generated_at": report.generated_at,
        "data": report.data,
    }


@router.get("/{engagement_id}/gap-analysis")
async def get_gap_report(
    engagement_id: UUID,
    tom_id: UUID | None = None,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Any:
    """Generate gap analysis report.

    Args:
        engagement_id: The engagement to report on.
        tom_id: Optional specific TOM to filter by.
        format: Response format ('json' or 'html').
    """
    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id), str(tom_id) if tom_id else None)

    if format == "html":
        html = engine.render_html(report)
        return HTMLResponse(content=html)

    return {
        "engagement": report.engagement,
        "report_type": report.report_type,
        "generated_at": report.generated_at,
        "data": report.data,
    }


@router.get("/{engagement_id}/governance")
async def get_governance_report(
    engagement_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
) -> Any:
    """Generate governance overlay report.

    Args:
        engagement_id: The engagement to report on.
        format: Response format ('json' or 'html').
    """
    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))

    if format == "html":
        html = engine.render_html(report)
        return HTMLResponse(content=html)

    return {
        "engagement": report.engagement,
        "report_type": report.report_type,
        "generated_at": report.generated_at,
        "data": report.data,
    }
