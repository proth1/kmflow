"""Route-level tests for Governance Flag Detection (Story #381)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import AlternativeSuggestion, User, UserRole
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
SCENARIO_ID = uuid.uuid4()
SUGGESTION_ID = uuid.uuid4()
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


class TestGovernanceCheckRoute:
    """POST .../governance-check"""

    def test_sod_flag_returned(self) -> None:
        suggestion = MagicMock(spec=AlternativeSuggestion)
        suggestion.id = SUGGESTION_ID
        suggestion.scenario_id = SCENARIO_ID
        suggestion.governance_flags = None

        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=suggestion)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}/governance-check",
            json={
                "role_changes": [
                    {"type": "merge", "roles": ["Approver", "Processor"]}
                ],
                "affected_element_ids": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_count"] == 1
        assert data["governance_flags"][0]["flag_type"] == "segregation_of_duties"

    def test_no_flags_returns_empty(self) -> None:
        suggestion = MagicMock(spec=AlternativeSuggestion)
        suggestion.id = SUGGESTION_ID
        suggestion.scenario_id = SCENARIO_ID
        suggestion.governance_flags = None

        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=suggestion)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}/governance-check",
            json={
                "role_changes": [],
                "affected_element_ids": [],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_count"] == 0
        assert data["governance_flags"] == []

    def test_suggestion_not_found_returns_404(self) -> None:
        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/scenarios/{SCENARIO_ID}/suggestions/{uuid.uuid4()}/governance-check",
            json={"role_changes": [], "affected_element_ids": []},
        )
        assert resp.status_code == 404

    def test_regulatory_flag_with_custom_elements(self) -> None:
        suggestion = MagicMock(spec=AlternativeSuggestion)
        suggestion.id = SUGGESTION_ID
        suggestion.scenario_id = SCENARIO_ID
        suggestion.governance_flags = None

        session = AsyncMock()
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=suggestion)
        session.execute = AsyncMock(return_value=result_mock)

        client = _make_client(session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}/governance-check",
            json={
                "role_changes": [
                    {"type": "automate", "element_id": "task_approve", "element_name": "Final Approval"}
                ],
                "affected_element_ids": [],
                "regulated_elements": {"task_approve": ["SOX Section 302"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["flag_count"] == 1
        assert data["governance_flags"][0]["regulation_reference"] == "SOX Section 302"
