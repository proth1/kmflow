"""Async executive report generation service.

Assembles engagement reports with executive summary, process model section,
gap analysis findings, recommendations, and evidence appendix with in-text
citations. Outputs HTML (self-contained) or PDF (via WeasyPrint).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    Engagement,
    EvidenceItem,
    ProcessModel,
    ReportFormat,
)
from src.core.reports import ReportEngine, _build_maturity_radar_svg

logger = logging.getLogger(__name__)


@dataclass
class CitedEvidence:
    """An evidence item cited in the report body."""

    citation_key: str
    title: str
    category: str
    grade: str
    date: str
    source: str
    evidence_id: str


@dataclass
class ReportSection:
    """A section of the generated report."""

    title: str
    content_html: str
    order: int = 0


@dataclass
class GeneratedReport:
    """Complete generated report with all sections and evidence appendix."""

    engagement_id: str
    engagement_name: str
    client: str
    format: str
    sections: list[ReportSection] = field(default_factory=list)
    citations: list[CitedEvidence] = field(default_factory=list)
    generated_at: str = ""
    html_content: str = ""
    pdf_bytes: bytes = b""
    error: str | None = None


class ReportGenerationService:
    """Service for generating executive reports asynchronously."""

    def __init__(self) -> None:
        self._engine = ReportEngine()

    async def generate(
        self,
        session: AsyncSession,
        engagement_id: str,
        report_format: str = ReportFormat.HTML,
        tom_id: str | None = None,
    ) -> GeneratedReport:
        """Generate a complete executive report for an engagement.

        Assembles all report sections: executive summary, process model,
        gap analysis, recommendations, and evidence appendix.

        Args:
            session: Database session.
            engagement_id: The engagement to report on.
            report_format: Output format (html or pdf).
            tom_id: Optional TOM filter for gap analysis.

        Returns:
            GeneratedReport with all content populated.
        """
        report = GeneratedReport(
            engagement_id=engagement_id,
            engagement_name="",
            client="",
            format=report_format,
            generated_at=datetime.now(UTC).isoformat(),
        )

        # Fetch engagement
        try:
            eng_uuid = uuid.UUID(engagement_id)
        except ValueError:
            report.error = f"Invalid engagement ID: {engagement_id}"
            return report

        eng_result = await session.execute(select(Engagement).where(Engagement.id == eng_uuid))
        engagement = eng_result.scalar_one_or_none()
        if not engagement:
            report.error = "Engagement not found"
            return report

        report.engagement_name = engagement.name
        report.client = engagement.client

        # Build sections
        sections = []
        citations: list[CitedEvidence] = []

        # 1. Executive Summary section
        summary_data = await self._engine.generate_engagement_summary(session, engagement_id)
        sections.append(
            ReportSection(
                title="Executive Summary",
                content_html=self._render_executive_summary(summary_data.data),
                order=1,
            )
        )

        # 2. Process Model section
        process_section = await self._build_process_model_section(session, eng_uuid)
        sections.append(
            ReportSection(
                title="Process Model",
                content_html=process_section,
                order=2,
            )
        )

        # 3. Gap Analysis Findings
        gap_data = await self._engine.generate_gap_report(session, engagement_id, tom_id)
        gap_html, gap_citations = await self._build_gap_section_with_citations(session, eng_uuid, gap_data.data)
        sections.append(
            ReportSection(
                title="Gap Analysis Findings",
                content_html=gap_html,
                order=3,
            )
        )
        citations.extend(gap_citations)

        # 4. Recommendations section
        sections.append(
            ReportSection(
                title="Recommendations",
                content_html=self._build_recommendations(gap_data.data),
                order=4,
            )
        )

        # 5. Evidence Appendix
        sections.append(
            ReportSection(
                title="Evidence Appendix",
                content_html=self._build_evidence_appendix(citations),
                order=5,
            )
        )

        report.sections = sections
        report.citations = citations

        # Render final HTML
        report.html_content = self._render_full_report(report)

        # Convert to PDF if requested
        if report_format == ReportFormat.PDF:
            report.pdf_bytes = self._render_pdf(report.html_content)

        return report

    def _render_executive_summary(self, data: dict[str, Any]) -> str:
        """Render executive summary section HTML."""
        evidence_count = data.get("evidence_count", 0)
        coverage = data.get("coverage_percentage", 0)
        covered = data.get("covered_categories", 0)
        total = data.get("total_categories", 0)

        return (
            f"<div class='summary-metrics'>"
            f"<div class='metric-card'><span class='metric-value'>{evidence_count}</span>"
            f"<span class='metric-label'>Evidence Items Analyzed</span></div>"
            f"<div class='metric-card'><span class='metric-value'>{coverage}%</span>"
            f"<span class='metric-label'>Category Coverage ({covered}/{total})</span></div>"
            f"</div>"
        )

    async def _build_process_model_section(self, session: AsyncSession, engagement_id: uuid.UUID) -> str:
        """Build process model section with confidence overlay."""
        result = await session.execute(
            select(ProcessModel)
            .where(ProcessModel.engagement_id == engagement_id)
            .order_by(ProcessModel.version.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()

        if not model:
            return "<p>No process model available for this engagement.</p>"

        confidence_class = (
            "high" if model.confidence_score >= 0.8 else "medium" if model.confidence_score >= 0.5 else "low"
        )

        html = (
            f"<div class='process-model'>"
            f"<p>Version {model.version} | "
            f"Confidence: <span class='confidence-{confidence_class}'>"
            f"{model.confidence_score:.0%}</span> | "
            f"Elements: {model.element_count}</p>"
        )

        if model.bpmn_xml:
            html += "<div class='bpmn-viewer' data-bpmn='embedded'><p><em>Process diagram embedded below</em></p></div>"

        html += "</div>"
        return html

    async def _build_gap_section_with_citations(
        self,
        session: AsyncSession,
        engagement_id: uuid.UUID,
        gap_data: dict[str, Any],
    ) -> tuple[str, list[CitedEvidence]]:
        """Build gap analysis section with evidence citations.

        Returns:
            Tuple of (html_content, list of cited evidence items).
        """
        gaps = gap_data.get("gaps", [])
        citations: list[CitedEvidence] = []
        citation_counter = 1

        # Fetch evidence items for citation linking
        evidence_result = await session.execute(select(EvidenceItem).where(EvidenceItem.engagement_id == engagement_id))
        evidence_items = {str(e.id): e for e in evidence_result.scalars().all()}

        # Build maturity radar
        radar_svg = _build_maturity_radar_svg(gaps)

        html_parts = [
            f"<div class='gap-summary'>"
            f"<p><strong>{gap_data.get('total_gaps', 0)}</strong> gaps identified, "
            f"<strong class='critical'>{gap_data.get('critical_gaps', 0)}</strong> critical</p>"
            f"</div>",
            f"<div class='maturity-radar'>{radar_svg}</div>",
            "<table class='gap-table'>"
            "<thead><tr><th>Dimension</th><th>Type</th><th>Severity</th>"
            "<th>Recommendation</th><th>Evidence</th></tr></thead><tbody>",
        ]

        for gap in gaps:
            # Create citation for each gap that has evidence
            gap_id = gap.get("id", "")
            citation_refs = []

            # Link gap to evidence items (using gap_id to find related evidence)
            if gap_id and gap_id in evidence_items:
                ev = evidence_items[gap_id]
                citation_key = f"E{citation_counter}"
                citations.append(
                    CitedEvidence(
                        citation_key=citation_key,
                        title=ev.title if hasattr(ev, "title") else str(ev.id),
                        category=str(ev.category) if hasattr(ev, "category") else "",
                        grade=str(ev.grade) if hasattr(ev, "grade") else "N/A",
                        date=str(ev.created_at) if hasattr(ev, "created_at") else "",
                        source=str(ev.source) if hasattr(ev, "source") else "",
                        evidence_id=str(ev.id),
                    )
                )
                citation_refs.append(f"<a href='#evidence-{citation_key}' class='citation'>[{citation_key}]</a>")
                citation_counter += 1

            sev = float(gap.get("severity", 0) or 0)
            sev_class = "critical" if sev > 0.7 else "warning" if sev > 0.4 else "good"
            citation_html = " ".join(citation_refs) if citation_refs else "—"

            html_parts.append(
                f"<tr><td>{gap.get('dimension', '')}</td>"
                f"<td>{gap.get('gap_type', '')}</td>"
                f"<td class='{sev_class}'>{sev:.2f}</td>"
                f"<td>{gap.get('recommendation', '')}</td>"
                f"<td>{citation_html}</td></tr>"
            )

        html_parts.append("</tbody></table>")
        return "\n".join(html_parts), citations

    def _build_recommendations(self, gap_data: dict[str, Any]) -> str:
        """Build prioritized recommendations section."""
        gaps = gap_data.get("gaps", [])
        if not gaps:
            return "<p>No gaps identified — no recommendations at this time.</p>"

        html_parts = ["<ol class='recommendations'>"]
        for gap in gaps:
            rec = gap.get("recommendation", "")
            if rec:
                priority = float(gap.get("priority_score", 0) or 0)
                priority_label = "High" if priority > 0.7 else "Medium" if priority > 0.4 else "Low"
                html_parts.append(
                    f"<li><strong>[{priority_label}]</strong> {rec} "
                    f"<em>(Dimension: {gap.get('dimension', '')})</em></li>"
                )
        html_parts.append("</ol>")
        return "\n".join(html_parts)

    def _build_evidence_appendix(self, citations: list[CitedEvidence]) -> str:
        """Build evidence appendix with anchored entries."""
        if not citations:
            return "<p>No evidence items cited in this report.</p>"

        html_parts = [
            "<table class='evidence-appendix'>"
            "<thead><tr><th>Ref</th><th>Title</th><th>Category</th>"
            "<th>Grade</th><th>Date</th><th>Source</th></tr></thead><tbody>"
        ]

        for cite in citations:
            html_parts.append(
                f"<tr id='evidence-{cite.citation_key}'>"
                f"<td><strong>{cite.citation_key}</strong></td>"
                f"<td>{cite.title}</td>"
                f"<td>{cite.category}</td>"
                f"<td>{cite.grade}</td>"
                f"<td>{cite.date}</td>"
                f"<td>{cite.source}</td></tr>"
            )

        html_parts.append("</tbody></table>")
        return "\n".join(html_parts)

    def _render_full_report(self, report: GeneratedReport) -> str:
        """Render the full report as a self-contained HTML document."""
        sections_html = ""
        for section in sorted(report.sections, key=lambda s: s.order):
            sections_html += (
                f"<section class='report-section'><h2>{section.title}</h2>{section.content_html}</section>\n"
            )

        return (
            "<!DOCTYPE html>\n<html lang='en'><head>\n"
            f"<title>Executive Report — {report.engagement_name}</title>\n"
            "<meta charset='utf-8'>\n"
            "<style>\n"
            "body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#333;line-height:1.6}"
            "h1{color:#1a237e;border-bottom:3px solid #1a237e;padding-bottom:10px}"
            "h2{color:#283593;margin-top:30px}"
            "table{border-collapse:collapse;width:100%;margin:15px 0}"
            "th,td{border:1px solid #ddd;padding:10px;text-align:left}"
            "th{background:#f5f5f5;font-weight:600}"
            ".metric-card{display:inline-block;margin:10px 20px 10px 0;padding:15px;"
            "background:#f8f9fa;border-left:4px solid #1a237e;min-width:150px}"
            ".metric-value{font-size:2em;font-weight:bold;display:block;color:#1a237e}"
            ".metric-label{font-size:0.85em;color:#666}"
            ".critical{color:#e74c3c;font-weight:bold}"
            ".warning{color:#f39c12}.good{color:#27ae60}"
            ".confidence-high{color:#27ae60;font-weight:bold}"
            ".confidence-medium{color:#f39c12;font-weight:bold}"
            ".confidence-low{color:#e74c3c;font-weight:bold}"
            ".citation{color:#1565c0;text-decoration:none;font-weight:600}"
            ".citation:hover{text-decoration:underline}"
            ".recommendations li{margin-bottom:8px}"
            ".report-section{margin-bottom:30px}"
            ".report-footer{margin-top:40px;padding-top:15px;border-top:2px solid #eee;"
            "color:#999;font-size:0.85em}"
            "@media print{body{margin:20px}.report-section{page-break-inside:avoid}}"
            "\n</style>\n</head><body>\n"
            f"<h1>Executive Report</h1>\n"
            f"<p><strong>Engagement:</strong> {report.engagement_name} | "
            f"<strong>Client:</strong> {report.client} | "
            f"<strong>Generated:</strong> {report.generated_at}</p>\n"
            f"<hr>\n{sections_html}\n"
            f"<div class='report-footer'>"
            f"<p>Generated by KMFlow Platform | {report.generated_at}</p>"
            f"</div>\n"
            "</body></html>"
        )

    def _render_pdf(self, html_content: str) -> bytes:
        """Convert HTML report to PDF using WeasyPrint.

        Returns empty bytes if WeasyPrint is not available.
        """
        try:
            from weasyprint import HTML

            return HTML(string=html_content).write_pdf()
        except ImportError:
            logger.warning("WeasyPrint not installed, PDF generation unavailable")
            return b""
        except Exception as e:
            logger.error("PDF generation failed: %s", e)
            return b""
