"""Tests for decision intelligence API routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routes.decisions import (
    ValidateRulePayload,
    export_decision_dmn,
    get_decision_coverage,
    get_decision_rules,
    list_decisions,
    validate_decision_rule,
)


def _make_element(
    *,
    name: str = "Check Credit Score",
    confidence_score: float = 0.85,
    evidence_count: int = 3,
    metadata_json: dict | None = None,
) -> MagicMock:
    """Create a mock ProcessElement."""
    elem = MagicMock()
    elem.id = uuid.uuid4()
    elem.name = name
    elem.confidence_score = confidence_score
    elem.evidence_count = evidence_count
    elem.metadata_json = metadata_json or {}
    return elem


def _mock_session(elements: list | None = None, scalar_one: MagicMock | None = None) -> AsyncMock:
    """Create a mock AsyncSession returning the given elements."""
    session = AsyncMock()
    mock_result = MagicMock()
    if elements is not None:
        mock_result.scalars.return_value.all.return_value = elements
    if scalar_one is not None:
        mock_result.scalar_one_or_none.return_value = scalar_one
    else:
        mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()
    return session


def _mock_user() -> MagicMock:
    """Create a mock User."""
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestListDecisions:
    """Tests for GET /engagements/{id}/decisions."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        session = _mock_session(elements=[])
        result = await list_decisions(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
            limit=50,
            offset=0,
            min_confidence=0.0,
        )
        assert result["decisions"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_decisions_with_brightness(self) -> None:
        elements = [
            _make_element(name="High Confidence", confidence_score=0.90),
            _make_element(name="Medium Confidence", confidence_score=0.50),
            _make_element(name="Low Confidence", confidence_score=0.20),
        ]
        session = _mock_session(elements=elements)
        result = await list_decisions(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
            limit=50,
            offset=0,
            min_confidence=0.0,
        )
        assert result["total"] == 3
        assert result["decisions"][0]["brightness"] == "BRIGHT"
        assert result["decisions"][1]["brightness"] == "DIM"
        assert result["decisions"][2]["brightness"] == "DARK"

    @pytest.mark.asyncio
    async def test_rule_count_from_metadata(self) -> None:
        elem = _make_element(metadata_json={"rule_count": 5})
        session = _mock_session(elements=[elem])
        result = await list_decisions(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
            limit=50,
            offset=0,
            min_confidence=0.0,
        )
        assert result["decisions"][0]["rule_count"] == 5


class TestGetDecisionRules:
    """Tests for GET /engagements/{id}/decisions/{id}/rules."""

    @pytest.mark.asyncio
    async def test_returns_rules(self) -> None:
        elem = _make_element(
            metadata_json={
                "rules": [
                    {"id": "r1", "rule_text": "Score > 700", "threshold_value": "700"},
                    {"id": "r2", "rule_text": "DTI < 43%"},
                ]
            }
        )
        session = _mock_session(scalar_one=elem)
        result = await get_decision_rules(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["total"] == 2
        assert result["rules"][0]["rule_text"] == "Score > 700"
        assert result["rules"][0]["threshold_value"] == "700"

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        session = _mock_session(scalar_one=None)
        with pytest.raises(Exception) as exc_info:
            await get_decision_rules(
                engagement_id=uuid.uuid4(),
                decision_id=uuid.uuid4(),
                session=session,
                _user=_mock_user(),
                _engagement_user=_mock_user(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_rules(self) -> None:
        elem = _make_element(metadata_json={})
        session = _mock_session(scalar_one=elem)
        result = await get_decision_rules(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["total"] == 0
        assert result["rules"] == []


class TestExportDecisionDmn:
    """Tests for GET /engagements/{id}/decisions/{id}/dmn."""

    @pytest.mark.asyncio
    async def test_generates_dmn_xml(self) -> None:
        elem = _make_element(
            metadata_json={
                "rules": [
                    {
                        "id": "r1",
                        "rule_text": "Score check",
                        "input_labels": ["Credit Score"],
                        "output_labels": ["Decision"],
                        "input_entries": [">= 700"],
                        "output_entries": ["Approve"],
                        "hit_policy": "FIRST",
                    }
                ]
            }
        )
        session = _mock_session(scalar_one=elem)
        result = await export_decision_dmn(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert "dmn_xml" in result
        assert "<?xml" in result["dmn_xml"]
        assert result["rule_count"] == 1

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        session = _mock_session(scalar_one=None)
        with pytest.raises(Exception) as exc_info:
            await export_decision_dmn(
                engagement_id=uuid.uuid4(),
                decision_id=uuid.uuid4(),
                session=session,
                _user=_mock_user(),
                _engagement_user=_mock_user(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_rules_raises_422(self) -> None:
        elem = _make_element(metadata_json={})
        session = _mock_session(scalar_one=elem)
        with pytest.raises(Exception) as exc_info:
            await export_decision_dmn(
                engagement_id=uuid.uuid4(),
                decision_id=elem.id,
                session=session,
                _user=_mock_user(),
                _engagement_user=_mock_user(),
            )
        assert exc_info.value.status_code == 422


class TestValidateDecisionRule:
    """Tests for POST /engagements/{id}/decisions/{id}/validate."""

    @pytest.mark.asyncio
    async def test_confirm_action(self) -> None:
        elem = _make_element(metadata_json={})
        session = _mock_session(scalar_one=elem)
        payload = ValidateRulePayload(action="confirm")
        result = await validate_decision_rule(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            payload=payload,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["action"] == "confirm"
        assert result["validation_count"] == 1

    @pytest.mark.asyncio
    async def test_correct_action_with_text(self) -> None:
        elem = _make_element(metadata_json={})
        session = _mock_session(scalar_one=elem)
        payload = ValidateRulePayload(
            action="correct",
            corrected_text="Score must be >= 680",
            reasoning="Updated threshold per 2026 guidelines",
        )
        result = await validate_decision_rule(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            payload=payload,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["action"] == "correct"

    @pytest.mark.asyncio
    async def test_confidence_override(self) -> None:
        elem = _make_element(confidence_score=0.5, metadata_json={})
        session = _mock_session(scalar_one=elem)
        payload = ValidateRulePayload(action="confirm", confidence_override=0.95)
        await validate_decision_rule(
            engagement_id=uuid.uuid4(),
            decision_id=elem.id,
            payload=payload,
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert elem.confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self) -> None:
        session = _mock_session(scalar_one=None)
        payload = ValidateRulePayload(action="reject")
        with pytest.raises(Exception) as exc_info:
            await validate_decision_rule(
                engagement_id=uuid.uuid4(),
                decision_id=uuid.uuid4(),
                payload=payload,
                session=session,
                _user=_mock_user(),
                _engagement_user=_mock_user(),
            )
        assert exc_info.value.status_code == 404


class TestGetDecisionCoverage:
    """Tests for GET /engagements/{id}/decisions/coverage."""

    @pytest.mark.asyncio
    async def test_full_coverage(self) -> None:
        elements = [
            _make_element(name="Activity A", metadata_json={"rule_count": 3}),
            _make_element(name="Activity B", metadata_json={"rule_count": 1}),
        ]
        session = _mock_session(elements=elements)
        result = await get_decision_coverage(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["total_activities"] == 2
        assert result["covered"] == 2
        assert result["coverage_percentage"] == 100.0
        assert result["gaps"] == []

    @pytest.mark.asyncio
    async def test_partial_coverage(self) -> None:
        elements = [
            _make_element(name="Covered", metadata_json={"rule_count": 2}),
            _make_element(name="Uncovered", metadata_json={}),
        ]
        session = _mock_session(elements=elements)
        result = await get_decision_coverage(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["covered"] == 1
        assert result["coverage_percentage"] == 50.0
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["activity_name"] == "Uncovered"

    @pytest.mark.asyncio
    async def test_empty_engagement(self) -> None:
        session = _mock_session(elements=[])
        result = await get_decision_coverage(
            engagement_id=uuid.uuid4(),
            session=session,
            _user=_mock_user(),
            _engagement_user=_mock_user(),
        )
        assert result["total_activities"] == 0
        assert result["coverage_percentage"] == 0.0
