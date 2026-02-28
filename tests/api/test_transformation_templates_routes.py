"""Route-level tests for transformation template endpoints (Story #376)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import (
    SimulationScenario,
    User,
    UserRole,
)

SCENARIO_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.PLATFORM_ADMIN) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_client(mock_session: AsyncMock, user_role: UserRole = UserRole.PLATFORM_ADMIN) -> TestClient:
    app = create_app()
    app.state.neo4j_driver = MagicMock()
    app.state.db_session_factory = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(user_role)
    return TestClient(app)


def _mock_scenario() -> MagicMock:
    s = MagicMock(spec=SimulationScenario)
    s.id = SCENARIO_ID
    s.engagement_id = ENGAGEMENT_ID
    return s


class TestListTemplates:
    """GET /api/v1/templates."""

    def test_returns_all_templates(self) -> None:
        session = AsyncMock()
        client = _make_client(session)

        resp = client.get("/api/v1/templates")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 4
        assert len(data["templates"]) == 4
        types = {t["template_type"] for t in data["templates"]}
        assert "consolidate_tasks" in types
        assert "automate_gateway" in types
        assert "shift_decision" in types
        assert "remove_control" in types


class TestApplyTemplates:
    """POST /api/v1/scenarios/{id}/templates/apply."""

    def test_apply_returns_suggestions(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_result

        client = _make_client(session)

        body = {
            "elements": [
                {
                    "id": "t1", "name": "Task A", "element_type": "task",
                    "lane": "Ops", "performer": "Analyst", "sequence_position": 1,
                },
                {
                    "id": "t2", "name": "Task B", "element_type": "task",
                    "lane": "Ops", "performer": "Analyst", "sequence_position": 2,
                },
            ]
        }

        resp = client.post(f"/api/v1/scenarios/{SCENARIO_ID}/templates/apply", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == str(SCENARIO_ID)
        assert data["suggestion_count"] >= 1
        assert len(data["suggestions"]) >= 1

    def test_empty_elements_returns_no_suggestions(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_result

        client = _make_client(session)

        resp = client.post(
            f"/api/v1/scenarios/{SCENARIO_ID}/templates/apply",
            json={"elements": []},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestion_count"] == 0

    def test_scenario_not_found(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        client = _make_client(session)

        resp = client.post(
            f"/api/v1/scenarios/{uuid.uuid4()}/templates/apply",
            json={"elements": []},
        )

        assert resp.status_code == 404


class TestUpdateSuggestionStatus:
    """PATCH /api/v1/scenarios/{id}/suggestions/{suggestion_id}."""

    def test_accept_suggestion(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_result

        client = _make_client(session)

        resp = client.patch(
            f"/api/v1/scenarios/{SCENARIO_ID}/suggestions/sugg-123",
            json={"action": "accept"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["action"] == "accept"

    def test_reject_suggestion(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_result

        client = _make_client(session)

        resp = client.patch(
            f"/api/v1/scenarios/{SCENARIO_ID}/suggestions/sugg-456",
            json={"action": "reject"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["action"] == "reject"

    def test_invalid_action_returns_422(self) -> None:
        """Pydantic Literal validation rejects invalid action values."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_result

        client = _make_client(session)

        resp = client.patch(
            f"/api/v1/scenarios/{SCENARIO_ID}/suggestions/sugg-789",
            json={"action": "invalid"},
        )

        assert resp.status_code == 422


class TestEngagementAccessControl:
    """IDOR protection — non-members get 403."""

    def test_non_member_gets_403_on_apply(self) -> None:
        session = AsyncMock()
        call_count = 0

        async def side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = _mock_scenario()
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=side_effect)

        client = _make_client(session, user_role=UserRole.PROCESS_ANALYST)

        resp = client.post(
            f"/api/v1/scenarios/{SCENARIO_ID}/templates/apply",
            json={"elements": []},
        )

        assert resp.status_code == 403

    def test_non_member_gets_403_on_suggestion_update(self) -> None:
        session = AsyncMock()
        call_count = 0

        async def side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = _mock_scenario()
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=side_effect)

        client = _make_client(session, user_role=UserRole.PROCESS_ANALYST)

        resp = client.patch(
            f"/api/v1/scenarios/{SCENARIO_ID}/suggestions/sugg-123",
            json={"action": "accept"},
        )

        assert resp.status_code == 403
