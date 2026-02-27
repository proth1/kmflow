"""BDD tests for Story #333 — Compliance State Tracking Per Process Element.

Scenario 1: COMPLIANT State When All Required Controls Present
Scenario 2: PARTIALLY_COMPLIANT State with Control Coverage Percentage
Scenario 3: Compliance Trend Available Over Time
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    ComplianceLevel,
    User,
    UserRole,
)
from src.governance.compliance import (
    ComplianceAssessmentService,
    compute_compliance_state,
)

ENGAGEMENT_ID = uuid.uuid4()
ACTIVITY_ID = uuid.uuid4()
MODEL_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes."""
    m = MagicMock()
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_app_with_session(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Unit tests for compute_compliance_state
# ---------------------------------------------------------------------------


class TestComputeComplianceState:
    """Tests for the compliance state computation logic."""

    def test_fully_compliant_all_controls_covered(self) -> None:
        """100% coverage → FULLY_COMPLIANT."""
        state, coverage = compute_compliance_state(3, 3)
        assert state == ComplianceLevel.FULLY_COMPLIANT
        assert coverage == Decimal("100.00")

    def test_partially_compliant_some_controls(self) -> None:
        """60% coverage → PARTIALLY_COMPLIANT."""
        state, coverage = compute_compliance_state(5, 3)
        assert state == ComplianceLevel.PARTIALLY_COMPLIANT
        assert coverage == Decimal("60.00")

    def test_non_compliant_zero_coverage(self) -> None:
        """0% coverage → NON_COMPLIANT."""
        state, coverage = compute_compliance_state(4, 0)
        assert state == ComplianceLevel.NON_COMPLIANT
        assert coverage == Decimal("0.00")

    def test_not_assessed_no_required_controls(self) -> None:
        """No required controls → NOT_ASSESSED."""
        state, coverage = compute_compliance_state(0, 0)
        assert state == ComplianceLevel.NOT_ASSESSED
        assert coverage == Decimal("0.00")

    def test_single_control_covered(self) -> None:
        """1/1 coverage → FULLY_COMPLIANT at 100%."""
        state, coverage = compute_compliance_state(1, 1)
        assert state == ComplianceLevel.FULLY_COMPLIANT
        assert coverage == Decimal("100.00")

    def test_partial_coverage_rounding(self) -> None:
        """2/3 coverage → 66.67% → PARTIALLY_COMPLIANT."""
        state, coverage = compute_compliance_state(3, 2)
        assert state == ComplianceLevel.PARTIALLY_COMPLIANT
        assert coverage == Decimal("66.67")


# ---------------------------------------------------------------------------
# Unit tests for ComplianceAssessmentService
# ---------------------------------------------------------------------------


class TestComplianceAssessmentService:
    """Tests for the service layer."""

    @pytest.mark.asyncio
    async def test_assess_fully_compliant_activity(self) -> None:
        """Scenario 1: All 3 controls have evidence → FULLY_COMPLIANT."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(
            side_effect=[
                # First call: get_required_controls → 3 controls
                [
                    {"control_id": "c1", "control_name": "Identity Check"},
                    {"control_id": "c2", "control_name": "Document Verification"},
                    {"control_id": "c3", "control_name": "Risk Screening"},
                ],
                # Second call: get_controls_with_evidence → all 3 have evidence
                [
                    {"control_id": "c1"},
                    {"control_id": "c2"},
                    {"control_id": "c3"},
                ],
            ]
        )

        service = ComplianceAssessmentService(mock_graph)
        result = await service.assess_activity("act1", "eng1")

        assert result["state"] == ComplianceLevel.FULLY_COMPLIANT
        assert result["control_coverage_percentage"] == Decimal("100.00")
        assert result["total_required_controls"] == 3
        assert result["controls_with_evidence"] == 3
        assert result["gaps"]["missing_controls"] == []

    @pytest.mark.asyncio
    async def test_assess_partially_compliant_activity(self) -> None:
        """Scenario 2: 3/5 controls have evidence → PARTIALLY_COMPLIANT at 60%."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(
            side_effect=[
                # 5 required controls
                [
                    {"control_id": "c1", "control_name": "Control A"},
                    {"control_id": "c2", "control_name": "Control B"},
                    {"control_id": "c3", "control_name": "Control C"},
                    {"control_id": "c4", "control_name": "Control D"},
                    {"control_id": "c5", "control_name": "Control E"},
                ],
                # Only 3 have evidence
                [
                    {"control_id": "c1"},
                    {"control_id": "c3"},
                    {"control_id": "c5"},
                ],
            ]
        )

        service = ComplianceAssessmentService(mock_graph)
        result = await service.assess_activity("act1", "eng1")

        assert result["state"] == ComplianceLevel.PARTIALLY_COMPLIANT
        assert result["control_coverage_percentage"] == Decimal("60.00")
        assert result["total_required_controls"] == 5
        assert result["controls_with_evidence"] == 3

        # Missing controls listed
        missing_ids = [c["control_id"] for c in result["gaps"]["missing_controls"]]
        assert "c2" in missing_ids
        assert "c4" in missing_ids
        assert len(missing_ids) == 2

    @pytest.mark.asyncio
    async def test_assess_non_compliant_activity(self) -> None:
        """All controls missing evidence → NON_COMPLIANT."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(
            side_effect=[
                [{"control_id": "c1", "control_name": "Control A"}],
                [],  # No evidence
            ]
        )

        service = ComplianceAssessmentService(mock_graph)
        result = await service.assess_activity("act1", "eng1")

        assert result["state"] == ComplianceLevel.NON_COMPLIANT
        assert result["control_coverage_percentage"] == Decimal("0.00")
        assert len(result["gaps"]["missing_controls"]) == 1

    @pytest.mark.asyncio
    async def test_assess_no_controls_returns_not_assessed(self) -> None:
        """No ENFORCED_BY edges → NOT_ASSESSED."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(return_value=[])

        service = ComplianceAssessmentService(mock_graph)
        result = await service.assess_activity("act1", "eng1")

        assert result["state"] == ComplianceLevel.NOT_ASSESSED
        assert result["total_required_controls"] == 0

    @pytest.mark.asyncio
    async def test_graph_failure_returns_not_assessed(self) -> None:
        """Graph query failure → NOT_ASSESSED (graceful degradation)."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(side_effect=Exception("Connection refused"))

        service = ComplianceAssessmentService(mock_graph)
        result = await service.assess_activity("act1", "eng1")

        assert result["state"] == ComplianceLevel.NOT_ASSESSED
        assert result["total_required_controls"] == 0


# ---------------------------------------------------------------------------
# API endpoint tests — Trigger Assessment
# ---------------------------------------------------------------------------


class TestTriggerComplianceAssessment:
    """Scenario 1-2: POST /api/v1/governance/activities/{id}/compliance-assessments"""

    @pytest.mark.asyncio
    async def test_trigger_returns_201_with_assessment(self) -> None:
        """Given a valid activity, When POST assessment, Then 201 with state."""
        mock_session = AsyncMock()

        # First call: activity lookup → found
        activity = _make_plain_mock(id=ACTIVITY_ID, model_id=MODEL_ID)
        activity.name = "Customer Identity Verification"
        act_result = MagicMock()
        act_result.scalar_one_or_none.return_value = activity

        # Second call: process model lookup → found
        process_model = _make_plain_mock(id=MODEL_ID, engagement_id=ENGAGEMENT_ID)
        model_result = MagicMock()
        model_result.scalar_one_or_none.return_value = process_model

        mock_session.execute = AsyncMock(side_effect=[act_result, model_result])
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        _added_objects: list[Any] = []

        def _fake_add(obj: Any) -> None:
            _added_objects.append(obj)

        mock_session.add = _fake_add

        app = _make_app_with_session(mock_session)
        app.state.neo4j_driver = MagicMock()

        # Mock the compliance service
        mock_assessment = {
            "state": ComplianceLevel.FULLY_COMPLIANT,
            "control_coverage_percentage": Decimal("100.00"),
            "total_required_controls": 3,
            "controls_with_evidence": 3,
            "gaps": {"missing_controls": []},
        }

        async def _fake_refresh(obj: Any) -> None:
            obj.id = uuid.uuid4()
            obj.assessed_at = datetime.now(UTC)

        mock_session.refresh = _fake_refresh

        with (
            mock.patch(
                "src.api.routes.governance.ComplianceAssessmentService"
            ) as mock_svc_cls,
            mock.patch("src.api.routes.governance.log_audit", new_callable=AsyncMock),
        ):
            mock_svc = AsyncMock()
            mock_svc.assess_activity = AsyncMock(return_value=mock_assessment)
            mock_svc_cls.return_value = mock_svc

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/governance/activities/{ACTIVITY_ID}/compliance-assessments",
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["state"] == "fully_compliant"
        assert data["control_coverage_percentage"] == 100.0
        assert data["total_required_controls"] == 3

    @pytest.mark.asyncio
    async def test_trigger_404_activity_not_found(self) -> None:
        """Returns 404 when activity does not exist."""
        mock_session = AsyncMock()

        act_result = MagicMock()
        act_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=act_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/governance/activities/{ACTIVITY_ID}/compliance-assessments",
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API endpoint tests — Compliance Trend
# ---------------------------------------------------------------------------


class TestComplianceTrend:
    """Scenario 3: GET /api/v1/governance/activities/{id}/compliance-trend"""

    @pytest.mark.asyncio
    async def test_get_trend_chronological_order(self) -> None:
        """Given 3 assessments, When GET trend, Then chronological order."""
        mock_session = AsyncMock()

        # First call: activity exists
        activity = _make_plain_mock(id=ACTIVITY_ID, model_id=MODEL_ID)
        act_result = MagicMock()
        act_result.scalar_one_or_none.return_value = activity

        # Second call: process model lookup (for engagement access check)
        process_model = _make_plain_mock(id=MODEL_ID, engagement_id=ENGAGEMENT_ID)
        pm_result = MagicMock()
        pm_result.scalar_one_or_none.return_value = process_model

        # Third call: assessments
        now = datetime.now(UTC)
        assessments = []
        states = [
            (ComplianceLevel.NON_COMPLIANT, 0.0),
            (ComplianceLevel.PARTIALLY_COMPLIANT, 60.0),
            (ComplianceLevel.FULLY_COMPLIANT, 100.0),
        ]
        for i, (state, coverage) in enumerate(states):
            a = _make_plain_mock(
                id=uuid.uuid4(),
                activity_id=ACTIVITY_ID,
                engagement_id=ENGAGEMENT_ID,
                state=state,
                control_coverage_percentage=Decimal(str(coverage)),
                total_required_controls=3,
                controls_with_evidence=int(coverage / 100 * 3),
                gaps={"missing_controls": []},
                assessed_at=now - timedelta(days=30 * (2 - i)),
                assessed_by=str(USER_ID),
            )
            assessments.append(a)

        assess_result = MagicMock()
        assess_result.scalars.return_value.all.return_value = assessments

        mock_session.execute = AsyncMock(side_effect=[act_result, pm_result, assess_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/activities/{ACTIVITY_ID}/compliance-trend",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["activity_id"] == str(ACTIVITY_ID)

        items = data["assessments"]
        assert len(items) == 3
        assert items[0]["state"] == "non_compliant"
        assert items[1]["state"] == "partially_compliant"
        assert items[2]["state"] == "fully_compliant"

    @pytest.mark.asyncio
    async def test_get_trend_404_activity_not_found(self) -> None:
        """Returns 404 when activity does not exist."""
        mock_session = AsyncMock()

        act_result = MagicMock()
        act_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=act_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/activities/{ACTIVITY_ID}/compliance-trend",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_trend_empty_returns_empty_list(self) -> None:
        """No assessments → empty list."""
        mock_session = AsyncMock()

        activity = _make_plain_mock(id=ACTIVITY_ID, model_id=MODEL_ID)
        act_result = MagicMock()
        act_result.scalar_one_or_none.return_value = activity

        # Process model lookup for engagement access check
        process_model = _make_plain_mock(id=MODEL_ID, engagement_id=ENGAGEMENT_ID)
        pm_result = MagicMock()
        pm_result.scalar_one_or_none.return_value = process_model

        assess_result = MagicMock()
        assess_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[act_result, pm_result, assess_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/activities/{ACTIVITY_ID}/compliance-trend",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["assessments"] == []
