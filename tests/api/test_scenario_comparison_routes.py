"""Route-level tests for Scenario Comparison endpoint (Story #383)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_app(
    mock_session: AsyncMock,
    role: UserRole = UserRole.ENGAGEMENT_LEAD,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(role)
    app.dependency_overrides[require_engagement_access] = lambda: _mock_user(role)
    return TestClient(app)


class TestCompareScenarios:
    def test_returns_422_for_single_id(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.get(
            "/api/v1/scenarios/compare",
            params={
                "ids": str(uuid.uuid4()),
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 422
        assert "At least 2" in resp.json()["detail"]

    def test_returns_422_for_6_ids(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        ids = ",".join(str(uuid.uuid4()) for _ in range(6))
        resp = client.get(
            "/api/v1/scenarios/compare",
            params={"ids": ids, "engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 422
        assert "At most 5" in resp.json()["detail"]

    def test_returns_422_for_invalid_uuid(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.get(
            "/api/v1/scenarios/compare",
            params={
                "ids": "not-a-uuid,also-bad",
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 422

    def test_returns_403_for_client_viewer(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.CLIENT_VIEWER)
        ids = ",".join(str(uuid.uuid4()) for _ in range(2))
        resp = client.get(
            "/api/v1/scenarios/compare",
            params={"ids": ids, "engagement_id": str(ENGAGEMENT_ID)},
        )
        # client_viewer doesn't have simulation:read → 403
        assert resp.status_code == 403

    def test_returns_409_for_incomplete_simulation(self) -> None:
        """Scenarios without completed simulation return 409."""
        sid_a, sid_b = uuid.uuid4(), uuid.uuid4()

        mock_session = AsyncMock()

        # Scenarios found but no results
        from src.core.models.simulation import SimulationScenario

        s_a = MagicMock(spec=SimulationScenario)
        s_a.id = sid_a
        s_a.engagement_id = ENGAGEMENT_ID
        s_a.name = "A"
        s_a.evidence_confidence_score = 0.8

        s_b = MagicMock(spec=SimulationScenario)
        s_b.id = sid_b
        s_b.engagement_id = ENGAGEMENT_ID
        s_b.name = "B"
        s_b.evidence_confidence_score = 0.7

        scenarios_result = MagicMock()
        scenarios_scalars = MagicMock()
        scenarios_scalars.all.return_value = [s_a, s_b]
        scenarios_result.scalars.return_value = scenarios_scalars

        # No simulation results
        results_result = MagicMock()
        results_scalars = MagicMock()
        results_scalars.all.return_value = []
        results_result.scalars.return_value = results_scalars

        mock_session.execute = AsyncMock(side_effect=[scenarios_result, results_result])

        client = _make_app(mock_session)
        resp = client.get(
            "/api/v1/scenarios/compare",
            params={
                "ids": f"{sid_a},{sid_b}",
                "engagement_id": str(ENGAGEMENT_ID),
            },
        )
        assert resp.status_code == 409
        assert "without completed simulation" in resp.json()["detail"]
