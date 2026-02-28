"""BDD tests for BPMN Viewer API endpoints (Story #338).

Tests the backend API endpoints needed by the interactive BPMN.js
process flow visualization component.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.pov import (
    DashboardKPIs,
    ElementEvidenceResponse,
    EngagementBPMNResponse,
    ProcessElementDetailResponse,
    get_element_evidence,
    get_engagement_dashboard,
    get_latest_model_for_engagement,
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
    model_id: uuid.UUID | None = None,
    name: str = "Submit Application",
    confidence: float = 0.85,
    brightness: str = "bright",
    grade: str = "A",
    evidence_count: int = 3,
    evidence_ids: list[str] | None = None,
) -> MagicMock:
    """Create a mock ProcessElement."""
    elem = MagicMock()
    elem.id = uuid.uuid4()
    elem.model_id = model_id or uuid.uuid4()
    elem.element_type = "activity"
    elem.name = name
    elem.confidence_score = confidence
    elem.triangulation_score = 0.7
    elem.corroboration_level = "moderately"
    elem.evidence_count = evidence_count
    elem.evidence_ids = evidence_ids or [str(uuid.uuid4()) for _ in range(evidence_count)]
    elem.evidence_grade = grade
    elem.brightness_classification = brightness
    elem.mvc_threshold_passed = confidence >= 0.75
    elem.metadata_json = None
    return elem


def _make_mock_model(
    engagement_id: uuid.UUID | None = None,
    version: int = 1,
    bpmn_xml: str = "<bpmn>test</bpmn>",
    confidence: float = 0.78,
    element_count: int = 5,
) -> MagicMock:
    """Create a mock ProcessModel."""
    model = MagicMock()
    model.id = uuid.uuid4()
    model.engagement_id = engagement_id or uuid.uuid4()
    model.version = version
    model.bpmn_xml = bpmn_xml
    model.confidence_score = confidence
    model.element_count = element_count
    return model


def _make_mock_evidence(
    name: str = "Client Interview Notes",
    category: str = "Documents",
) -> MagicMock:
    """Create a mock EvidenceItem."""
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.name = name
    ev.category = category
    ev.source_system = "Client Upload"
    ev.created_at = "2026-02-28T12:00:00Z"
    return ev


# ============================================================
# Scenario 1: Latest model for engagement
# ============================================================


class TestLatestModelEndpoint:
    """GET /api/v1/pov/engagement/{id}/latest-model returns the latest
    process model with BPMN and elements."""

    @pytest.mark.asyncio
    async def test_returns_latest_model_with_elements(self) -> None:
        """Latest model includes BPMN XML and element details."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, version=3)
        elem1 = _make_mock_element(model_id=model.id, name="Task A", brightness="bright")
        elem2 = _make_mock_element(model_id=model.id, name="Task B", brightness="dim")

        session = AsyncMock()
        # First call: model query; second call: elements query
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model

        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [elem1, elem2]

        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_latest_model_for_engagement(str(eng_id), session, user)

        assert result["engagement_id"] == str(eng_id)
        assert result["version"] == 3
        assert result["bpmn_xml"] == "<bpmn>test</bpmn>"
        assert len(result["elements"]) == 2

    @pytest.mark.asyncio
    async def test_elements_include_brightness_and_grade(self) -> None:
        """Each element includes brightness_classification and evidence_grade."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id)
        elem = _make_mock_element(model_id=model.id, brightness="dark", grade="D", confidence=0.3)

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [elem]
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_latest_model_for_engagement(str(eng_id), session, user)

        element = result["elements"][0]
        assert element["brightness_classification"] == "dark"
        assert element["evidence_grade"] == "D"
        assert element["confidence_score"] == 0.3

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
            await get_latest_model_for_engagement(str(eng_id), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_bpmn_xml_raises_404(self) -> None:
        """Model without BPMN XML returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, bpmn_xml=None)

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        session.execute = AsyncMock(return_value=model_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_latest_model_for_engagement(str(eng_id), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_engagement_id_raises_400(self) -> None:
        """Invalid engagement ID format returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_latest_model_for_engagement("not-a-uuid", session, user)

        assert exc_info.value.status_code == 400


# ============================================================
# Scenario 2: Element evidence detail
# ============================================================


class TestElementEvidenceEndpoint:
    """GET /api/v1/pov/elements/{id}/evidence returns evidence
    items linked to a process element."""

    @pytest.mark.asyncio
    async def test_returns_linked_evidence(self) -> None:
        """Returns evidence items referenced by element's evidence_ids."""
        ev1 = _make_mock_evidence("Interview Notes", "Documents")
        ev2 = _make_mock_evidence("Process Map", "BPM Process Models")

        model = _make_mock_model()
        elem = _make_mock_element(
            model_id=model.id,
            name="Review Application",
            evidence_ids=[str(ev1.id), str(ev2.id)],
        )

        session = AsyncMock()
        elem_result = MagicMock()
        elem_result.scalar_one_or_none.return_value = elem
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        ev_result = MagicMock()
        ev_result.scalars.return_value.all.return_value = [ev1, ev2]
        session.execute = AsyncMock(side_effect=[elem_result, model_result, ev_result])
        user = _make_mock_user()

        result = await get_element_evidence(str(elem.id), session, user)

        assert result["element_name"] == "Review Application"
        assert result["total"] == 2
        assert result["evidence_items"][0]["title"] == "Interview Notes"
        assert result["evidence_items"][1]["category"] == "BPM Process Models"

    @pytest.mark.asyncio
    async def test_element_with_no_evidence(self) -> None:
        """Element with no evidence_ids returns empty list."""
        model = _make_mock_model()
        elem = _make_mock_element(model_id=model.id, name="Unknown Step", evidence_ids=[], evidence_count=0)

        session = AsyncMock()
        elem_result = MagicMock()
        elem_result.scalar_one_or_none.return_value = elem
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        session.execute = AsyncMock(side_effect=[elem_result, model_result])
        user = _make_mock_user()

        result = await get_element_evidence(str(elem.id), session, user)

        assert result["total"] == 0
        assert result["evidence_items"] == []

    @pytest.mark.asyncio
    async def test_element_not_found_raises_404(self) -> None:
        """Missing element returns 404."""
        from fastapi import HTTPException

        session = AsyncMock()
        elem_result = MagicMock()
        elem_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=elem_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_element_evidence(str(uuid.uuid4()), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_element_id_raises_400(self) -> None:
        """Invalid element ID format returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_element_evidence("bad-id", session, user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user without engagement access gets 403."""
        from fastapi import HTTPException

        model = _make_mock_model()
        elem = _make_mock_element(model_id=model.id, evidence_ids=[], evidence_count=0)

        session = AsyncMock()
        elem_result = MagicMock()
        elem_result.scalar_one_or_none.return_value = elem
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        # Membership check returns None (not a member)
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[elem_result, model_result, member_result])
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_element_evidence(str(elem.id), session, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_evidence_items_include_all_fields(self) -> None:
        """Each evidence item has title, category, grade, source, date."""
        ev = _make_mock_evidence("Org Chart", "Structured Data")
        model = _make_mock_model()
        elem = _make_mock_element(model_id=model.id, evidence_ids=[str(ev.id)], evidence_count=1)

        session = AsyncMock()
        elem_result = MagicMock()
        elem_result.scalar_one_or_none.return_value = elem
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        ev_result = MagicMock()
        ev_result.scalars.return_value.all.return_value = [ev]
        session.execute = AsyncMock(side_effect=[elem_result, model_result, ev_result])
        user = _make_mock_user()

        result = await get_element_evidence(str(elem.id), session, user)

        item = result["evidence_items"][0]
        assert item["title"] == "Org Chart"
        assert item["category"] == "Structured Data"
        assert item["grade"] == "N/A"
        assert item["source"] == "Client Upload"
        assert item["created_at"] is not None


# ============================================================
# Scenario 3: Confidence-based dashboard KPIs
# ============================================================


class TestDashboardKPIsEndpoint:
    """GET /api/v1/pov/engagement/{id}/dashboard returns KPIs
    including brightness distribution and gap counts."""

    @pytest.mark.asyncio
    async def test_returns_brightness_distribution(self) -> None:
        """Dashboard includes bright/dim/dark element counts and percentages."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, confidence=0.72, element_count=6)

        bright_elem = _make_mock_element(brightness="bright")
        dim_elem1 = _make_mock_element(brightness="dim")
        dim_elem2 = _make_mock_element(brightness="dim")
        dark_elem = _make_mock_element(brightness="dark")

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model

        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [bright_elem, dim_elem1, dim_elem2, dark_elem]

        gap_count_result = MagicMock()
        gap_count_result.scalar.return_value = 3
        critical_gap_result = MagicMock()
        critical_gap_result.scalar.return_value = 1

        session.execute = AsyncMock(side_effect=[model_result, elem_result, gap_count_result, critical_gap_result])
        user = _make_mock_user()

        result = await get_engagement_dashboard(str(eng_id), session, user)

        assert result["brightness_distribution"]["bright"] == 1
        assert result["brightness_distribution"]["dim"] == 2
        assert result["brightness_distribution"]["dark"] == 1
        assert result["brightness_percentages"]["bright"] == 25.0
        assert result["overall_confidence"] == 0.72
        assert result["gap_count"] == 3
        assert result["critical_gap_count"] == 1

    @pytest.mark.asyncio
    async def test_evidence_coverage_percentage(self) -> None:
        """Evidence coverage = % of elements with at least 1 evidence item."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, element_count=4)

        # 3 out of 4 have evidence
        e1 = _make_mock_element(evidence_count=2, brightness="bright")
        e2 = _make_mock_element(evidence_count=1, brightness="dim")
        e3 = _make_mock_element(evidence_count=0, brightness="dark")
        e4 = _make_mock_element(evidence_count=3, brightness="bright")

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [e1, e2, e3, e4]
        gap_result = MagicMock()
        gap_result.scalar.return_value = 0
        crit_result = MagicMock()
        crit_result.scalar.return_value = 0
        session.execute = AsyncMock(side_effect=[model_result, elem_result, gap_result, crit_result])
        user = _make_mock_user()

        result = await get_engagement_dashboard(str(eng_id), session, user)

        assert result["evidence_coverage"] == 75.0

    @pytest.mark.asyncio
    async def test_no_model_raises_404(self) -> None:
        """Missing model returns 404."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=model_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_engagement_dashboard(str(eng_id), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_engagement_id_raises_400(self) -> None:
        """Invalid engagement ID returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_engagement_dashboard("bad-id", session, user)

        assert exc_info.value.status_code == 400


# ============================================================
# Schema validation tests
# ============================================================


class TestBPMNViewerSchemas:
    """Schema validation for BPMN viewer API response models."""

    def test_element_detail_response_validates(self) -> None:
        """ProcessElementDetailResponse includes brightness and grade."""
        resp = ProcessElementDetailResponse(
            id="elem-1",
            model_id="model-1",
            element_type="activity",
            name="Submit Form",
            confidence_score=0.82,
            triangulation_score=0.7,
            corroboration_level="moderately",
            evidence_count=3,
            evidence_grade="A",
            brightness_classification="bright",
        )
        assert resp.brightness_classification == "bright"
        assert resp.evidence_grade == "A"
        assert resp.mvc_threshold_passed is False

    def test_element_evidence_response_validates(self) -> None:
        """ElementEvidenceResponse schema is valid."""
        resp = ElementEvidenceResponse(
            element_id="elem-1",
            element_name="Review",
            evidence_items=[],
            total=0,
        )
        assert resp.total == 0

    def test_dashboard_kpis_validates(self) -> None:
        """DashboardKPIs schema is valid."""
        resp = DashboardKPIs(
            engagement_id="eng-1",
            model_version=2,
            overall_confidence=0.75,
            element_count=10,
            brightness_distribution={"bright": 5, "dim": 3, "dark": 2},
            brightness_percentages={"bright": 50.0, "dim": 30.0, "dark": 20.0},
            evidence_coverage=80.0,
            gap_count=4,
            critical_gap_count=1,
        )
        assert resp.brightness_distribution["bright"] == 5
        assert resp.gap_count == 4

    def test_engagement_bpmn_response_validates(self) -> None:
        """EngagementBPMNResponse schema is valid."""
        resp = EngagementBPMNResponse(
            engagement_id="eng-1",
            model_id="model-1",
            version=1,
            bpmn_xml="<bpmn/>",
            confidence_score=0.8,
            element_count=5,
            elements=[],
        )
        assert resp.version == 1
        assert resp.bpmn_xml == "<bpmn/>"
