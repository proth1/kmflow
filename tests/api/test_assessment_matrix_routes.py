"""Tests for Assessment Overlay Matrix API routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.api.routes.assessment_matrix import (
    compute_assessment_matrix,
    export_assessment_matrix,
    get_assessment_matrix,
)


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = "platform_admin"
    return user


def _make_entry(name: str = "Loan Processing", quadrant: str = "transform") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "process_area_name": name,
        "process_area_description": None,
        "value_score": 72.5,
        "ability_to_execute": 65.3,
        "quadrant": quadrant,
        "value_components": {
            "volume_impact": 80.0,
            "cost_savings_potential": 60.0,
            "risk_reduction": 75.0,
            "strategic_alignment": 70.0,
        },
        "ability_components": {
            "process_maturity": 60.0,
            "evidence_confidence": 70.0,
            "compliance_readiness": 65.0,
            "resource_availability": 60.0,
        },
        "element_count": 5,
        "notes": None,
        "created_at": "2026-03-11T10:00:00+00:00",
        "updated_at": None,
    }


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    return _mock_user()


class TestGetAssessmentMatrix:
    @pytest.mark.asyncio
    async def test_returns_entries(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()
        entries = [_make_entry("Loan Processing", "transform"), _make_entry("Payments", "invest")]

        with patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls:
            svc_cls.return_value.get_matrix = AsyncMock(return_value=entries)
            result = await get_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert result["total"] == 2
        assert result["engagement_id"] == str(engagement_id)
        assert "entries" in result
        assert "quadrant_summary" in result

    @pytest.mark.asyncio
    async def test_empty_matrix(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()

        with patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls:
            svc_cls.return_value.get_matrix = AsyncMock(return_value=[])
            result = await get_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert result["total"] == 0
        assert result["entries"] == []

    @pytest.mark.asyncio
    async def test_quadrant_summary_counts(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()
        entries = [
            _make_entry("A", "transform"),
            _make_entry("B", "transform"),
            _make_entry("C", "invest"),
        ]

        with patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls:
            svc_cls.return_value.get_matrix = AsyncMock(return_value=entries)
            result = await get_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert result["quadrant_summary"]["transform"] == 2
        assert result["quadrant_summary"]["invest"] == 1


class TestComputeAssessmentMatrix:
    @pytest.mark.asyncio
    async def test_compute_returns_entries(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()
        entries = [_make_entry()]

        with (
            patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls,
            patch("src.api.routes.assessment_matrix.log_audit", new_callable=AsyncMock),
        ):
            svc_cls.return_value.compute_matrix = AsyncMock(return_value=entries)
            result = await compute_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert result["total"] == 1
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_compute_empty_engagement(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()

        with (
            patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls,
            patch("src.api.routes.assessment_matrix.log_audit", new_callable=AsyncMock),
        ):
            svc_cls.return_value.compute_matrix = AsyncMock(return_value=[])
            result = await compute_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert result["total"] == 0


class TestExportAssessmentMatrix:
    @pytest.mark.asyncio
    async def test_export_returns_recommendations(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()
        entries = [
            _make_entry("A", "transform"),
            _make_entry("B", "invest"),
        ]

        with (
            patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls,
            patch("src.api.routes.assessment_matrix.log_audit", new_callable=AsyncMock),
        ):
            svc_cls.return_value.get_matrix = AsyncMock(return_value=entries)
            result = await export_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert "recommendations" in result
        assert "quadrant_analysis" in result
        assert len(result["recommendations"]) == 2  # transform + invest

    @pytest.mark.asyncio
    async def test_export_empty_raises_404(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()

        with patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls:
            svc_cls.return_value.get_matrix = AsyncMock(return_value=[])
            with pytest.raises(Exception) as exc_info:
                await export_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_export_all_quadrants(self, mock_session: AsyncMock, mock_user: MagicMock) -> None:
        engagement_id = uuid.uuid4()
        entries = [
            _make_entry("A", "transform"),
            _make_entry("B", "invest"),
            _make_entry("C", "maintain"),
            _make_entry("D", "deprioritize"),
        ]

        with (
            patch("src.api.routes.assessment_matrix.AssessmentMatrixService") as svc_cls,
            patch("src.api.routes.assessment_matrix.log_audit", new_callable=AsyncMock),
        ):
            svc_cls.return_value.get_matrix = AsyncMock(return_value=entries)
            result = await export_assessment_matrix(engagement_id, mock_session, mock_user, mock_user)

        assert len(result["recommendations"]) == 4
        priorities = {r["priority"] for r in result["recommendations"]}
        assert priorities == {"high", "medium", "low", "info"}
