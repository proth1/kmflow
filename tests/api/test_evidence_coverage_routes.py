"""Route-level tests for Evidence Coverage endpoints (Story #385)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.pov import BrightnessClassification
from src.core.models.simulation import ScenarioModification, SimulationScenario
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.PROCESS_ANALYST) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "analyst@example.com"
    user.role = role
    return user


def _make_app(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _setup_coverage_query(mock_session: AsyncMock) -> None:
    """Set up mock session for a single-element coverage query."""
    scenario = MagicMock(spec=SimulationScenario)
    scenario.id = SCENARIO_ID
    scenario.engagement_id = ENGAGEMENT_ID

    mod = MagicMock(spec=ScenarioModification)
    mod.element_id = "elem-1"
    mod.element_name = "Review Task"

    scenario_result = MagicMock()
    scenario_result.scalar_one_or_none.return_value = scenario

    mods_result = MagicMock()
    mods_scalars = MagicMock()
    mods_scalars.all.return_value = [mod]
    mods_result.scalars.return_value = mods_scalars

    brightness_result = MagicMock()
    brightness_result.all.return_value = [("elem-1", BrightnessClassification.BRIGHT)]

    mock_session.execute = AsyncMock(
        side_effect=[scenario_result, mods_result, brightness_result]
    )


class TestGetEvidenceCoverage:
    def test_returns_200(self) -> None:
        mock_session = AsyncMock()
        _setup_coverage_query(mock_session)
        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/scenarios/{SCENARIO_ID}/evidence-coverage",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == str(SCENARIO_ID)
        assert len(data["modified_elements"]) == 1
        assert "coverage_summary" in data

    def test_not_found_returns_404(self) -> None:
        mock_session = AsyncMock()
        scenario_result = MagicMock()
        scenario_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=scenario_result)
        client = _make_app(mock_session)
        resp = client.get(
            f"/api/v1/scenarios/{SCENARIO_ID}/evidence-coverage",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 404


class TestCompareEvidenceCoverage:
    def test_requires_at_least_two_ids(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.get(
            "/api/v1/scenarios/compare/evidence-coverage",
            params={
                "scenario_ids": str(SCENARIO_ID),
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 422

    def test_invalid_uuid_returns_422(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.get(
            "/api/v1/scenarios/compare/evidence-coverage",
            params={
                "scenario_ids": "not-a-uuid,also-bad",
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 422

    def test_exceeds_max_scenarios_returns_422(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        ids = ",".join(str(uuid.uuid4()) for _ in range(11))
        resp = client.get(
            "/api/v1/scenarios/compare/evidence-coverage",
            params={
                "scenario_ids": ids,
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 422
        assert "Maximum" in resp.json()["detail"]
