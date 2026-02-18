"""Tests for client portal routes.

Tests the /api/v1/portal endpoints for read-only client access to
engagement overview, findings, evidence status, and process models.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from src.core.models import (
    Engagement,
    EngagementStatus,
    EvidenceCategory,
    GapAnalysisResult,
    ProcessModel,
    TOMDimension,
    TOMGapType,
)


class TestPortalOverview:
    """Tests for portal overview route."""

    @pytest.mark.asyncio
    async def test_portal_overview(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting portal overview for an engagement."""
        engagement_id = uuid.uuid4()

        # Mock engagement object
        mock_engagement = MagicMock(spec=Engagement)
        mock_engagement.id = engagement_id
        mock_engagement.name = "Test Engagement"
        mock_engagement.client = "Test Client"
        mock_engagement.status = EngagementStatus.ACTIVE

        # Setup execute calls for all queries
        mock_engagement_result = MagicMock()
        mock_engagement_result.scalar_one_or_none.return_value = mock_engagement

        mock_db_session.execute.side_effect = [
            mock_engagement_result,  # Engagement query
            MagicMock(scalar=MagicMock(return_value=10)),  # evidence_count
            MagicMock(scalar=MagicMock(return_value=2)),   # model_count
            MagicMock(scalar=MagicMock(return_value=3)),   # alert_count
            MagicMock(scalar=MagicMock(return_value=0.85)),  # overall_confidence
        ]

        response = await client.get(f"/api/v1/portal/{engagement_id}/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == str(engagement_id)
        assert data["engagement_name"] == "Test Engagement"
        assert data["client"] == "Test Client"
        assert data["status"] == "active"
        assert data["evidence_count"] == 10
        assert data["process_model_count"] == 2
        assert data["open_alerts"] == 3
        assert data["overall_confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_portal_overview_not_found(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting portal overview for a non-existent engagement."""
        engagement_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/portal/{engagement_id}/overview")
        assert response.status_code == 404


class TestPortalFindings:
    """Tests for portal findings route."""

    @pytest.mark.asyncio
    async def test_portal_findings(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting gap analysis findings for client review."""
        engagement_id = uuid.uuid4()

        mock_gap = MagicMock(spec=GapAnalysisResult)
        mock_gap.id = uuid.uuid4()
        mock_gap.dimension = TOMDimension.PEOPLE_AND_ORGANIZATION
        mock_gap.gap_type = TOMGapType.PARTIAL_GAP
        mock_gap.severity = 0.75
        mock_gap.recommendation = "Improve training"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_gap]
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/portal/{engagement_id}/findings")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["dimension"] == "people_and_organization"


class TestPortalEvidenceStatus:
    """Tests for portal evidence status route."""

    @pytest.mark.asyncio
    async def test_portal_evidence_status(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting evidence status summary."""
        engagement_id = uuid.uuid4()

        # Mock a row from the aggregation query
        mock_row = MagicMock()
        mock_row.category = EvidenceCategory.DOCUMENTS
        mock_row.count = 5
        mock_row.avg_quality = 0.85

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/portal/{engagement_id}/evidence-status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 5
        assert len(data["categories"]) == 1
        assert data["categories"][0]["category"] == "documents"
        assert data["categories"][0]["count"] == 5
        assert data["categories"][0]["avg_quality"] == 0.85


class TestPortalProcess:
    """Tests for portal process model route."""

    @pytest.mark.asyncio
    async def test_portal_process(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting process model data for interactive explorer."""
        engagement_id = uuid.uuid4()
        model_id = uuid.uuid4()

        mock_model = MagicMock(spec=ProcessModel)
        mock_model.id = model_id
        mock_model.scope = "procurement"
        mock_model.confidence_score = 0.9
        mock_model.element_count = 15
        mock_model.bpmn_xml = "<bpmn>...</bpmn>"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/portal/{engagement_id}/process")
        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == str(engagement_id)
        assert data["model"] is not None
        assert data["model"]["id"] == str(model_id)
        assert data["model"]["scope"] == "procurement"

    @pytest.mark.asyncio
    async def test_portal_process_no_model(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """Test getting process model when no model exists returns null."""
        engagement_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        response = await client.get(f"/api/v1/portal/{engagement_id}/process")
        assert response.status_code == 200
        data = response.json()
        assert data["engagement_id"] == str(engagement_id)
        assert data["model"] is None
