"""Executive Report Generation Engine.

Generates HTML reports using Jinja2 templates for engagement summaries,
gap analysis, and governance overlay reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


class ReportEngine:
    """Engine for generating executive reports."""

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
            gap_data.append({
                "id": str(gap.id),
                "dimension": str(gap.dimension),
                "gap_type": str(gap.gap_type),
                "severity": gap.severity,
                "confidence": gap.confidence,
                "priority_score": gap.priority_score,
                "rationale": gap.rationale,
                "recommendation": gap.recommendation,
            })

        # Sort by priority
        gap_data.sort(key=lambda x: x["priority_score"], reverse=True)

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
                "critical_gaps": len([g for g in gap_data if g["severity"] > 0.7]),
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
        avg_effectiveness = round(sum(effectiveness_scores) / len(effectiveness_scores), 2) if effectiveness_scores else 0

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
        """Render report data to HTML.

        Uses simple HTML template rendering. In production, this would
        use Jinja2 templates from report_templates/.

        Args:
            report_data: The report data to render.

        Returns:
            HTML string.
        """
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
            html_parts.append(f"<p>Coverage: {data.get('coverage_percentage', 0)}% "
                            f"({data.get('covered_categories', 0)}/{data.get('total_categories', 0)} categories)</p>")
        elif report_data.report_type == "gap_analysis":
            html_parts.append(f"<div class='metric'>{data.get('total_gaps', 0)} Gaps Identified</div>")
            html_parts.append(f"<p class='critical'>{data.get('critical_gaps', 0)} Critical</p>")
            html_parts.append("<table><tr><th>Dimension</th><th>Type</th><th>Severity</th><th>Priority</th><th>Recommendation</th></tr>")
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
            html_parts.append(f"<div class='metric'>{data.get('policy_count', 0)} Policies | "
                            f"{data.get('control_count', 0)} Controls | "
                            f"{data.get('regulation_count', 0)} Regulations</div>")
            html_parts.append(f"<p>Avg Control Effectiveness: {data.get('avg_control_effectiveness', 0):.0%}</p>")

        html_parts.extend(["</body></html>"])
        return "\n".join(html_parts)
