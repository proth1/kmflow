"""BDD tests for Confidence Heatmap API endpoints (Story #341).

Tests the confidence map and summary export endpoints that provide
data for the heatmap overlay on the BPMN.js process viewer.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.pov import (
    ConfidenceMapResponse,
    ConfidenceSummaryResponse,
    ElementConfidenceEntry,
    get_confidence_map,
    get_confidence_summary,
)
from src.core.models import UserRole

# -- Fixtures ----------------------------------------------------------------


def _make_mock_user(role: UserRole = UserRole.PLATFORM_ADMIN) -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_mock_element(
    brightness: str = "bright",
    confidence: float = 0.85,
    grade: str = "A",
    evidence_count: int = 3,
) -> MagicMock:
    """Create a mock ProcessElement."""
    elem = MagicMock()
    elem.id = uuid.uuid4()
    elem.name = "Test Element"
    elem.confidence_score = confidence
    elem.brightness_classification = brightness
    elem.evidence_grade = grade
    elem.evidence_count = evidence_count
    return elem


def _make_mock_model(
    engagement_id: uuid.UUID | None = None,
    version: int = 1,
    confidence: float = 0.78,
) -> MagicMock:
    """Create a mock ProcessModel."""
    model = MagicMock()
    model.id = uuid.uuid4()
    model.engagement_id = engagement_id or uuid.uuid4()
    model.version = version
    model.confidence_score = confidence
    return model


# ============================================================
# Scenario 1: Heatmap toggle colors elements by brightness
# ============================================================


class TestConfidenceMapEndpoint:
    """GET /api/v1/pov/engagement/{id}/confidence returns per-element
    confidence data for the heatmap overlay."""

    @pytest.mark.asyncio
    async def test_returns_element_confidence_map(self) -> None:
        """Confidence map includes score, brightness, and grade per element."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, version=2)
        bright_elem = _make_mock_element(brightness="bright", confidence=0.85, grade="A")
        dim_elem = _make_mock_element(brightness="dim", confidence=0.55, grade="C")
        dark_elem = _make_mock_element(brightness="dark", confidence=0.2, grade="D")

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [bright_elem, dim_elem, dark_elem]
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_map(str(eng_id), session, user)

        assert result["engagement_id"] == str(eng_id)
        assert result["model_version"] == 2
        assert result["total_elements"] == 3
        assert str(bright_elem.id) in result["elements"]
        assert result["elements"][str(bright_elem.id)]["brightness"] == "bright"
        assert result["elements"][str(dim_elem.id)]["score"] == 0.55
        assert result["elements"][str(dark_elem.id)]["grade"] == "D"

    @pytest.mark.asyncio
    async def test_no_model_raises_404(self) -> None:
        """Missing model for engagement returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=model_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_confidence_map(str(eng_id), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_engagement_id_raises_400(self) -> None:
        """Invalid engagement ID format returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_confidence_map("bad-id", session, user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_model_returns_empty_map(self) -> None:
        """Model with no elements returns empty confidence map."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id)

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_map(str(eng_id), session, user)

        assert result["total_elements"] == 0
        assert result["elements"] == {}

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user without engagement access gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        # Membership check returns None (not a member)
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=member_result)
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_confidence_map(str(eng_id), session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Scenario 3: Heatmap summary export
# ============================================================


class TestConfidenceSummaryEndpoint:
    """GET /api/v1/pov/engagement/{id}/confidence/summary returns
    brightness distribution summary for export."""

    @pytest.mark.asyncio
    async def test_returns_brightness_counts_and_percentages(self) -> None:
        """Summary includes counts and percentages for each tier."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, version=3, confidence=0.72)

        elems = [
            _make_mock_element(brightness="bright"),
            _make_mock_element(brightness="bright"),
            _make_mock_element(brightness="dim"),
            _make_mock_element(brightness="dark"),
        ]

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = elems
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_summary(str(eng_id), "json", session, user)

        assert result["total_elements"] == 4
        assert result["bright_count"] == 2
        assert result["bright_percentage"] == 50.0
        assert result["dim_count"] == 1
        assert result["dim_percentage"] == 25.0
        assert result["dark_count"] == 1
        assert result["dark_percentage"] == 25.0
        assert result["overall_confidence"] == 0.72

    @pytest.mark.asyncio
    async def test_csv_export_returns_csv_content(self) -> None:
        """CSV format returns text/csv response with proper headers."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, version=1, confidence=0.65)

        elems = [
            _make_mock_element(brightness="bright"),
            _make_mock_element(brightness="dim"),
        ]

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = elems
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_summary(str(eng_id), "csv", session, user)

        assert result.media_type == "text/csv"
        body = result.body.decode()
        assert "Metric,Value" in body
        assert "Bright Count,1" in body
        assert "Dim Count,1" in body
        assert "Dark Count,0" in body
        assert "Overall Confidence,0.65" in body

    @pytest.mark.asyncio
    async def test_no_model_raises_404(self) -> None:
        """Missing model for engagement returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=model_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_confidence_summary(str(eng_id), "json", session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_all_bright_elements(self) -> None:
        """All elements bright results in 100% bright."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, confidence=0.95)

        elems = [
            _make_mock_element(brightness="bright"),
            _make_mock_element(brightness="bright"),
            _make_mock_element(brightness="bright"),
        ]

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = elems
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_summary(str(eng_id), "json", session, user)

        assert result["bright_percentage"] == 100.0
        assert result["dim_percentage"] == 0.0
        assert result["dark_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_csv_has_content_disposition_header(self) -> None:
        """CSV response includes Content-Disposition for download."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, confidence=0.5)

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [_make_mock_element(brightness="dim")]
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_confidence_summary(str(eng_id), "csv", session, user)

        content_disp = result.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert "confidence-summary" in content_disp

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user without engagement access gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=member_result)
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_confidence_summary(str(eng_id), "json", session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Schema validation tests
# ============================================================


class TestConfidenceHeatmapSchemas:
    """Schema validation for confidence heatmap response models."""

    def test_element_confidence_entry_validates(self) -> None:
        """ElementConfidenceEntry requires score, brightness, grade."""
        entry = ElementConfidenceEntry(score=0.85, brightness="bright", grade="A")
        assert entry.score == 0.85
        assert entry.brightness == "bright"

    def test_confidence_map_response_validates(self) -> None:
        """ConfidenceMapResponse includes elements dict."""
        resp = ConfidenceMapResponse(
            engagement_id="eng-1",
            model_version=2,
            elements={},
            total_elements=0,
        )
        assert resp.model_version == 2
        assert resp.total_elements == 0

    def test_confidence_summary_response_validates(self) -> None:
        """ConfidenceSummaryResponse includes all tier fields."""
        resp = ConfidenceSummaryResponse(
            engagement_id="eng-1",
            model_version=1,
            total_elements=10,
            bright_count=5,
            bright_percentage=50.0,
            dim_count=3,
            dim_percentage=30.0,
            dark_count=2,
            dark_percentage=20.0,
            overall_confidence=0.75,
        )
        assert resp.bright_count == 5
        assert resp.dark_percentage == 20.0
