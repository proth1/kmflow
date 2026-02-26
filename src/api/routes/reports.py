"""Executive report generation routes.

Provides endpoints for generating engagement summaries, gap analysis,
and governance overlay reports in HTML format.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.permissions import require_engagement_access, require_permission
from src.core.reports import ReportEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# -- Routes -------------------------------------------------------------------


def _render_format(engine: ReportEngine, report: Any, fmt: str, filename: str) -> Any:
    """Render report in the requested format.

    Args:
        engine: ReportEngine instance.
        report: ReportData to render.
        fmt: Output format (json, html, pdf).
        filename: Suggested filename for PDF downloads.

    Returns:
        Appropriate FastAPI response.
    """
    if fmt == "html":
        html = engine.render_html(report)
        return HTMLResponse(content=html)

    if fmt == "pdf":
        from src.core.pdf_generator import html_to_pdf, is_pdf_available

        if not is_pdf_available():
            raise HTTPException(
                status_code=501,
                detail="PDF generation requires WeasyPrint. Install with: pip install weasyprint",
            )
        html = engine.render_html(report)
        pdf_bytes = html_to_pdf(html)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return {
        "engagement": report.engagement,
        "report_type": report.report_type,
        "generated_at": report.generated_at,
        "data": report.data,
    }


@router.get("/{engagement_id}/summary")
async def get_engagement_summary(
    engagement_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Any:
    """Generate engagement summary report.

    Args:
        engagement_id: The engagement to report on.
        format: Response format ('json', 'html', or 'pdf').
    """
    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))
    return _render_format(engine, report, format, f"summary-{engagement_id}.pdf")


@router.get("/{engagement_id}/gap-analysis")
async def get_gap_report(
    engagement_id: UUID,
    tom_id: UUID | None = None,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Any:
    """Generate gap analysis report.

    Args:
        engagement_id: The engagement to report on.
        tom_id: Optional specific TOM to filter by.
        format: Response format ('json', 'html', or 'pdf').
    """
    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id), str(tom_id) if tom_id else None)
    return _render_format(engine, report, format, f"gap-analysis-{engagement_id}.pdf")


@router.get("/{engagement_id}/governance")
async def get_governance_report(
    engagement_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Any:
    """Generate governance overlay report.

    Args:
        engagement_id: The engagement to report on.
        format: Response format ('json', 'html', or 'pdf').
    """
    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))
    return _render_format(engine, report, format, f"governance-{engagement_id}.pdf")


@router.get("/{engagement_id}/executive-summary")
async def get_executive_summary(
    engagement_id: UUID,
    tom_id: UUID | None = None,
    format: str = "html",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Any:
    """Generate a combined executive summary combining all 3 report types.

    Renders engagement summary, gap analysis, and governance overlay
    into a single HTML document.

    Args:
        engagement_id: The engagement to report on.
        tom_id: Optional specific TOM to filter gap analysis by.
        format: Response format ('json' or 'html').
    """
    engine = ReportEngine()

    summary = await engine.generate_engagement_summary(session, str(engagement_id))
    gaps = await engine.generate_gap_report(session, str(engagement_id), str(tom_id) if tom_id else None)
    governance = await engine.generate_governance_report(session, str(engagement_id))

    if format == "html":
        parts = [
            engine.render_html(summary),
            engine.render_html(gaps),
            engine.render_html(governance),
        ]
        combined = "\n<!-- SECTION BREAK -->\n".join(parts)
        return HTMLResponse(content=combined)

    return {
        "engagement_id": str(engagement_id),
        "report_type": "executive_summary",
        "sections": {
            "engagement_summary": {
                "engagement": summary.engagement,
                "generated_at": summary.generated_at,
                "data": summary.data,
            },
            "gap_analysis": {
                "engagement": gaps.engagement,
                "generated_at": gaps.generated_at,
                "data": gaps.data,
            },
            "governance_overlay": {
                "engagement": governance.engagement,
                "generated_at": governance.generated_at,
                "data": governance.data,
            },
        },
    }
