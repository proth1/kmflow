"""Executive Report Generation Engine.

Generates HTML reports using Jinja2 templates for engagement summaries,
gap analysis, and governance overlay reporting.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    Control,
    Engagement,
    EvidenceCategory,
    EvidenceItem,
    GapAnalysisResult,
    Policy,
    Regulation,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ReportData:
    """Data container for report generation.

    Attributes:
        engagement: Engagement details.
        report_type: Type of report being generated.
        generated_at: Timestamp of generation.
        data: Report-specific data payload.
    """

    engagement: dict[str, Any] = field(default_factory=dict)
    report_type: str = ""
    generated_at: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _build_maturity_radar_svg(gaps: list[dict[str, Any]]) -> str:
    """Generate an inline SVG maturity radar chart from gap data.

    Plots average severity per dimension as a filled polygon on a
    hexagonal radar (one axis per TOM dimension).

    Args:
        gaps: List of gap dicts with 'dimension' and 'severity'.

    Returns:
        SVG markup string.
    """
    dimensions = [
        "process_architecture",
        "people_and_organization",
        "technology_and_data",
        "governance_structures",
        "performance_management",
        "risk_and_compliance",
    ]
    labels = [
        "Process",
        "People & Org",
        "Technology",
        "Governance",
        "Performance",
        "Risk",
    ]
    n = len(dimensions)

    # Aggregate avg severity per dimension (0-1 scale, invert: 1=no gap)
    dim_severity: dict[str, list[float]] = {d: [] for d in dimensions}
    for g in gaps:
        dim = g.get("dimension", "")
        if dim in dim_severity:
            dim_severity[dim].append(float(g.get("severity", 0)))

    # radius for each dimension: 1 - avg_severity (higher radius = better)
    radii = []
    for d in dimensions:
        sevs = dim_severity[d]
        avg_sev = sum(sevs) / len(sevs) if sevs else 0.0
        radii.append(max(0.1, 1.0 - avg_sev))

    cx, cy, max_r = 200, 200, 150
    angles = [2 * math.pi * i / n - math.pi / 2 for i in range(n)]

    def polar(r: float, angle: float) -> tuple[float, float]:
        return cx + r * max_r * math.cos(angle), cy + r * max_r * math.sin(angle)

    # Build grid circles
    grid_circles = ""
    for level in [0.25, 0.5, 0.75, 1.0]:
        pts = " ".join(f"{polar(level, a)[0]:.1f},{polar(level, a)[1]:.1f}" for a in angles)
        grid_circles += f'<polygon points="{pts}" fill="none" stroke="#ddd" stroke-width="1"/>\n'

    # Build axes
    axes = ""
    for angle in angles:
        x, y = polar(1.0, angle)
        axes += f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#ccc" stroke-width="1"/>\n'

    # Build data polygon
    data_pts = " ".join(f"{polar(r, a)[0]:.1f},{polar(r, a)[1]:.1f}" for r, a in zip(radii, angles, strict=True))
    data_polygon = f'<polygon points="{data_pts}" fill="rgba(41,128,185,0.3)" stroke="#2980b9" stroke-width="2"/>\n'

    # Labels
    label_markup = ""
    for label, angle in zip(labels, angles, strict=True):
        lx, ly = polar(1.2, angle)
        label_markup += (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="11" fill="#555">{label}</text>\n'
        )

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">\n'
        f"{grid_circles}{axes}{data_polygon}{label_markup}"
        "</svg>"
    )
    return svg


class ReportEngine:
    """Engine for generating executive reports."""

    def _get_jinja_env(self) -> Any:
        """Return a Jinja2 Environment pointing at the templates directory."""
        try:
            from jinja2 import Environment, FileSystemLoader

            return Environment(
                loader=FileSystemLoader(str(_TEMPLATES_DIR)),
                autoescape=True,
            )
        except ImportError:
            return None

    async def generate_engagement_summary(
        self,
        session: AsyncSession,
        engagement_id: str,
    ) -> ReportData:
        """Generate an engagement summary report.

        Includes: engagement details, evidence coverage, key metrics.

        Args:
            session: Database session.
            engagement_id: The engagement to report on.

        Returns:
            ReportData with summary information.
        """
        # Fetch engagement
        eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
        engagement = eng_result.scalar_one_or_none()
        if not engagement:
            return ReportData(report_type="engagement_summary", data={"error": "Engagement not found"})

        # Count evidence
        count_result = await session.execute(
            select(func.count()).select_from(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id)
        )
        evidence_count = count_result.scalar() or 0

        # Count by category
        cat_query = (
            select(EvidenceItem.category, func.count().label("count"))
            .where(EvidenceItem.engagement_id == engagement_id)
            .group_by(EvidenceItem.category)
        )
        cat_result = await session.execute(cat_query)
        evidence_by_category = {str(row.category): row.count for row in cat_result}

        total_categories = len(EvidenceCategory)
        covered = len(evidence_by_category)
        coverage_pct = round(covered / total_categories * 100, 2) if total_categories > 0 else 0

        return ReportData(
            engagement={
                "id": str(engagement.id),
                "name": engagement.name,
                "client": engagement.client,
                "business_area": engagement.business_area,
                "status": str(engagement.status),
            },
            report_type="engagement_summary",
            generated_at=datetime.now(UTC).isoformat(),
            data={
                "evidence_count": evidence_count,
                "evidence_by_category": evidence_by_category,
                "coverage_percentage": coverage_pct,
                "total_categories": total_categories,
                "covered_categories": covered,
            },
        )

    async def generate_gap_report(
        self,
        session: AsyncSession,
        engagement_id: str,
        tom_id: str | None = None,
    ) -> ReportData:
        """Generate a gap analysis report.

        Includes: prioritized gaps, recommendations, maturity assessment.

        Args:
            session: Database session.
            engagement_id: The engagement to report on.
            tom_id: Optional specific TOM to report on.

        Returns:
            ReportData with gap analysis details.
        """
        eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
        engagement = eng_result.scalar_one_or_none()
        if not engagement:
            return ReportData(report_type="gap_analysis", data={"error": "Engagement not found"})

        # Fetch gaps
        gap_query = select(GapAnalysisResult).where(GapAnalysisResult.engagement_id == engagement_id)
        if tom_id:
            gap_query = gap_query.where(GapAnalysisResult.tom_id == tom_id)
        gap_result = await session.execute(gap_query)
        gaps = list(gap_result.scalars().all())

        gap_data = []
        for gap in gaps:
            gap_data.append(
                {
                    "id": str(gap.id),
                    "dimension": str(gap.dimension),
                    "gap_type": str(gap.gap_type),
                    "severity": gap.severity,
                    "confidence": gap.confidence,
                    "priority_score": gap.priority_score,
                    "rationale": gap.rationale,
                    "recommendation": gap.recommendation,
                }
            )

        # Sort by priority
        gap_data.sort(key=lambda x: float(x.get("priority_score", 0) or 0), reverse=True)  # type: ignore[arg-type]

        return ReportData(
            engagement={
                "id": str(engagement.id),
                "name": engagement.name,
                "client": engagement.client,
            },
            report_type="gap_analysis",
            generated_at=datetime.now(UTC).isoformat(),
            data={
                "gaps": gap_data,
                "total_gaps": len(gap_data),
                "critical_gaps": len([g for g in gap_data if float(g.get("severity", 0) or 0) > 0.7]),  # type: ignore[arg-type]
            },
        )

    async def generate_governance_report(
        self,
        session: AsyncSession,
        engagement_id: str,
    ) -> ReportData:
        """Generate a governance overlay report.

        Includes: policy coverage, control effectiveness, regulatory mapping.

        Args:
            session: Database session.
            engagement_id: The engagement to report on.

        Returns:
            ReportData with governance details.
        """
        eng_result = await session.execute(select(Engagement).where(Engagement.id == engagement_id))
        engagement = eng_result.scalar_one_or_none()
        if not engagement:
            return ReportData(report_type="governance_overlay", data={"error": "Engagement not found"})

        # Fetch policies
        policy_result = await session.execute(select(Policy).where(Policy.engagement_id == engagement_id))
        policies = list(policy_result.scalars().all())

        # Fetch controls
        control_result = await session.execute(select(Control).where(Control.engagement_id == engagement_id))
        controls = list(control_result.scalars().all())

        # Fetch regulations
        reg_result = await session.execute(select(Regulation).where(Regulation.engagement_id == engagement_id))
        regulations = list(reg_result.scalars().all())

        # Calculate control effectiveness summary
        effectiveness_scores = [c.effectiveness_score for c in controls if c.effectiveness_score > 0]
        avg_effectiveness = (
            round(sum(effectiveness_scores) / len(effectiveness_scores), 2) if effectiveness_scores else 0
        )

        return ReportData(
            engagement={
                "id": str(engagement.id),
                "name": engagement.name,
                "client": engagement.client,
            },
            report_type="governance_overlay",
            generated_at=datetime.now(UTC).isoformat(),
            data={
                "policy_count": len(policies),
                "control_count": len(controls),
                "regulation_count": len(regulations),
                "avg_control_effectiveness": avg_effectiveness,
                "policies": [{"id": str(p.id), "name": p.name, "type": str(p.policy_type)} for p in policies],
                "regulations": [{"id": str(r.id), "name": r.name, "framework": r.framework} for r in regulations],
            },
        )

    def render_html(self, report_data: ReportData) -> str:
        """Render report data to HTML using Jinja2 templates.

        Falls back to inline HTML if Jinja2 is not available or template
        file is missing.

        Args:
            report_data: The report data to render.

        Returns:
            HTML string.
        """
        env = self._get_jinja_env()

        template_map = {
            "engagement_summary": "executive_summary.html",
            "gap_analysis": "gap_report.html",
            "governance_overlay": "governance_report.html",
        }

        template_name = template_map.get(report_data.report_type)
        if env is not None and template_name:
            try:
                template = env.get_template(template_name)
                context: dict[str, Any] = {
                    "engagement": report_data.engagement,
                    "report_type": report_data.report_type,
                    "generated_at": report_data.generated_at,
                    "data": report_data.data,
                }
                if report_data.report_type == "gap_analysis":
                    context["maturity_radar_svg"] = _build_maturity_radar_svg(report_data.data.get("gaps", []))
                return template.render(**context)
            except Exception as e:
                logger.warning("Jinja2 template rendering failed, falling back: %s", e)

        # Fallback to inline HTML
        return self._render_html_fallback(report_data)

    def _render_html_fallback(self, report_data: ReportData) -> str:
        """Inline HTML fallback when Jinja2 is unavailable."""
        title = report_data.report_type.replace("_", " ").title()
        engagement = report_data.engagement

        html_parts = [
            "<!DOCTYPE html>",
            "<html><head>",
            f"<title>{title} - {engagement.get('name', 'Unknown')}</title>",
            "<style>body{font-family:Arial,sans-serif;margin:40px;}"
            "table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ddd;padding:8px;text-align:left}"
            "th{background:#f5f5f5}"
            ".metric{font-size:2em;font-weight:bold;color:#333}"
            ".critical{color:#e74c3c}.warning{color:#f39c12}.good{color:#27ae60}"
            "</style>",
            "</head><body>",
            f"<h1>{title}</h1>",
            f"<p>Engagement: <strong>{engagement.get('name', '')}</strong> "
            f"| Client: {engagement.get('client', '')} "
            f"| Generated: {report_data.generated_at}</p>",
            "<hr>",
        ]

        data = report_data.data
        if report_data.report_type == "engagement_summary":
            html_parts.append(f"<div class='metric'>{data.get('evidence_count', 0)} Evidence Items</div>")
            html_parts.append(
                f"<p>Coverage: {data.get('coverage_percentage', 0)}% "
                f"({data.get('covered_categories', 0)}/{data.get('total_categories', 0)} categories)</p>"
            )
        elif report_data.report_type == "gap_analysis":
            html_parts.append(f"<div class='metric'>{data.get('total_gaps', 0)} Gaps Identified</div>")
            html_parts.append(f"<p class='critical'>{data.get('critical_gaps', 0)} Critical</p>")
            html_parts.append(
                "<table><tr><th>Dimension</th><th>Type</th><th>Severity</th><th>Priority</th><th>Recommendation</th></tr>"
            )
            for gap in data.get("gaps", []):
                sev_class = "critical" if gap["severity"] > 0.7 else "warning" if gap["severity"] > 0.4 else "good"
                html_parts.append(
                    f"<tr><td>{gap['dimension']}</td><td>{gap['gap_type']}</td>"
                    f"<td class='{sev_class}'>{gap['severity']:.2f}</td>"
                    f"<td>{gap['priority_score']:.3f}</td>"
                    f"<td>{gap.get('recommendation', '')}</td></tr>"
                )
            html_parts.append("</table>")
        elif report_data.report_type == "governance_overlay":
            html_parts.append(
                f"<div class='metric'>{data.get('policy_count', 0)} Policies | "
                f"{data.get('control_count', 0)} Controls | "
                f"{data.get('regulation_count', 0)} Regulations</div>"
            )
            html_parts.append(f"<p>Avg Control Effectiveness: {data.get('avg_control_effectiveness', 0):.0%}</p>")

        html_parts.extend(["</body></html>"])
        return "\n".join(html_parts)
