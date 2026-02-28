"""Executive report generation routes.

Provides endpoints for generating engagement summaries, gap analysis,
and governance overlay reports in HTML format. Also provides async
report generation with status tracking and download.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import ReportFormat, ReportStatus, User
from src.core.permissions import require_engagement_access, require_permission
from src.core.reports import ReportEngine
from src.core.services.report_generation import ReportGenerationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

# Job TTL in Redis: 24 hours
_REPORT_JOB_TTL = 86400


# -- Schemas ------------------------------------------------------------------


class ReportGenerateRequest(BaseModel):
    """Request body for triggering async report generation."""

    format: str = Field(default="html", pattern="^(html|pdf)$")
    tom_id: str | None = None
    sections: list[str] | None = None


class ReportStatusResponse(BaseModel):
    """Response for report generation status polling."""

    report_id: str
    engagement_id: str
    status: str
    format: str
    progress_percentage: int = 0
    error: str | None = None
    download_url: str | None = None


class ReportTriggerResponse(BaseModel):
    """Response when a report generation job is triggered."""

    report_id: str
    engagement_id: str
    status: str = ReportStatus.PENDING
    status_url: str
    message: str = "Report generation started"


# -- Redis job helpers --------------------------------------------------------


async def _set_report_job(request: Request, report_id: str, data: dict[str, Any]) -> None:
    """Store a report job record in Redis."""
    try:
        redis_client = request.app.state.redis_client
        await redis_client.setex(f"report:job:{report_id}", _REPORT_JOB_TTL, json.dumps(data))
    except aioredis.RedisError:
        logger.warning("Redis unavailable for report job store, job %s status may be lost", report_id)


async def _get_report_job(request: Request, report_id: str) -> dict[str, Any] | None:
    """Retrieve a report job record from Redis."""
    try:
        redis_client = request.app.state.redis_client
        raw = await redis_client.get(f"report:job:{report_id}")
        if raw:
            return json.loads(raw)
    except aioredis.RedisError:
        logger.warning("Redis unavailable for report job lookup")
    return None


# -- Existing synchronous routes ----------------------------------------------


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


# -- Async report generation endpoints ---------------------------------------


@router.post(
    "/engagements/{engagement_id}/generate",
    response_model=ReportTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_report_generation(
    engagement_id: UUID,
    body: ReportGenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Trigger async generation of a complete executive report.

    Returns a report_id for status polling and eventual download.

    Args:
        engagement_id: The engagement to generate a report for.
        body: Report generation options (format, tom_id, sections).
    """
    report_id = uuid.uuid4().hex

    # Store initial job state
    await _set_report_job(
        request,
        report_id,
        {
            "status": ReportStatus.PENDING,
            "engagement_id": str(engagement_id),
            "format": body.format,
            "progress_percentage": 0,
            "requested_by": str(user.id),
        },
    )

    # Generate the report (runs inline for now; production would use Celery)
    service = ReportGenerationService()

    await _set_report_job(
        request,
        report_id,
        {
            "status": ReportStatus.GENERATING,
            "engagement_id": str(engagement_id),
            "format": body.format,
            "progress_percentage": 10,
            "requested_by": str(user.id),
        },
    )

    try:
        result = await service.generate(
            session,
            str(engagement_id),
            report_format=body.format,
            tom_id=body.tom_id,
        )

        if result.error:
            await _set_report_job(
                request,
                report_id,
                {
                    "status": ReportStatus.FAILED,
                    "engagement_id": str(engagement_id),
                    "format": body.format,
                    "progress_percentage": 0,
                    "error": result.error,
                    "requested_by": str(user.id),
                },
            )
        else:
            # Store the generated content
            job_data: dict[str, Any] = {
                "status": ReportStatus.COMPLETE,
                "engagement_id": str(engagement_id),
                "format": body.format,
                "progress_percentage": 100,
                "requested_by": str(user.id),
                "html_content": result.html_content,
                "citation_count": len(result.citations),
                "section_count": len(result.sections),
            }
            if body.format == ReportFormat.PDF and result.pdf_bytes:
                # Store PDF as base64 for Redis (production would use S3)
                job_data["pdf_base64"] = base64.b64encode(result.pdf_bytes).decode()
            await _set_report_job(request, report_id, job_data)

    except Exception as e:
        logger.error("Report generation failed for %s: %s", engagement_id, e)
        await _set_report_job(
            request,
            report_id,
            {
                "status": ReportStatus.FAILED,
                "engagement_id": str(engagement_id),
                "format": body.format,
                "progress_percentage": 0,
                "error": "Report generation failed. Please try again or contact support.",
                "requested_by": str(user.id),
            },
        )

    status_url = f"/api/v1/reports/engagements/{engagement_id}/status/{report_id}"
    return {
        "report_id": report_id,
        "engagement_id": str(engagement_id),
        "status": ReportStatus.PENDING,
        "status_url": status_url,
        "message": "Report generation started",
    }


@router.get(
    "/engagements/{engagement_id}/status/{report_id}",
    response_model=ReportStatusResponse,
)
async def get_report_status(
    engagement_id: UUID,
    report_id: str,
    request: Request,
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Poll the status of an async report generation job.

    Args:
        engagement_id: The engagement the report belongs to.
        report_id: The report job ID returned from POST /generate.
    """
    job = await _get_report_job(request, report_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report job {report_id} not found",
        )

    # Verify engagement_id matches
    if job.get("engagement_id") != str(engagement_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report job {report_id} not found for engagement {engagement_id}",
        )

    download_url = None
    if job.get("status") == ReportStatus.COMPLETE:
        download_url = (
            f"/api/v1/reports/engagements/{engagement_id}/download/{report_id}?format={job.get('format', 'html')}"
        )

    return {
        "report_id": report_id,
        "engagement_id": str(engagement_id),
        "status": job.get("status", "unknown"),
        "format": job.get("format", "html"),
        "progress_percentage": job.get("progress_percentage", 0),
        "error": job.get("error"),
        "download_url": download_url,
    }


@router.get("/engagements/{engagement_id}/download/{report_id}")
async def download_report(
    engagement_id: UUID,
    report_id: str,
    output_format: str = Query(default="html", alias="format", pattern="^(html|pdf)$"),
    request: Request = None,  # FastAPI injects automatically
    user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> Any:
    """Download a completed report.

    Args:
        engagement_id: The engagement the report belongs to.
        report_id: The report job ID.
        output_format: Download format (html or pdf).
    """
    job = await _get_report_job(request, report_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report job {report_id} not found",
        )

    if job.get("engagement_id") != str(engagement_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report job {report_id} not found for engagement {engagement_id}",
        )

    if job.get("status") != ReportStatus.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is not complete (status: {job.get('status')})",
        )

    if output_format == "pdf":
        pdf_b64 = job.get("pdf_base64")
        if not pdf_b64:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF content not available for this report",
            )
        pdf_bytes = base64.b64decode(pdf_b64)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report-{engagement_id}.pdf"'},
        )

    # Default: return HTML
    html_content = job.get("html_content", "")
    if not html_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HTML content not available for this report",
        )
    return HTMLResponse(content=html_content)


# -- Existing synchronous report routes --------------------------------------


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
