"""Route-level tests for sensitivity analysis endpoints (Story #364)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import FinancialAssumption, User, UserRole
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


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


def _mock_assumption(name: str, value: float, confidence: float, confidence_range: float) -> MagicMock:
    a = MagicMock(spec=FinancialAssumption)
    a.name = name
    a.value = value
    a.confidence = confidence
    a.confidence_range = confidence_range
    return a


class TestSensitivityRoute:
    def test_sensitivity_returns_ranked_entries(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            _mock_assumption("volume", 100_000, 0.7, 30.0),
            _mock_assumption("rate", 150, 0.9, 10.0),
        ]
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/sensitivity")

        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert len(data["entries"]) == 2
        assert data["entries"][0]["rank"] == 1

    def test_sensitivity_no_assumptions_404(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/sensitivity")

        assert resp.status_code == 404


class TestTornadoRoute:
    def test_tornado_chart_returns_items(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            _mock_assumption("cost_a", 10_000, 0.8, 20.0),
            _mock_assumption("cost_b", 5_000, 0.7, 25.0),
        ]
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/tornado")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 2
        assert data["items"][0]["rank"] == 1

    def test_tornado_entry_has_all_fields(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            _mock_assumption("single", 1_000, 0.8, 20.0),
        ]
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/tornado")

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in ("assumption_name", "baseline_cost", "low_cost", "high_cost", "swing_magnitude", "rank"):
            assert field in item


class TestPercentileRoute:
    def test_percentiles_p10_lt_p50_lt_p90(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            _mock_assumption("vol", 10_000, 0.7, 20.0),
            _mock_assumption("rate", 5_000, 0.8, 15.0),
        ]
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/percentiles")

        assert resp.status_code == 200
        data = resp.json()
        assert data["p10"] < data["p50"]
        assert data["p50"] < data["p90"]

    def test_percentiles_no_assumptions_404(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result
        client = _make_client(session)

        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/financial-analysis/percentiles")

        assert resp.status_code == 404
