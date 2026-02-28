"""Route-level tests for scenario simulation endpoints (Story #380)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import (
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    User,
    UserRole,
)
from src.core.permissions import require_engagement_access

SCENARIO_ID = uuid.uuid4()
SIM_RESULT_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = UserRole.PLATFORM_ADMIN  # bypass engagement member check
    return user


def _make_client(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.state.db_session_factory = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_scenario() -> MagicMock:
    s = MagicMock(spec=SimulationScenario)
    s.id = SCENARIO_ID
    s.name = "Test Scenario"
    s.engagement_id = ENGAGEMENT_ID
    return s


def _mock_sim_result(
    status: SimulationStatus = SimulationStatus.COMPLETED,
) -> MagicMock:
    r = MagicMock(spec=SimulationResult)
    r.id = SIM_RESULT_ID
    r.scenario_id = SCENARIO_ID
    r.status = status
    r.metrics = {"cycle_time_delta_pct": 10.0, "total_fte_delta": -1.0}
    r.impact_analysis = {"per_element_results": [], "confidence_overlay": []}
    r.execution_time_ms = 42
    r.error_message = None
    r.started_at = datetime(2026, 2, 27, 10, 0, tzinfo=UTC)
    r.completed_at = datetime(2026, 2, 27, 10, 1, tzinfo=UTC)
    r.created_at = datetime(2026, 2, 27, 10, 0, tzinfo=UTC)
    return r


class TestTriggerSimulation:
    """POST /api/v1/scenarios/{id}/simulate -> 202 Accepted."""

    @patch("src.api.routes.scenario_simulation._run_simulation_task")
    def test_trigger_returns_202(self, mock_bg_task: MagicMock) -> None:
        session = AsyncMock()

        # _get_scenario loads the scenario; admin bypasses engagement check
        mock_scenario_result = MagicMock()
        mock_scenario_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_scenario_result
        session.commit = AsyncMock()

        async def mock_refresh(obj: SimulationResult) -> None:
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = SIM_RESULT_ID

        session.refresh = mock_refresh

        client = _make_client(session)
        resp = client.post(f"/api/v1/scenarios/{SCENARIO_ID}/simulate")

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert "task_id" in data
        assert data["scenario_id"] == str(SCENARIO_ID)

    def test_trigger_404_for_missing_scenario(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        client = _make_client(session)
        resp = client.post(f"/api/v1/scenarios/{uuid.uuid4()}/simulate")

        assert resp.status_code == 404


class TestSimulationStatus:
    """GET /api/v1/scenarios/{id}/simulation-status."""

    def test_returns_latest_status(self) -> None:
        session = AsyncMock()
        mock_scenario = _mock_scenario()
        mock_sim = _mock_sim_result()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_scenario
            else:
                result.scalar_one_or_none.return_value = mock_sim
            return result

        session.execute = side_effect

        client = _make_client(session)
        resp = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/simulation-status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["scenario_id"] == str(SCENARIO_ID)

    def test_status_404_when_no_simulation(self) -> None:
        session = AsyncMock()
        mock_scenario = _mock_scenario()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_scenario
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = side_effect

        client = _make_client(session)
        resp = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/simulation-status")

        assert resp.status_code == 404


class TestSimulationResults:
    """GET /api/v1/scenarios/{id}/simulation-results."""

    def test_returns_completed_results(self) -> None:
        session = AsyncMock()
        mock_scenario = _mock_scenario()
        mock_sim = _mock_sim_result()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_scenario
            else:
                result.scalar_one_or_none.return_value = mock_sim
            return result

        session.execute = side_effect

        client = _make_client(session)
        resp = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/simulation-results")

        assert resp.status_code == 200
        data = resp.json()
        assert data["metrics"]["cycle_time_delta_pct"] == 10.0
        assert data["metrics"]["total_fte_delta"] == -1.0
        assert data["execution_time_ms"] == 42

    def test_results_404_when_not_completed(self) -> None:
        session = AsyncMock()
        mock_scenario = _mock_scenario()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_scenario
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = side_effect

        client = _make_client(session)
        resp = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/simulation-results")

        assert resp.status_code == 404


class TestEngagementAccessControl:
    """IDOR protection: non-members cannot access simulations."""

    def test_non_member_gets_403(self) -> None:
        """Non-admin, non-member user gets 403."""
        session = AsyncMock()
        mock_scenario = _mock_scenario()

        call_count = 0

        async def side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # _get_scenario returns scenario
                result.scalar_one_or_none.return_value = mock_scenario
            else:
                # _check_engagement_member finds no membership
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = side_effect

        # Non-admin user
        non_admin_user = MagicMock(spec=User)
        non_admin_user.id = uuid.uuid4()
        non_admin_user.email = "outsider@example.com"
        non_admin_user.role = UserRole.PROCESS_ANALYST

        app = create_app()
        app.state.neo4j_driver = MagicMock()
        app.state.db_session_factory = AsyncMock()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: non_admin_user
        app.dependency_overrides[require_engagement_access] = lambda: non_admin_user
        client = TestClient(app)

        resp = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/simulation-status")
        assert resp.status_code == 403
