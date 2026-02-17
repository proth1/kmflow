"""Tests for Dashboard API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import (
    AuditAction,
    EngagementStatus,
    EvidenceCategory,
    GapSeverity,
    ProcessModelStatus,
)


@pytest.fixture
def mock_engagement():
    """Create a mock engagement."""
    eng = MagicMock()
    eng.id = uuid.uuid4()
    eng.name = "Test Engagement"
    eng.client = "Test Client"
    eng.business_area = "Finance"
    eng.status = EngagementStatus.ACTIVE
    return eng


@pytest.fixture
def engagement_id(mock_engagement):
    """Return the string engagement ID."""
    return str(mock_engagement.id)


class TestGetDashboard:
    """Tests for GET /api/v1/dashboard/{engagement_id}."""

    @pytest.mark.asyncio
    async def test_dashboard_returns_200(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns dashboard data when engagement exists."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Engagement lookup
                result.scalar_one_or_none.return_value = mock_engagement
            elif call_count == 2:
                # Evidence item count
                result.scalar.return_value = 15
            elif call_count == 3:
                # Process model count
                result.scalar.return_value = 2
            elif call_count == 4:
                # Latest completed model
                result.scalar_one_or_none.return_value = None
            elif call_count == 5:
                # Shelf items aggregation (empty)
                result.all.return_value = []
            elif call_count == 6:
                # Audit logs
                result.scalars.return_value.all.return_value = []
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == engagement_id
        assert data["engagement_name"] == "Test Engagement"
        assert data["evidence_item_count"] == 15
        assert data["process_model_count"] == 2
        assert "gap_counts" in data
        assert "recent_activity" in data

    @pytest.mark.asyncio
    async def test_dashboard_not_found(self, client, mock_db_session):
        """Returns 404 when engagement not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        eng_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/dashboard/{eng_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_dashboard_invalid_id(self, client, mock_db_session):
        """Returns 400 for invalid engagement ID format."""
        response = await client.get("/api/v1/dashboard/not-a-uuid")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_dashboard_with_model_and_gaps(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns gap counts when a completed model exists."""
        mock_model = MagicMock()
        mock_model.id = uuid.uuid4()
        mock_model.confidence_score = 0.78
        mock_model.status = ProcessModelStatus.COMPLETED

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement
            elif call_count == 2:
                result.scalar.return_value = 10
            elif call_count == 3:
                result.scalar.return_value = 1
            elif call_count == 4:
                result.scalar_one_or_none.return_value = mock_model
            elif call_count == 5:
                result.all.return_value = []
            elif call_count == 6:
                # Gap counts by severity
                high_row = MagicMock()
                high_row.severity = GapSeverity.HIGH
                high_row.cnt = 2
                med_row = MagicMock()
                med_row.severity = GapSeverity.MEDIUM
                med_row.cnt = 3
                result.all.return_value = [high_row, med_row]
            elif call_count == 7:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_confidence"] == 0.78
        assert data["gap_counts"]["high"] == 2
        assert data["gap_counts"]["medium"] == 3
        assert data["gap_counts"]["low"] == 0

    @pytest.mark.asyncio
    async def test_dashboard_with_audit_logs(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns recent activity entries."""
        mock_log = MagicMock()
        mock_log.id = uuid.uuid4()
        mock_log.action = AuditAction.EVIDENCE_UPLOADED
        mock_log.actor = "system"
        mock_log.details = "File uploaded"
        mock_log.created_at = "2024-01-01T00:00:00Z"

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement
            elif call_count == 2:
                result.scalar.return_value = 5
            elif call_count == 3:
                result.scalar.return_value = 0
            elif call_count == 4:
                result.scalar_one_or_none.return_value = None
            elif call_count == 5:
                result.all.return_value = []
            elif call_count == 6:
                result.scalars.return_value.all.return_value = [mock_log]
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_activity"]) == 1
        assert data["recent_activity"][0]["action"] == "evidence_uploaded"
        assert data["recent_activity"][0]["actor"] == "system"


class TestGetEvidenceCoverage:
    """Tests for GET /api/v1/dashboard/{engagement_id}/evidence-coverage."""

    @pytest.mark.asyncio
    async def test_evidence_coverage_returns_200(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns evidence coverage breakdown."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement.id
            elif call_count == 2:
                row1 = MagicMock()
                row1.category = EvidenceCategory.DOCUMENTS
                row1.total = 10
                row1.received = 8
                row2 = MagicMock()
                row2.category = EvidenceCategory.IMAGES
                row2.total = 5
                row2.received = 1
                result.all.return_value = [row1, row2]
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}/evidence-coverage")

        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == engagement_id
        assert len(data["categories"]) == 2
        # 9 received out of 15 total = 60%
        assert data["overall_coverage_pct"] == 60.0

        # Documents: 8/10 = 80%, not below threshold
        docs = data["categories"][0]
        assert docs["coverage_pct"] == 80.0
        assert docs["below_threshold"] is False

        # Images: 1/5 = 20%, below threshold
        imgs = data["categories"][1]
        assert imgs["coverage_pct"] == 20.0
        assert imgs["below_threshold"] is True

    @pytest.mark.asyncio
    async def test_evidence_coverage_not_found(self, client, mock_db_session):
        """Returns 404 when engagement not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        eng_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/dashboard/{eng_id}/evidence-coverage")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_evidence_coverage_empty(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns 0% when no shelf request items exist."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement.id
            elif call_count == 2:
                result.all.return_value = []
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}/evidence-coverage")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_coverage_pct"] == 0.0
        assert data["categories"] == []


class TestGetConfidenceDistribution:
    """Tests for GET /api/v1/dashboard/{engagement_id}/confidence-distribution."""

    @pytest.mark.asyncio
    async def test_confidence_distribution_returns_200(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns confidence distribution when a completed model exists."""
        mock_model = MagicMock()
        mock_model.id = uuid.uuid4()
        mock_model.confidence_score = 0.72
        mock_model.status = ProcessModelStatus.COMPLETED

        mock_elem1 = MagicMock()
        mock_elem1.id = uuid.uuid4()
        mock_elem1.name = "Submit Request"
        mock_elem1.element_type = "activity"
        mock_elem1.confidence_score = 0.95

        mock_elem2 = MagicMock()
        mock_elem2.id = uuid.uuid4()
        mock_elem2.name = "Review Request"
        mock_elem2.element_type = "activity"
        mock_elem2.confidence_score = 0.3

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement.id
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_model
            elif call_count == 3:
                result.scalars.return_value.all.return_value = [
                    mock_elem1,
                    mock_elem2,
                ]
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}/confidence-distribution")

        assert response.status_code == 200
        data = response.json()
        assert data["model_id"] == str(mock_model.id)
        assert data["overall_confidence"] == 0.72
        assert len(data["distribution"]) == 5

        # VERY_HIGH should have 1 element (0.95)
        very_high = next(d for d in data["distribution"] if d["level"] == "VERY_HIGH")
        assert very_high["count"] == 1

        # LOW should have 1 element (0.3)
        low = next(d for d in data["distribution"] if d["level"] == "LOW")
        assert low["count"] == 1

        # Weakest elements should include Review Request
        assert len(data["weakest_elements"]) == 2
        assert data["weakest_elements"][0]["name"] == "Review Request"

    @pytest.mark.asyncio
    async def test_confidence_distribution_no_model(self, client, mock_db_session, mock_engagement, engagement_id):
        """Returns empty distribution when no completed model exists."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_engagement.id
            elif call_count == 2:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db_session.execute = AsyncMock(side_effect=side_effect)

        response = await client.get(f"/api/v1/dashboard/{engagement_id}/confidence-distribution")

        assert response.status_code == 200
        data = response.json()
        assert data["model_id"] is None
        assert data["overall_confidence"] == 0.0
        assert all(d["count"] == 0 for d in data["distribution"])
        assert data["weakest_elements"] == []

    @pytest.mark.asyncio
    async def test_confidence_distribution_not_found(self, client, mock_db_session):
        """Returns 404 when engagement not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        eng_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/dashboard/{eng_id}/confidence-distribution")

        assert response.status_code == 404
