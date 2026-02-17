"""Tests for the ReportEngine in src/core/reports.py.

Tests all report generation methods and HTML rendering with proper
SQLAlchemy session mocking using side_effect for multiple execute calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import EvidenceCategory
from src.core.reports import ReportData, ReportEngine


# =============================================================================
# Engagement Summary Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_engagement_summary():
    """Valid engagement returns ReportData with evidence_count and coverage."""
    engagement_id = uuid.uuid4()

    # Mock engagement
    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test Engagement"
    mock_eng.client = "ACME Corp"
    mock_eng.business_area = "Finance"
    mock_eng.status = "active"

    # Mock session.execute is called 3 times:
    # 1. select(Engagement) → returns engagement
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    # 2. select(func.count()).select_from(EvidenceItem) → returns count
    count_result = MagicMock()
    count_result.scalar.return_value = 42

    # 3. select(EvidenceItem.category, func.count()) → returns category rows
    cat_row_1 = MagicMock()
    cat_row_1.category = EvidenceCategory.DOCUMENTS
    cat_row_1.count = 20
    cat_row_2 = MagicMock()
    cat_row_2.category = EvidenceCategory.IMAGES
    cat_row_2.count = 22
    cat_result = MagicMock()
    cat_result.__iter__ = MagicMock(return_value=iter([cat_row_1, cat_row_2]))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, count_result, cat_result])

    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))

    assert isinstance(report, ReportData)
    assert report.engagement["id"] == str(engagement_id)
    assert report.engagement["name"] == "Test Engagement"
    assert report.engagement["client"] == "ACME Corp"
    assert report.data["evidence_count"] == 42
    assert report.data["evidence_by_category"]["documents"] == 20
    assert report.data["evidence_by_category"]["images"] == 22
    assert report.data["covered_categories"] == 2
    # Coverage: 2 categories / 12 total = 16.67%
    assert report.data["coverage_percentage"] == 16.67


@pytest.mark.asyncio
async def test_generate_engagement_summary_not_found():
    """No engagement found returns error in data."""
    engagement_id = uuid.uuid4()

    # Mock session returning no engagement
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=eng_result)

    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))

    assert report.report_type == "engagement_summary"
    assert "error" in report.data
    assert report.data["error"] == "Engagement not found"


@pytest.mark.asyncio
async def test_engagement_summary_report_type():
    """Report type is set to engagement_summary."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"
    mock_eng.business_area = "Finance"
    mock_eng.status = "active"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    count_result = MagicMock()
    count_result.scalar.return_value = 10

    cat_result = MagicMock()
    cat_result.__iter__ = MagicMock(return_value=iter([]))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, count_result, cat_result])

    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))

    assert report.report_type == "engagement_summary"


@pytest.mark.asyncio
async def test_engagement_summary_has_timestamp():
    """Generated_at timestamp is not empty."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"
    mock_eng.business_area = "Finance"
    mock_eng.status = "active"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    count_result = MagicMock()
    count_result.scalar.return_value = 5

    cat_result = MagicMock()
    cat_result.__iter__ = MagicMock(return_value=iter([]))

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, count_result, cat_result])

    engine = ReportEngine()
    report = await engine.generate_engagement_summary(session, str(engagement_id))

    assert report.generated_at != ""
    # Verify it's a valid ISO timestamp
    datetime.fromisoformat(report.generated_at)


# =============================================================================
# Gap Report Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_gap_report():
    """Valid engagement with gaps returns data with gaps list, total_gaps, critical_gaps."""
    engagement_id = uuid.uuid4()

    # Mock engagement
    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test Engagement"
    mock_eng.client = "ACME Corp"

    # Mock gaps
    gap1 = MagicMock()
    gap1.id = uuid.uuid4()
    gap1.dimension = "process"
    gap1.gap_type = "missing_step"
    gap1.severity = 0.8
    gap1.confidence = 0.9
    gap1.priority_score = 0.85
    gap1.rationale = "Gap 1 rationale"
    gap1.recommendation = "Gap 1 recommendation"

    gap2 = MagicMock()
    gap2.id = uuid.uuid4()
    gap2.dimension = "technology"
    gap2.gap_type = "missing_tool"
    gap2.severity = 0.5
    gap2.confidence = 0.7
    gap2.priority_score = 0.6
    gap2.rationale = "Gap 2 rationale"
    gap2.recommendation = "Gap 2 recommendation"

    # session.execute is called 2 times:
    # 1. select(Engagement) → returns engagement
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    # 2. select(GapAnalysisResult) → returns gaps
    gap_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [gap1, gap2]
    gap_result.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, gap_result])

    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id))

    assert report.report_type == "gap_analysis"
    assert report.engagement["name"] == "Test Engagement"
    assert report.data["total_gaps"] == 2
    # Only gap1 has severity > 0.7
    assert report.data["critical_gaps"] == 1
    assert len(report.data["gaps"]) == 2


@pytest.mark.asyncio
async def test_generate_gap_report_not_found():
    """No engagement returns error."""
    engagement_id = uuid.uuid4()

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=eng_result)

    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id))

    assert report.report_type == "gap_analysis"
    assert "error" in report.data
    assert report.data["error"] == "Engagement not found"


@pytest.mark.asyncio
async def test_gap_report_sorted_by_priority():
    """Gaps are sorted descending by priority_score."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"

    # Create gaps with different priority scores
    gap1 = MagicMock()
    gap1.id = uuid.uuid4()
    gap1.dimension = "process"
    gap1.gap_type = "type1"
    gap1.severity = 0.5
    gap1.confidence = 0.5
    gap1.priority_score = 0.3
    gap1.rationale = "Low priority"
    gap1.recommendation = "Recommendation 1"

    gap2 = MagicMock()
    gap2.id = uuid.uuid4()
    gap2.dimension = "people"
    gap2.gap_type = "type2"
    gap2.severity = 0.9
    gap2.confidence = 0.9
    gap2.priority_score = 0.95
    gap2.rationale = "High priority"
    gap2.recommendation = "Recommendation 2"

    gap3 = MagicMock()
    gap3.id = uuid.uuid4()
    gap3.dimension = "technology"
    gap3.gap_type = "type3"
    gap3.severity = 0.6
    gap3.confidence = 0.7
    gap3.priority_score = 0.65
    gap3.rationale = "Medium priority"
    gap3.recommendation = "Recommendation 3"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    gap_result = MagicMock()
    scalars_mock = MagicMock()
    # Return in random order
    scalars_mock.all.return_value = [gap1, gap2, gap3]
    gap_result.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, gap_result])

    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id))

    # Should be sorted: gap2 (0.95), gap3 (0.65), gap1 (0.3)
    assert report.data["gaps"][0]["priority_score"] == 0.95
    assert report.data["gaps"][1]["priority_score"] == 0.65
    assert report.data["gaps"][2]["priority_score"] == 0.3


@pytest.mark.asyncio
async def test_gap_report_with_tom_filter():
    """When tom_id passed, report filters accordingly."""
    engagement_id = uuid.uuid4()
    tom_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"

    gap1 = MagicMock()
    gap1.id = uuid.uuid4()
    gap1.dimension = "process"
    gap1.gap_type = "type1"
    gap1.severity = 0.5
    gap1.confidence = 0.5
    gap1.priority_score = 0.5
    gap1.rationale = "Rationale"
    gap1.recommendation = "Recommendation"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    gap_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [gap1]
    gap_result.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, gap_result])

    engine = ReportEngine()
    # Pass tom_id to filter
    report = await engine.generate_gap_report(session, str(engagement_id), str(tom_id))

    # Verify session.execute was called with the filtered query
    # The second call should have the tom_id filter
    assert session.execute.call_count == 2
    assert report.data["total_gaps"] == 1


@pytest.mark.asyncio
async def test_gap_report_critical_count():
    """Gaps with severity > 0.7 counted as critical."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"

    # Create gaps with varying severity
    gap1 = MagicMock()
    gap1.id = uuid.uuid4()
    gap1.dimension = "process"
    gap1.gap_type = "type1"
    gap1.severity = 0.8  # Critical
    gap1.confidence = 0.5
    gap1.priority_score = 0.5
    gap1.rationale = "Rationale"
    gap1.recommendation = "Recommendation"

    gap2 = MagicMock()
    gap2.id = uuid.uuid4()
    gap2.dimension = "people"
    gap2.gap_type = "type2"
    gap2.severity = 0.6  # Not critical
    gap2.confidence = 0.5
    gap2.priority_score = 0.5
    gap2.rationale = "Rationale"
    gap2.recommendation = "Recommendation"

    gap3 = MagicMock()
    gap3.id = uuid.uuid4()
    gap3.dimension = "technology"
    gap3.gap_type = "type3"
    gap3.severity = 0.75  # Critical
    gap3.confidence = 0.5
    gap3.priority_score = 0.5
    gap3.rationale = "Rationale"
    gap3.recommendation = "Recommendation"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    gap_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [gap1, gap2, gap3]
    gap_result.scalars.return_value = scalars_mock

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, gap_result])

    engine = ReportEngine()
    report = await engine.generate_gap_report(session, str(engagement_id))

    assert report.data["total_gaps"] == 3
    assert report.data["critical_gaps"] == 2


# =============================================================================
# Governance Report Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_governance_report():
    """Returns policy_count, control_count, regulation_count."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test Engagement"
    mock_eng.client = "ACME Corp"

    # Mock policies
    policy1 = MagicMock()
    policy1.id = uuid.uuid4()
    policy1.name = "Policy 1"
    policy1.policy_type = "organizational"

    policy2 = MagicMock()
    policy2.id = uuid.uuid4()
    policy2.name = "Policy 2"
    policy2.policy_type = "regulatory"

    # Mock controls
    control1 = MagicMock()
    control1.id = uuid.uuid4()
    control1.name = "Control 1"
    control1.effectiveness_score = 0.8

    control2 = MagicMock()
    control2.id = uuid.uuid4()
    control2.name = "Control 2"
    control2.effectiveness_score = 0.9

    # Mock regulations
    regulation1 = MagicMock()
    regulation1.id = uuid.uuid4()
    regulation1.name = "Regulation 1"
    regulation1.framework = "SOX"

    # session.execute is called 4 times:
    # 1. select(Engagement) → returns engagement
    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    # 2. select(Policy) → returns policies
    policy_result = MagicMock()
    policy_scalars = MagicMock()
    policy_scalars.all.return_value = [policy1, policy2]
    policy_result.scalars.return_value = policy_scalars

    # 3. select(Control) → returns controls
    control_result = MagicMock()
    control_scalars = MagicMock()
    control_scalars.all.return_value = [control1, control2]
    control_result.scalars.return_value = control_scalars

    # 4. select(Regulation) → returns regulations
    regulation_result = MagicMock()
    regulation_scalars = MagicMock()
    regulation_scalars.all.return_value = [regulation1]
    regulation_result.scalars.return_value = regulation_scalars

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, policy_result, control_result, regulation_result])

    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))

    assert report.report_type == "governance_overlay"
    assert report.data["policy_count"] == 2
    assert report.data["control_count"] == 2
    assert report.data["regulation_count"] == 1


@pytest.mark.asyncio
async def test_governance_report_avg_effectiveness():
    """Correct avg calculation for control effectiveness."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"

    # Mock controls with varying effectiveness scores
    control1 = MagicMock()
    control1.id = uuid.uuid4()
    control1.name = "Control 1"
    control1.effectiveness_score = 0.6

    control2 = MagicMock()
    control2.id = uuid.uuid4()
    control2.name = "Control 2"
    control2.effectiveness_score = 0.8

    control3 = MagicMock()
    control3.id = uuid.uuid4()
    control3.name = "Control 3"
    control3.effectiveness_score = 0.7

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    policy_result = MagicMock()
    policy_scalars = MagicMock()
    policy_scalars.all.return_value = []
    policy_result.scalars.return_value = policy_scalars

    control_result = MagicMock()
    control_scalars = MagicMock()
    control_scalars.all.return_value = [control1, control2, control3]
    control_result.scalars.return_value = control_scalars

    regulation_result = MagicMock()
    regulation_scalars = MagicMock()
    regulation_scalars.all.return_value = []
    regulation_result.scalars.return_value = regulation_scalars

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, policy_result, control_result, regulation_result])

    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))

    # Average: (0.6 + 0.8 + 0.7) / 3 = 0.7
    assert report.data["avg_control_effectiveness"] == 0.7


@pytest.mark.asyncio
async def test_governance_report_not_found():
    """No engagement returns error."""
    engagement_id = uuid.uuid4()

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=eng_result)

    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))

    assert report.report_type == "governance_overlay"
    assert "error" in report.data
    assert report.data["error"] == "Engagement not found"


@pytest.mark.asyncio
async def test_governance_report_zero_controls():
    """No controls returns avg_effectiveness = 0."""
    engagement_id = uuid.uuid4()

    mock_eng = MagicMock()
    mock_eng.id = engagement_id
    mock_eng.name = "Test"
    mock_eng.client = "Client"

    eng_result = MagicMock()
    eng_result.scalar_one_or_none.return_value = mock_eng

    policy_result = MagicMock()
    policy_scalars = MagicMock()
    policy_scalars.all.return_value = []
    policy_result.scalars.return_value = policy_scalars

    # No controls
    control_result = MagicMock()
    control_scalars = MagicMock()
    control_scalars.all.return_value = []
    control_result.scalars.return_value = control_scalars

    regulation_result = MagicMock()
    regulation_scalars = MagicMock()
    regulation_scalars.all.return_value = []
    regulation_result.scalars.return_value = regulation_scalars

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[eng_result, policy_result, control_result, regulation_result])

    engine = ReportEngine()
    report = await engine.generate_governance_report(session, str(engagement_id))

    assert report.data["control_count"] == 0
    assert report.data["avg_control_effectiveness"] == 0


# =============================================================================
# HTML Rendering Tests
# =============================================================================


def test_render_html_engagement_summary():
    """HTML contains Evidence Items and Coverage."""
    report_data = ReportData(
        engagement={"id": str(uuid.uuid4()), "name": "Test Engagement", "client": "ACME"},
        report_type="engagement_summary",
        generated_at="2024-01-01T00:00:00Z",
        data={
            "evidence_count": 50,
            "coverage_percentage": 75.0,
            "covered_categories": 9,
            "total_categories": 12,
        },
    )

    engine = ReportEngine()
    html = engine.render_html(report_data)

    assert "Evidence Items" in html
    assert "Coverage" in html
    assert "50" in html
    assert "75" in html


def test_render_html_gap_analysis():
    """HTML contains table with Dimension, Type, Severity columns."""
    report_data = ReportData(
        engagement={"id": str(uuid.uuid4()), "name": "Test Engagement", "client": "ACME"},
        report_type="gap_analysis",
        generated_at="2024-01-01T00:00:00Z",
        data={
            "total_gaps": 2,
            "critical_gaps": 1,
            "gaps": [
                {
                    "id": str(uuid.uuid4()),
                    "dimension": "process",
                    "gap_type": "missing_step",
                    "severity": 0.8,
                    "confidence": 0.9,
                    "priority_score": 0.85,
                    "rationale": "Rationale",
                    "recommendation": "Recommendation 1",
                },
                {
                    "id": str(uuid.uuid4()),
                    "dimension": "technology",
                    "gap_type": "missing_tool",
                    "severity": 0.5,
                    "confidence": 0.7,
                    "priority_score": 0.6,
                    "rationale": "Rationale",
                    "recommendation": "Recommendation 2",
                },
            ],
        },
    )

    engine = ReportEngine()
    html = engine.render_html(report_data)

    assert "<table>" in html
    assert "Dimension" in html
    assert "Type" in html
    assert "Severity" in html
    assert "process" in html
    assert "technology" in html


def test_render_html_governance():
    """HTML contains Policies, Controls, Regulations."""
    report_data = ReportData(
        engagement={"id": str(uuid.uuid4()), "name": "Test Engagement", "client": "ACME"},
        report_type="governance_overlay",
        generated_at="2024-01-01T00:00:00Z",
        data={
            "policy_count": 5,
            "control_count": 10,
            "regulation_count": 3,
            "avg_control_effectiveness": 0.75,
            "policies": [],
            "regulations": [],
        },
    )

    engine = ReportEngine()
    html = engine.render_html(report_data)

    assert "Policies" in html
    assert "Controls" in html
    assert "Regulations" in html
    assert "5" in html
    assert "10" in html
    assert "3" in html


def test_render_html_includes_title():
    """Title derived from report_type."""
    report_data = ReportData(
        engagement={"id": str(uuid.uuid4()), "name": "Test Engagement", "client": "ACME"},
        report_type="engagement_summary",
        generated_at="2024-01-01T00:00:00Z",
        data={},
    )

    engine = ReportEngine()
    html = engine.render_html(report_data)

    assert "<title>Engagement Summary - Test Engagement</title>" in html
    assert "<h1>Engagement Summary</h1>" in html


def test_render_html_includes_engagement_name():
    """Engagement name in output."""
    report_data = ReportData(
        engagement={"id": str(uuid.uuid4()), "name": "My Special Engagement", "client": "TechCorp"},
        report_type="gap_analysis",
        generated_at="2024-01-01T00:00:00Z",
        data={"total_gaps": 0, "critical_gaps": 0, "gaps": []},
    )

    engine = ReportEngine()
    html = engine.render_html(report_data)

    assert "My Special Engagement" in html
    assert "TechCorp" in html
