"""Cross-source consistency reporting routes.

Provides disagreement reports, consistency metrics with agreement rate,
and POV version trend tracking for conflict reduction over time.

Implements Story #392: Cross-Source Consistency Reporting.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models.conflict import ConflictObject, MismatchType, ResolutionStatus
from src.core.models.pov import ProcessModel, ProcessModelStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagements", tags=["consistency"])


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{engagement_id}/reports/disagreement
# ---------------------------------------------------------------------------


@router.get(
    "/{engagement_id}/reports/disagreement",
    summary="Disagreement report for an engagement",
)
async def disagreement_report(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    format: str = Query("json", description="Output format: json or pdf"),
) -> dict[str, Any]:
    """Return a disagreement report listing all ConflictObjects with full status.

    Each entry includes conflict_id, type, severity, resolution_status,
    resolution_type (if resolved), and linked source evidence IDs.
    Open vs resolved counts are summarized in a header section.
    """
    query = (
        select(ConflictObject)
        .where(ConflictObject.engagement_id == engagement_id)
        .order_by(ConflictObject.severity.desc(), ConflictObject.created_at.asc())
    )
    result = await session.execute(query)
    conflicts = result.scalars().all()

    # Build summary counts
    total = len(conflicts)
    open_count = sum(1 for c in conflicts if c.resolution_status == ResolutionStatus.UNRESOLVED)
    escalated_count = sum(1 for c in conflicts if c.resolution_status == ResolutionStatus.ESCALATED)
    resolved_count = sum(1 for c in conflicts if c.resolution_status == ResolutionStatus.RESOLVED)

    # Per-type breakdown
    type_breakdown: dict[str, int] = {}
    for c in conflicts:
        mtype = c.mismatch_type.value if isinstance(c.mismatch_type, MismatchType) else str(c.mismatch_type)
        type_breakdown[mtype] = type_breakdown.get(mtype, 0) + 1

    items = []
    for c in conflicts:
        items.append(
            {
                "conflict_id": str(c.id),
                "type": c.mismatch_type.value if isinstance(c.mismatch_type, MismatchType) else str(c.mismatch_type),
                "severity": c.severity,
                "resolution_status": c.resolution_status.value
                if isinstance(c.resolution_status, ResolutionStatus)
                else str(c.resolution_status),
                "resolution_type": c.resolution_type.value if c.resolution_type else None,
                "source_a_id": str(c.source_a_id) if c.source_a_id else None,
                "source_b_id": str(c.source_b_id) if c.source_b_id else None,
                "resolver_id": str(c.resolver_id) if c.resolver_id else None,
                "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
        )

    report = {
        "engagement_id": str(engagement_id),
        "summary": {
            "total_conflicts": total,
            "open_count": open_count,
            "escalated_count": escalated_count,
            "resolved_count": resolved_count,
            "type_breakdown": type_breakdown,
        },
        "conflicts": items,
    }

    if format == "pdf":
        # PDF generation via existing infrastructure
        try:
            from src.core.pdf_generator import html_to_pdf, is_pdf_available

            if not is_pdf_available():
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="PDF generation not available. Install weasyprint.",
                )

            html = _render_disagreement_html(report)
            from fastapi.responses import Response

            pdf_bytes = html_to_pdf(html)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="disagreement-report-{engagement_id}.pdf"'},
            )
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="PDF generation not available. Install weasyprint.",
            ) from exc

    return report


def _render_disagreement_html(report: dict[str, Any]) -> str:
    """Render a simple HTML disagreement report for PDF conversion."""
    summary = report["summary"]
    rows = ""
    for c in report["conflicts"]:
        rows += (
            f"<tr>"
            f"<td>{c['conflict_id'][:8]}...</td>"
            f"<td>{c['type']}</td>"
            f"<td>{c['severity']:.2f}</td>"
            f"<td>{c['resolution_status']}</td>"
            f"<td>{c['resolution_type'] or '-'}</td>"
            f"<td>{c['source_a_id'][:8] if c['source_a_id'] else '-'}...</td>"
            f"<td>{c['source_b_id'][:8] if c['source_b_id'] else '-'}...</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Disagreement Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2em; }}
h1 {{ color: #1a1a1a; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 0.9em; }}
th {{ background-color: #f4f4f4; }}
.summary {{ margin: 1em 0; padding: 1em; background: #f9f9f9; border-radius: 4px; }}
</style></head><body>
<h1>Cross-Source Disagreement Report</h1>
<p>Engagement: {report["engagement_id"]}</p>
<div class="summary">
<strong>Summary:</strong>
Total: {summary["total_conflicts"]} |
Open: {summary["open_count"]} |
Escalated: {summary["escalated_count"]} |
Resolved: {summary["resolved_count"]}
</div>
<table>
<thead><tr>
<th>ID</th><th>Type</th><th>Severity</th><th>Status</th>
<th>Resolution</th><th>Source A</th><th>Source B</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>"""


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{engagement_id}/consistency-metrics
# ---------------------------------------------------------------------------


@router.get(
    "/{engagement_id}/consistency-metrics",
    summary="Consistency metrics with agreement rate",
)
async def consistency_metrics(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return consistency metrics including agreement rate.

    Computes:
    - total_element_pairs: unique mapped process element pairs across sources
    - conflicting_pairs: pairs with ConflictObjects (open or resolved)
    - agreement_rate: (total - conflicting) / total * 100
    - resolved_conflict_rate: % of conflicts that are resolved
    - open_conflict_count: count of still-open conflicts
    """
    # Count total conflicts
    conflict_count_q = (
        select(func.count()).select_from(ConflictObject).where(ConflictObject.engagement_id == engagement_id)
    )
    conflict_result = await session.execute(conflict_count_q)
    conflicting_pairs = conflict_result.scalar() or 0

    # Count resolved
    resolved_count_q = (
        select(func.count())
        .select_from(ConflictObject)
        .where(
            ConflictObject.engagement_id == engagement_id,
            ConflictObject.resolution_status == ResolutionStatus.RESOLVED,
        )
    )
    resolved_result = await session.execute(resolved_count_q)
    resolved_count = resolved_result.scalar() or 0

    # Count open (unresolved + escalated)
    open_count_q = (
        select(func.count())
        .select_from(ConflictObject)
        .where(
            ConflictObject.engagement_id == engagement_id,
            ConflictObject.resolution_status.in_([ResolutionStatus.UNRESOLVED, ResolutionStatus.ESCALATED]),
        )
    )
    open_result = await session.execute(open_count_q)
    open_conflict_count = open_result.scalar() or 0

    # Estimate total element pairs: use element_count from latest ProcessModel
    # as a proxy for total mapped pairs (each element pair = potential conflict site)
    model_q = (
        select(ProcessModel)
        .where(
            ProcessModel.engagement_id == engagement_id,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.version.desc())
        .limit(1)
    )
    model_result = await session.execute(model_q)
    latest_model = model_result.scalar_one_or_none()

    # Total element pairs: use element_count as proxy, minimum = conflicting_pairs
    total_element_pairs = max(latest_model.element_count if latest_model else 0, conflicting_pairs)
    if total_element_pairs == 0:
        total_element_pairs = conflicting_pairs if conflicting_pairs > 0 else 1  # avoid division by zero

    agreement_rate = round(((total_element_pairs - conflicting_pairs) / total_element_pairs) * 100, 2)
    resolved_conflict_rate = round((resolved_count / conflicting_pairs * 100), 2) if conflicting_pairs > 0 else 100.0

    return {
        "engagement_id": str(engagement_id),
        "total_element_pairs": total_element_pairs,
        "conflicting_pairs": conflicting_pairs,
        "agreement_rate": agreement_rate,
        "resolved_conflict_rate": resolved_conflict_rate,
        "open_conflict_count": open_conflict_count,
        "resolved_count": resolved_count,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{engagement_id}/consistency-metrics/trend
# ---------------------------------------------------------------------------


@router.get(
    "/{engagement_id}/consistency-metrics/trend",
    summary="POV version trend with conflict reduction rate",
)
async def consistency_trend(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return conflict reduction trend across POV versions.

    Each entry includes: pov_version, pov_created_at, open_conflict_count,
    resolved_conflict_count, agreement_rate. Conflict reduction rate is
    computed between consecutive versions.
    """
    # Get all completed POV versions chronologically
    models_q = (
        select(ProcessModel)
        .where(
            ProcessModel.engagement_id == engagement_id,
            ProcessModel.status == ProcessModelStatus.COMPLETED,
        )
        .order_by(ProcessModel.version.asc())
    )
    models_result = await session.execute(models_q)
    models = models_result.scalars().all()

    if not models:
        return {
            "engagement_id": str(engagement_id),
            "trend": [],
            "conflict_reduction_rate": None,
        }

    trend: list[dict[str, Any]] = []
    for model in models:
        # Use conflict_snapshot from metadata if available (stored at POV generation)
        snapshot = (model.metadata_json or {}).get("conflict_snapshot") if model.metadata_json else None

        if snapshot:
            open_count = snapshot.get("open_count", 0)
            resolved_count = snapshot.get("resolved_count", 0)
            total_pairs = snapshot.get("total_element_pairs", model.element_count or 0)
        else:
            # Use contradiction_count as historical proxy for older POVs
            open_count = model.contradiction_count or 0
            resolved_count = 0
            total_pairs = model.element_count or 0

        total_for_rate = max(total_pairs, open_count + resolved_count, 1)
        agreement_rate = round(((total_for_rate - (open_count + resolved_count)) / total_for_rate) * 100, 2)

        trend.append(
            {
                "pov_version": model.version,
                "pov_created_at": model.generated_at.isoformat() if model.generated_at else None,
                "open_conflict_count": open_count,
                "resolved_conflict_count": resolved_count,
                "agreement_rate": agreement_rate,
            }
        )

    # Compute conflict reduction rate between last two versions
    conflict_reduction_rate = None
    if len(trend) >= 2:
        prev_open = trend[-2]["open_conflict_count"]
        curr_open = trend[-1]["open_conflict_count"]
        if prev_open > 0:
            conflict_reduction_rate = round(((prev_open - curr_open) / prev_open) * 100, 2)

    return {
        "engagement_id": str(engagement_id),
        "trend": trend,
        "conflict_reduction_rate": conflict_reduction_rate,
    }
