"""BDD tests for Evidence Mapping Overlay API endpoints (Story #343).

Tests the reverse evidence-to-element lookup and dark element
endpoints that support the evidence mapping overlay feature.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.pov import (
    DarkElementEntry,
    DarkElementsResponse,
    ReverseElementEntry,
    ReverseEvidenceLookupResponse,
    _suggest_evidence_actions,
    get_dark_elements,
    get_elements_for_evidence,
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
    element_type: str = "activity",
    confidence: float = 0.85,
    brightness: str = "bright",
    evidence_count: int = 3,
    evidence_ids: list[str] | None = None,
) -> MagicMock:
    """Create a mock ProcessElement."""
    elem = MagicMock()
    elem.id = uuid.uuid4()
    elem.model_id = model_id or uuid.uuid4()
    elem.element_type = element_type
    elem.name = name
    elem.confidence_score = confidence
    elem.brightness_classification = brightness
    elem.evidence_count = evidence_count
    elem.evidence_ids = evidence_ids or [str(uuid.uuid4()) for _ in range(evidence_count)]
    return elem


def _make_mock_model(
    engagement_id: uuid.UUID | None = None,
    version: int = 1,
) -> MagicMock:
    """Create a mock ProcessModel."""
    model = MagicMock()
    model.id = uuid.uuid4()
    model.engagement_id = engagement_id or uuid.uuid4()
    model.version = version
    return model


def _make_mock_evidence(
    engagement_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock EvidenceItem."""
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.engagement_id = engagement_id or uuid.uuid4()
    ev.name = "Test Evidence"
    ev.category = "Documents"
    return ev


# ============================================================
# Scenario 2: Process elements highlighted from evidence panel
# ============================================================


class TestReverseEvidenceLookup:
    """GET /api/v1/pov/evidence/{id}/process-elements returns elements
    that reference a given evidence item."""

    @pytest.mark.asyncio
    async def test_returns_matching_elements(self) -> None:
        """Elements referencing the evidence ID are returned."""
        eng_id = uuid.uuid4()
        evidence = _make_mock_evidence(engagement_id=eng_id)
        model = _make_mock_model(engagement_id=eng_id)

        # Two elements reference this evidence, one does not
        elem1 = _make_mock_element(
            model_id=model.id,
            name="Task A",
            evidence_ids=[str(evidence.id), str(uuid.uuid4())],
        )
        elem2 = _make_mock_element(
            model_id=model.id,
            name="Task B",
            evidence_ids=[str(evidence.id)],
        )
        elem3 = _make_mock_element(
            model_id=model.id,
            name="Task C",
            evidence_ids=[str(uuid.uuid4())],
        )

        session = AsyncMock()
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = evidence
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [elem1, elem2, elem3]
        session.execute = AsyncMock(side_effect=[ev_result, model_result, elem_result])
        user = _make_mock_user()

        result = await get_elements_for_evidence(str(evidence.id), session, user)

        assert result["evidence_id"] == str(evidence.id)
        assert result["total"] == 2
        element_names = [e["element_name"] for e in result["elements"]]
        assert "Task A" in element_names
        assert "Task B" in element_names
        assert "Task C" not in element_names

    @pytest.mark.asyncio
    async def test_no_matching_elements(self) -> None:
        """Evidence not referenced by any element returns empty list."""
        eng_id = uuid.uuid4()
        evidence = _make_mock_evidence(engagement_id=eng_id)
        model = _make_mock_model(engagement_id=eng_id)

        elem = _make_mock_element(
            model_id=model.id,
            evidence_ids=[str(uuid.uuid4())],
        )

        session = AsyncMock()
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = evidence
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [elem]
        session.execute = AsyncMock(side_effect=[ev_result, model_result, elem_result])
        user = _make_mock_user()

        result = await get_elements_for_evidence(str(evidence.id), session, user)

        assert result["total"] == 0
        assert result["elements"] == []

    @pytest.mark.asyncio
    async def test_evidence_not_found_raises_404(self) -> None:
        """Missing evidence item returns 404."""
        from fastapi import HTTPException

        session = AsyncMock()
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=ev_result)
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_elements_for_evidence(str(uuid.uuid4()), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_evidence_id_raises_400(self) -> None:
        """Invalid evidence ID format returns 400."""
        from fastapi import HTTPException

        session = AsyncMock()
        user = _make_mock_user()

        with pytest.raises(HTTPException) as exc_info:
            await get_elements_for_evidence("bad-id", session, user)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user gets 403 Forbidden."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        evidence = _make_mock_evidence(engagement_id=eng_id)

        session = AsyncMock()
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = evidence
        # Membership check returns None
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[ev_result, member_result])
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_elements_for_evidence(str(evidence.id), session, user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_elements_include_brightness(self) -> None:
        """Returned elements include brightness classification for highlighting."""
        eng_id = uuid.uuid4()
        evidence = _make_mock_evidence(engagement_id=eng_id)
        model = _make_mock_model(engagement_id=eng_id)

        elem = _make_mock_element(
            model_id=model.id,
            brightness="dim",
            confidence=0.55,
            evidence_ids=[str(evidence.id)],
        )

        session = AsyncMock()
        ev_result = MagicMock()
        ev_result.scalar_one_or_none.return_value = evidence
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [elem]
        session.execute = AsyncMock(side_effect=[ev_result, model_result, elem_result])
        user = _make_mock_user()

        result = await get_elements_for_evidence(str(evidence.id), session, user)

        assert result["elements"][0]["brightness_classification"] == "dim"
        assert result["elements"][0]["confidence_score"] == 0.55


# ============================================================
# Scenario 3: Dark elements marked as unsupported
# ============================================================


class TestDarkElementsEndpoint:
    """GET /api/v1/pov/engagement/{id}/dark-elements returns elements
    with no supporting evidence and suggested actions."""

    @pytest.mark.asyncio
    async def test_returns_dark_elements_with_suggestions(self) -> None:
        """Dark elements include suggested evidence acquisition actions."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id, version=2)

        dark1 = _make_mock_element(
            model_id=model.id,
            name="Approve Loan",
            element_type="activity",
            evidence_count=0,
            brightness="dark",
            confidence=0.0,
        )
        dark2 = _make_mock_element(
            model_id=model.id,
            name="Risk Check",
            element_type="gateway",
            evidence_count=0,
            brightness="dark",
            confidence=0.0,
        )

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = [dark1, dark2]
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_dark_elements(str(eng_id), session, user)

        assert result["engagement_id"] == str(eng_id)
        assert result["model_version"] == 2
        assert result["total"] == 2

        # Activity should have SME interview suggestion
        activity_elem = next(e for e in result["dark_elements"] if e["element_name"] == "Approve Loan")
        assert any("SME interview" in a for a in activity_elem["suggested_actions"])

        # Gateway should have decision criteria suggestion
        gateway_elem = next(e for e in result["dark_elements"] if e["element_name"] == "Risk Check")
        assert any("decision criteria" in a for a in gateway_elem["suggested_actions"])

    @pytest.mark.asyncio
    async def test_no_dark_elements(self) -> None:
        """Engagement with no dark elements returns empty list."""
        eng_id = uuid.uuid4()
        model = _make_mock_model(engagement_id=eng_id)

        session = AsyncMock()
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = model
        elem_result = MagicMock()
        elem_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[model_result, elem_result])
        user = _make_mock_user()

        result = await get_dark_elements(str(eng_id), session, user)

        assert result["total"] == 0
        assert result["dark_elements"] == []

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
            await get_dark_elements(str(eng_id), session, user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self) -> None:
        """Non-member user gets 403."""
        from fastapi import HTTPException

        eng_id = uuid.uuid4()
        session = AsyncMock()
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=member_result)
        user = _make_mock_user(role=UserRole.ENGAGEMENT_LEAD)

        with pytest.raises(HTTPException) as exc_info:
            await get_dark_elements(str(eng_id), session, user)

        assert exc_info.value.status_code == 403


# ============================================================
# Suggestion helper tests
# ============================================================


class TestSuggestEvidenceActions:
    """Tests for the _suggest_evidence_actions helper."""

    def test_activity_suggestions(self) -> None:
        """Activity elements get SME interview and documentation suggestions."""
        suggestions = _suggest_evidence_actions("activity", "Review Application")
        assert len(suggestions) == 3
        assert any("SME interview" in s for s in suggestions)
        assert any("documentation" in s for s in suggestions)

    def test_gateway_suggestions(self) -> None:
        """Gateway elements get decision criteria suggestions."""
        suggestions = _suggest_evidence_actions("gateway", "Approve?")
        assert len(suggestions) == 2
        assert any("decision criteria" in s for s in suggestions)

    def test_role_suggestions(self) -> None:
        """Role elements get org chart suggestions."""
        suggestions = _suggest_evidence_actions("role", "Loan Officer")
        assert len(suggestions) == 2
        assert any("org chart" in s or "RACI" in s for s in suggestions)

    def test_event_suggestions(self) -> None:
        """Event elements get trigger condition suggestions."""
        suggestions = _suggest_evidence_actions("event", "Timer Expired")
        assert len(suggestions) == 2
        assert any("trigger" in s for s in suggestions)

    def test_unknown_type_suggestions(self) -> None:
        """Unknown element types get generic suggestions."""
        suggestions = _suggest_evidence_actions("document", "Policy Manual")
        assert len(suggestions) == 2
        assert any("supporting evidence" in s for s in suggestions)


# ============================================================
# Schema validation tests
# ============================================================


class TestEvidenceMappingSchemas:
    """Schema validation for evidence mapping response models."""

    def test_reverse_element_entry_validates(self) -> None:
        """ReverseElementEntry schema is valid."""
        entry = ReverseElementEntry(
            element_id="elem-1",
            element_name="Task A",
            element_type="activity",
            confidence_score=0.75,
            brightness_classification="dim",
        )
        assert entry.element_name == "Task A"

    def test_reverse_lookup_response_validates(self) -> None:
        """ReverseEvidenceLookupResponse schema is valid."""
        resp = ReverseEvidenceLookupResponse(
            evidence_id="ev-1",
            elements=[],
            total=0,
        )
        assert resp.total == 0

    def test_dark_element_entry_validates(self) -> None:
        """DarkElementEntry includes suggested_actions."""
        entry = DarkElementEntry(
            element_id="elem-1",
            element_name="Unknown Step",
            element_type="activity",
            confidence_score=0.0,
            evidence_count=0,
            suggested_actions=["Schedule SME interview"],
        )
        assert len(entry.suggested_actions) == 1

    def test_dark_elements_response_validates(self) -> None:
        """DarkElementsResponse schema is valid."""
        resp = DarkElementsResponse(
            engagement_id="eng-1",
            model_version=1,
            dark_elements=[],
            total=0,
        )
        assert resp.model_version == 1
