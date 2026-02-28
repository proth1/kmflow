"""BDD tests for Executive Report Generation (Story #356).

Tests the async report generation endpoints: trigger, status polling,
download, and evidence appendix with in-text citations.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routes.reports import (
    ReportGenerateRequest,
    ReportStatusResponse,
    ReportTriggerResponse,
    _get_report_job,
    _set_report_job,
    download_report,
    get_report_status,
    trigger_report_generation,
)
from src.core.models import ReportStatus, UserRole
from src.core.services.report_generation import (
    CitedEvidence,
    GeneratedReport,
    ReportGenerationService,
    ReportSection,
)

# -- Fixtures ----------------------------------------------------------------


def _make_mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_mock_request(
    job_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock Request with a Redis client."""
    request = MagicMock()
    redis = AsyncMock()

    if job_data is not None:
        redis.get = AsyncMock(return_value=json.dumps(job_data))
    else:
        redis.get = AsyncMock(return_value=None)

    redis.setex = AsyncMock()
    request.app.state.redis_client = redis
    return request


def _make_mock_engagement(
    eng_id: uuid.UUID | None = None,
    name: str = "Test Engagement",
    client: str = "Test Client",
) -> MagicMock:
    """Create a mock Engagement."""
    eng = MagicMock()
    eng.id = eng_id or uuid.uuid4()
    eng.name = name
    eng.client = client
    eng.business_area = "IT"
    eng.status = "active"
    return eng


# ============================================================
# Scenario 1: Complete report generated from engagement data
# ============================================================


class TestReportGenerationTrigger:
    """Given an engagement with completed POV and gap analysis,
    POST /api/v1/reports/engagements/{id}/generate triggers async generation."""

    @pytest.mark.asyncio
    async def test_trigger_returns_report_id(self) -> None:
        """Triggering report generation returns a report_id."""
        eng_id = uuid.uuid4()
        request = _make_mock_request()
        session = AsyncMock()
        user = _make_mock_user()
        body = ReportGenerateRequest(format="html")

        with patch.object(
            ReportGenerationService,
            "generate",
            new_callable=AsyncMock,
            return_value=GeneratedReport(
                engagement_id=str(eng_id),
                engagement_name="Test",
                client="Client",
                format="html",
                html_content="<html>report</html>",
                sections=[ReportSection(title="Summary", content_html="<p>test</p>", order=1)],
            ),
        ):
            result = await trigger_report_generation(
                eng_id, body, request, session, user, user,
            )

        assert "report_id" in result
        assert result["engagement_id"] == str(eng_id)
        assert result["status_url"].startswith("/api/v1/reports/engagements/")

    @pytest.mark.asyncio
    async def test_trigger_stores_job_in_redis(self) -> None:
        """Report job is stored in Redis for status tracking."""
        eng_id = uuid.uuid4()
        request = _make_mock_request()
        session = AsyncMock()
        user = _make_mock_user()
        body = ReportGenerateRequest(format="html")

        with patch.object(
            ReportGenerationService,
            "generate",
            new_callable=AsyncMock,
            return_value=GeneratedReport(
                engagement_id=str(eng_id),
                engagement_name="Test",
                client="Client",
                format="html",
                html_content="<html>done</html>",
            ),
        ):
            await trigger_report_generation(
                eng_id, body, request, session, user, user,
            )

        # Verify Redis setex was called (at least 3 times: pending, generating, complete)
        redis = request.app.state.redis_client
        assert redis.setex.call_count >= 2

    @pytest.mark.asyncio
    async def test_trigger_with_pdf_format(self) -> None:
        """PDF format request is accepted and processed."""
        eng_id = uuid.uuid4()
        request = _make_mock_request()
        session = AsyncMock()
        user = _make_mock_user()
        body = ReportGenerateRequest(format="pdf")

        with patch.object(
            ReportGenerationService,
            "generate",
            new_callable=AsyncMock,
            return_value=GeneratedReport(
                engagement_id=str(eng_id),
                engagement_name="Test",
                client="Client",
                format="pdf",
                html_content="<html>report</html>",
                pdf_bytes=b"%PDF-fake",
            ),
        ):
            result = await trigger_report_generation(
                eng_id, body, request, session, user, user,
            )

        assert result["report_id"] is not None

    @pytest.mark.asyncio
    async def test_trigger_handles_generation_error(self) -> None:
        """Failed generation stores error in job data."""
        eng_id = uuid.uuid4()
        request = _make_mock_request()
        session = AsyncMock()
        user = _make_mock_user()
        body = ReportGenerateRequest(format="html")

        with patch.object(
            ReportGenerationService,
            "generate",
            new_callable=AsyncMock,
            return_value=GeneratedReport(
                engagement_id=str(eng_id),
                engagement_name="",
                client="",
                format="html",
                error="Engagement not found",
            ),
        ):
            await trigger_report_generation(
                eng_id, body, request, session, user, user,
            )

        # Last Redis call should contain FAILED status
        redis = request.app.state.redis_client
        last_call = redis.setex.call_args_list[-1]
        stored = json.loads(last_call[0][2])
        assert stored["status"] == ReportStatus.FAILED
        assert stored["error"] == "Engagement not found"

    @pytest.mark.asyncio
    async def test_trigger_handles_exception(self) -> None:
        """Unexpected exception during generation is handled gracefully."""
        eng_id = uuid.uuid4()
        request = _make_mock_request()
        session = AsyncMock()
        user = _make_mock_user()
        body = ReportGenerateRequest(format="html")

        with patch.object(
            ReportGenerationService,
            "generate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ):
            result = await trigger_report_generation(
                eng_id, body, request, session, user, user,
            )

        # Should still return a response (not crash)
        assert result["report_id"] is not None

        # Error should be stored in Redis
        redis = request.app.state.redis_client
        last_call = redis.setex.call_args_list[-1]
        stored = json.loads(last_call[0][2])
        assert stored["status"] == ReportStatus.FAILED
        assert "try again" in stored["error"]


# ============================================================
# Scenario 2 & 3: Status polling and download
# ============================================================


class TestReportStatusPolling:
    """GET /api/v1/reports/engagements/{id}/status/{report_id} returns job status."""

    @pytest.mark.asyncio
    async def test_status_returns_pending(self) -> None:
        """Pending job returns status=pending with 0% progress."""
        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.PENDING,
            "engagement_id": str(eng_id),
            "format": "html",
            "progress_percentage": 0,
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_report_status(eng_id, "report-123", request, user, user)

        assert result["status"] == "pending"
        assert result["progress_percentage"] == 0
        assert result["download_url"] is None

    @pytest.mark.asyncio
    async def test_status_returns_complete_with_download_url(self) -> None:
        """Completed job returns status=complete with download URL."""
        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.COMPLETE,
            "engagement_id": str(eng_id),
            "format": "html",
            "progress_percentage": 100,
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_report_status(eng_id, "report-456", request, user, user)

        assert result["status"] == "complete"
        assert result["progress_percentage"] == 100
        assert result["download_url"] is not None
        assert "download" in result["download_url"]

    @pytest.mark.asyncio
    async def test_status_not_found_raises_404(self) -> None:
        """Missing report job returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        request = _make_mock_request(None)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_report_status(eng_id, "nonexistent", request, user, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_status_wrong_engagement_raises_404(self) -> None:
        """Report job belonging to different engagement returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        other_eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.COMPLETE,
            "engagement_id": str(other_eng_id),
            "format": "html",
            "progress_percentage": 100,
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_report_status(eng_id, "report-789", request, user, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_status_shows_error_for_failed(self) -> None:
        """Failed job includes error message in status response."""
        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.FAILED,
            "engagement_id": str(eng_id),
            "format": "html",
            "progress_percentage": 0,
            "error": "Database timeout",
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await get_report_status(eng_id, "report-fail", request, user, user)

        assert result["status"] == "failed"
        assert result["error"] == "Database timeout"


class TestReportDownload:
    """GET /api/v1/reports/engagements/{id}/download/{report_id} returns report content."""

    @pytest.mark.asyncio
    async def test_download_html_report(self) -> None:
        """Completed HTML report is downloadable."""
        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.COMPLETE,
            "engagement_id": str(eng_id),
            "format": "html",
            "html_content": "<html><body>Executive Report</body></html>",
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await download_report(eng_id, "report-dl", "html", request, user, user)

        assert result.status_code == 200
        assert b"Executive Report" in result.body

    @pytest.mark.asyncio
    async def test_download_pdf_report(self) -> None:
        """Completed PDF report is downloadable."""
        import base64

        eng_id = uuid.uuid4()
        pdf_content = b"%PDF-1.4 fake pdf content"
        job_data = {
            "status": ReportStatus.COMPLETE,
            "engagement_id": str(eng_id),
            "format": "pdf",
            "pdf_base64": base64.b64encode(pdf_content).decode(),
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        result = await download_report(eng_id, "report-pdf", "pdf", request, user, user)

        assert result.status_code == 200
        assert result.body == pdf_content
        assert result.media_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_download_not_complete_raises_409(self) -> None:
        """Downloading an incomplete report returns 409 Conflict."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.GENERATING,
            "engagement_id": str(eng_id),
            "format": "html",
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await download_report(eng_id, "report-wip", "html", request, user, user)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_download_not_found_raises_404(self) -> None:
        """Missing report returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        request = _make_mock_request(None)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await download_report(eng_id, "nonexistent", "html", request, user, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_pdf_not_available_raises_404(self) -> None:
        """Requesting PDF when only HTML was generated returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        job_data = {
            "status": ReportStatus.COMPLETE,
            "engagement_id": str(eng_id),
            "format": "html",
            "html_content": "<html>report</html>",
        }
        request = _make_mock_request(job_data)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await download_report(eng_id, "report-nopdf", "pdf", request, user, user)

        assert exc_info.value.status_code == 404


# ============================================================
# Scenario 4: Evidence appendix with citations
# ============================================================


class TestEvidenceAppendixCitations:
    """Evidence appendix links findings to evidence with in-text citations."""

    def test_citation_key_format(self) -> None:
        """Citation keys follow E1, E2, ... format."""
        cite = CitedEvidence(
            citation_key="E1",
            title="Interview Notes",
            category="Documents",
            grade="A",
            date="2026-01-15",
            source="Client Upload",
            evidence_id=str(uuid.uuid4()),
        )
        assert cite.citation_key == "E1"

    def test_evidence_appendix_html_has_anchors(self) -> None:
        """Evidence appendix entries have anchor IDs for in-document linking."""
        service = ReportGenerationService()
        citations = [
            CitedEvidence(
                citation_key="E1",
                title="Process Map v1",
                category="BPM Process Models",
                grade="B",
                date="2026-01-20",
                source="Consultant",
                evidence_id=str(uuid.uuid4()),
            ),
            CitedEvidence(
                citation_key="E2",
                title="Staff Survey Results",
                category="Structured Data",
                grade="A",
                date="2026-01-22",
                source="Client HR",
                evidence_id=str(uuid.uuid4()),
            ),
        ]

        html = service._build_evidence_appendix(citations)

        assert 'id=\'evidence-E1\'' in html
        assert 'id=\'evidence-E2\'' in html
        assert "Process Map v1" in html
        assert "Staff Survey Results" in html
        assert "BPM Process Models" in html

    def test_empty_citations_shows_message(self) -> None:
        """No citations produces a helpful message."""
        service = ReportGenerationService()
        html = service._build_evidence_appendix([])
        assert "No evidence items cited" in html

    def test_full_report_html_is_self_contained(self) -> None:
        """Rendered HTML report is a complete, self-contained document."""
        service = ReportGenerationService()
        report = GeneratedReport(
            engagement_id=str(uuid.uuid4()),
            engagement_name="Loan Origination Review",
            client="Acme Bank",
            format="html",
            generated_at="2026-02-28T12:00:00Z",
            sections=[
                ReportSection(title="Executive Summary", content_html="<p>Summary</p>", order=1),
                ReportSection(title="Gap Analysis", content_html="<p>Gaps</p>", order=3),
                ReportSection(title="Evidence Appendix", content_html="<p>Evidence</p>", order=5),
            ],
        )

        html = service._render_full_report(report)

        assert "<!DOCTYPE html>" in html
        assert "<style>" in html
        assert "Loan Origination Review" in html
        assert "Acme Bank" in html
        assert "Executive Summary" in html
        assert "Gap Analysis" in html
        assert "Evidence Appendix" in html

    def test_sections_rendered_in_order(self) -> None:
        """Report sections are rendered in order field, not insertion order."""
        service = ReportGenerationService()
        report = GeneratedReport(
            engagement_id=str(uuid.uuid4()),
            engagement_name="Test",
            client="Client",
            format="html",
            sections=[
                ReportSection(title="Appendix", content_html="<p>Last</p>", order=5),
                ReportSection(title="Summary", content_html="<p>First</p>", order=1),
                ReportSection(title="Gaps", content_html="<p>Middle</p>", order=3),
            ],
        )

        html = service._render_full_report(report)

        # Summary should appear before Gaps which appears before Appendix
        summary_pos = html.index("Summary")
        gaps_pos = html.index("Gaps")
        appendix_pos = html.index("Appendix")
        assert summary_pos < gaps_pos < appendix_pos


# ============================================================
# Schema validation tests
# ============================================================


class TestReportSchemas:
    """Schema validation for report request/response models."""

    def test_generate_request_defaults(self) -> None:
        """ReportGenerateRequest has sensible defaults."""
        req = ReportGenerateRequest()
        assert req.format == "html"
        assert req.tom_id is None
        assert req.sections is None

    def test_generate_request_pdf(self) -> None:
        """PDF format is accepted."""
        req = ReportGenerateRequest(format="pdf")
        assert req.format == "pdf"

    def test_status_response_validates(self) -> None:
        """ReportStatusResponse can be constructed."""
        resp = ReportStatusResponse(
            report_id="abc",
            engagement_id="eng-1",
            status="complete",
            format="html",
            progress_percentage=100,
        )
        assert resp.status == "complete"
        assert resp.download_url is None

    def test_trigger_response_validates(self) -> None:
        """ReportTriggerResponse can be constructed."""
        resp = ReportTriggerResponse(
            report_id="xyz",
            engagement_id="eng-2",
            status_url="/api/v1/reports/engagements/eng-2/status/xyz",
        )
        assert resp.report_id == "xyz"
        assert resp.message == "Report generation started"


# ============================================================
# Redis job helpers
# ============================================================


class TestReportJobRedis:
    """Tests for report job Redis storage helpers."""

    @pytest.mark.asyncio
    async def test_set_and_get_job(self) -> None:
        """Job can be stored and retrieved from Redis."""
        request = _make_mock_request()
        await _set_report_job(request, "test-job", {"status": "pending"})

        # Verify setex was called
        redis = request.app.state.redis_client
        assert redis.setex.called

    @pytest.mark.asyncio
    async def test_get_missing_job_returns_none(self) -> None:
        """Missing job returns None."""
        request = _make_mock_request(None)
        result = await _get_report_job(request, "missing")
        assert result is None


# ============================================================
# Report generation service unit tests
# ============================================================


class TestReportGenerationService:
    """Unit tests for the ReportGenerationService."""

    def test_render_executive_summary_section(self) -> None:
        """Executive summary section renders metrics."""
        service = ReportGenerationService()
        html = service._render_executive_summary({
            "evidence_count": 42,
            "coverage_percentage": 75.5,
            "covered_categories": 9,
            "total_categories": 12,
        })

        assert "42" in html
        assert "75.5%" in html
        assert "9/12" in html

    def test_build_recommendations_with_gaps(self) -> None:
        """Recommendations section lists prioritized actions."""
        service = ReportGenerationService()
        html = service._build_recommendations({
            "gaps": [
                {
                    "recommendation": "Automate manual handoffs",
                    "priority_score": 0.85,
                    "dimension": "process_architecture",
                },
                {
                    "recommendation": "Add access controls",
                    "priority_score": 0.45,
                    "dimension": "governance_structures",
                },
            ],
        })

        assert "Automate manual handoffs" in html
        assert "[High]" in html
        assert "Add access controls" in html
        assert "[Medium]" in html

    def test_build_recommendations_empty(self) -> None:
        """Empty gaps produces no-recommendations message."""
        service = ReportGenerationService()
        html = service._build_recommendations({"gaps": []})
        assert "No gaps identified" in html

    @pytest.mark.asyncio
    async def test_generate_invalid_engagement_id(self) -> None:
        """Invalid engagement ID returns error in report."""
        service = ReportGenerationService()
        session = AsyncMock()

        result = await service.generate(session, "not-a-uuid")

        assert result.error is not None
        assert "Invalid engagement ID" in result.error

    @pytest.mark.asyncio
    async def test_generate_missing_engagement(self) -> None:
        """Missing engagement returns error."""
        service = ReportGenerationService()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        eng_id = str(uuid.uuid4())
        result = await service.generate(session, eng_id)

        assert result.error == "Engagement not found"

    def test_render_pdf_without_weasyprint(self) -> None:
        """PDF render returns empty bytes when WeasyPrint is not installed."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "weasyprint":
                raise ImportError("No module named 'weasyprint'")
            return real_import(name, *args, **kwargs)

        service = ReportGenerationService()
        with patch("builtins.__import__", side_effect=mock_import):
            result = service._render_pdf("<html>test</html>")
        # Should not raise; returns empty bytes
        assert isinstance(result, bytes)
