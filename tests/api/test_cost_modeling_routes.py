"""Route-level tests for Cost-Per-Role and Volume Forecast Modeling (Story #359).

Tests the engagement-scoped cost modeling endpoints.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import RoleRateAssumption, User, UserRole, VolumeForecast
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
RATE_ID = uuid.uuid4()
FORECAST_ID = uuid.uuid4()


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = UserRole.ENGAGEMENT_LEAD
    return user


def _make_client(mock_session: AsyncMock) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user()
    return TestClient(app)


def _mock_rate() -> MagicMock:
    rate = MagicMock(spec=RoleRateAssumption)
    rate.id = RATE_ID
    rate.engagement_id = ENGAGEMENT_ID
    rate.role_name = "Analyst"
    rate.hourly_rate = 100.0
    rate.annual_rate = None
    rate.rate_variance_pct = 10.0
    rate.created_at = None
    return rate


def _mock_forecast() -> MagicMock:
    forecast = MagicMock(spec=VolumeForecast)
    forecast.id = FORECAST_ID
    forecast.engagement_id = ENGAGEMENT_ID
    forecast.name = "Monthly transactions"
    forecast.baseline_volume = 1000
    forecast.variance_pct = 15.0
    forecast.seasonal_factors = {"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115}
    forecast.created_at = None
    return forecast


class TestRoleRateRoutes:
    """CRUD for role rate assumptions."""

    def test_create_role_rate_returns_201(self) -> None:
        session = AsyncMock()
        rate = _mock_rate()
        session.refresh = AsyncMock()
        client = _make_client(session)
        # After session.add and commit/refresh, the endpoint serializes the object.
        # We patch to control what gets returned.
        with patch("src.api.routes.cost_modeling.RoleRateAssumption", return_value=rate):
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/role-rates",
                json={"role_name": "Analyst", "hourly_rate": 100.0, "rate_variance_pct": 10.0},
            )
        assert resp.status_code == 201
        assert resp.json()["role_name"] == "Analyst"

    def test_list_role_rates(self) -> None:
        rate = _mock_rate()
        session = AsyncMock()
        result_mock = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[rate])
        result_mock.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/role-rates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["hourly_rate"] == 100.0


class TestVolumeForecastRoutes:
    """CRUD for volume forecasts."""

    def test_create_volume_forecast_returns_201(self) -> None:
        session = AsyncMock()
        forecast = _mock_forecast()
        session.refresh = AsyncMock()
        client = _make_client(session)
        with patch("src.api.routes.cost_modeling.VolumeForecast", return_value=forecast):
            resp = client.post(
                f"/api/v1/engagements/{ENGAGEMENT_ID}/volume-forecasts",
                json={
                    "name": "Monthly transactions",
                    "baseline_volume": 1000,
                    "variance_pct": 15.0,
                    "seasonal_factors": {"Q1": 80, "Q2": 110, "Q3": 95, "Q4": 115},
                },
            )
        assert resp.status_code == 201
        assert resp.json()["baseline_volume"] == 1000

    def test_list_volume_forecasts(self) -> None:
        forecast = _mock_forecast()
        session = AsyncMock()
        result_mock = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[forecast])
        result_mock.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/volume-forecasts")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestStaffingCostRoute:
    """POST /cost-modeling/staffing"""

    def test_staffing_cost_computation(self) -> None:
        rate = _mock_rate()
        session = AsyncMock()
        result_mock = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[rate])
        result_mock.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/cost-modeling/staffing",
            json={
                "task_assignments": [
                    {"role_name": "Analyst", "task_count": 5, "avg_hours_per_task": 2.0},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"]["mid"] == 1000.0
        assert data["total"]["low"] < data["total"]["high"]

    def test_staffing_no_rates_returns_404(self) -> None:
        session = AsyncMock()
        result_mock = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        result_mock.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/cost-modeling/staffing",
            json={"task_assignments": [{"role_name": "Analyst", "task_count": 1, "avg_hours_per_task": 1.0}]},
        )
        assert resp.status_code == 404


class TestVolumeCostRoute:
    """POST /cost-modeling/volume"""

    @patch("src.api.routes.cost_modeling._get_forecast")
    def test_volume_cost_computation(self, mock_get_forecast) -> None:
        forecast = _mock_forecast()
        mock_get_forecast.return_value = forecast

        session = AsyncMock()
        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/cost-modeling/volume",
            json={"forecast_id": str(FORECAST_ID), "per_transaction_cost": 10.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cost_range"]["mid"] == 10000.0


class TestFteSavingsRoute:
    """POST /cost-modeling/fte-savings"""

    def test_fte_savings_computation(self) -> None:
        rate = _mock_rate()
        session = AsyncMock()
        result_mock = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[rate])
        result_mock.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/cost-modeling/fte-savings",
            json={
                "as_is_tasks": [{"role_name": "Analyst", "task_count": 4, "avg_hours_per_task": 2.0}],
                "to_be_tasks": [{"role_name": "Analyst", "task_count": 2, "avg_hours_per_task": 2.0}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["savings"]["mid"] == 400.0
