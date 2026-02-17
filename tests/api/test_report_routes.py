"""Tests for report API routes in src/api/routes/reports.py.

Tests all three report endpoints with JSON and HTML format support,
using the existing test fixture pattern from conftest.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Engagement Summary Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_engagement_summary_json(client):
    """Returns JSON with engagement, report_type, generated_at, data."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {
        "id": str(engagement_id),
        "name": "Test Engagement",
        "client": "ACME Corp",
        "business_area": "Finance",
        "status": "active",
    }
    mock_report.report_type = "engagement_summary"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {
        "evidence_count": 42,
        "coverage_percentage": 75.0,
        "covered_categories": 9,
        "total_categories": 12,
    }

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_engagement_summary = AsyncMock(return_value=mock_report)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "engagement_summary"
    assert data["engagement"]["name"] == "Test Engagement"
    assert data["data"]["evidence_count"] == 42
    assert data["generated_at"] == "2024-01-01T00:00:00Z"


@pytest.mark.asyncio
async def test_get_engagement_summary_html(client):
    """format=html returns HTMLResponse with content-type text/html."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {
        "id": str(engagement_id),
        "name": "Test Engagement",
        "client": "ACME Corp",
    }
    mock_report.report_type = "engagement_summary"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {"evidence_count": 10}

    html_content = "<html><body><h1>Engagement Summary</h1></body></html>"

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_engagement_summary = AsyncMock(return_value=mock_report)
        instance.render_html = MagicMock(return_value=html_content)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/summary?format=html")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "Engagement Summary" in resp.text


# =============================================================================
# Gap Report Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_gap_report_json(client):
    """Returns gap analysis JSON."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {
        "id": str(engagement_id),
        "name": "Test Engagement",
        "client": "ACME Corp",
    }
    mock_report.report_type = "gap_analysis"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {
        "total_gaps": 5,
        "critical_gaps": 2,
        "gaps": [
            {
                "id": str(uuid.uuid4()),
                "dimension": "process",
                "gap_type": "missing_step",
                "severity": 0.8,
                "confidence": 0.9,
                "priority_score": 0.85,
                "rationale": "Missing approval step",
                "recommendation": "Add approval workflow",
            },
        ],
    }

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_gap_report = AsyncMock(return_value=mock_report)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/gap-analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "gap_analysis"
    assert data["data"]["total_gaps"] == 5
    assert data["data"]["critical_gaps"] == 2


@pytest.mark.asyncio
async def test_get_gap_report_with_tom_id(client):
    """Passes tom_id to engine when provided."""
    engagement_id = uuid.uuid4()
    tom_id = uuid.uuid4()

    mock_report = MagicMock()
    mock_report.engagement = {"id": str(engagement_id), "name": "Test", "client": "Client"}
    mock_report.report_type = "gap_analysis"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {"total_gaps": 2, "critical_gaps": 1, "gaps": []}

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_gap_report = AsyncMock(return_value=mock_report)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/gap-analysis?tom_id={tom_id}")

    assert resp.status_code == 200
    # Verify generate_gap_report was called with tom_id
    instance.generate_gap_report.assert_called_once()
    call_args = instance.generate_gap_report.call_args
    # Arguments: (session, engagement_id_str, tom_id_str)
    assert call_args[0][1] == str(engagement_id)
    assert call_args[0][2] == str(tom_id)


@pytest.mark.asyncio
async def test_get_gap_report_html(client):
    """format=html returns HTML."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {"id": str(engagement_id), "name": "Test", "client": "Client"}
    mock_report.report_type = "gap_analysis"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {"total_gaps": 0, "critical_gaps": 0, "gaps": []}

    html_content = "<html><body><h1>Gap Analysis</h1><table></table></body></html>"

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_gap_report = AsyncMock(return_value=mock_report)
        instance.render_html = MagicMock(return_value=html_content)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/gap-analysis?format=html")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "Gap Analysis" in resp.text
    assert "<table>" in resp.text


# =============================================================================
# Governance Report Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_governance_report_json(client):
    """Returns governance JSON."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {
        "id": str(engagement_id),
        "name": "Test Engagement",
        "client": "ACME Corp",
    }
    mock_report.report_type = "governance_overlay"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {
        "policy_count": 8,
        "control_count": 15,
        "regulation_count": 4,
        "avg_control_effectiveness": 0.82,
        "policies": [
            {"id": str(uuid.uuid4()), "name": "Policy 1", "type": "organizational"},
        ],
        "regulations": [
            {"id": str(uuid.uuid4()), "name": "SOX", "framework": "Sarbanes-Oxley"},
        ],
    }

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_governance_report = AsyncMock(return_value=mock_report)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/governance")

    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "governance_overlay"
    assert data["data"]["policy_count"] == 8
    assert data["data"]["control_count"] == 15
    assert data["data"]["regulation_count"] == 4
    assert data["data"]["avg_control_effectiveness"] == 0.82


@pytest.mark.asyncio
async def test_get_governance_report_html(client):
    """format=html returns HTML."""
    engagement_id = uuid.uuid4()
    mock_report = MagicMock()
    mock_report.engagement = {"id": str(engagement_id), "name": "Test", "client": "Client"}
    mock_report.report_type = "governance_overlay"
    mock_report.generated_at = "2024-01-01T00:00:00Z"
    mock_report.data = {
        "policy_count": 3,
        "control_count": 7,
        "regulation_count": 2,
        "avg_control_effectiveness": 0.75,
        "policies": [],
        "regulations": [],
    }

    html_content = (
        "<html><body>"
        "<h1>Governance Overlay</h1>"
        "<div>3 Policies | 7 Controls | 2 Regulations</div>"
        "</body></html>"
    )

    with patch("src.api.routes.reports.ReportEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate_governance_report = AsyncMock(return_value=mock_report)
        instance.render_html = MagicMock(return_value=html_content)

        resp = await client.get(f"/api/v1/reports/{engagement_id}/governance?format=html")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "Governance Overlay" in resp.text
    assert "Policies" in resp.text
    assert "Controls" in resp.text
    assert "Regulations" in resp.text
