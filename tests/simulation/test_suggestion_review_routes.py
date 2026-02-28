"""Route-level tests for Suggestion Review Workflow (Story #379).

Tests the PATCH /api/v1/simulations/scenarios/{id}/suggestions/{suggestion_id}
endpoint with all disposition types and validation.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import (
    AlternativeSuggestion,
    SimulationScenario,
    SuggestionDisposition,
    User,
    UserRole,
)
from src.core.permissions import require_permission

SCENARIO_ID = uuid.uuid4()
SUGGESTION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()


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
    # Override require_permission to bypass auth
    app.dependency_overrides[require_permission("simulation:create")] = lambda: _mock_user()
    return TestClient(app)


def _mock_scenario() -> MagicMock:
    s = MagicMock(spec=SimulationScenario)
    s.id = SCENARIO_ID
    s.engagement_id = ENGAGEMENT_ID
    s.name = "Test Scenario"
    return s


def _mock_suggestion(
    disposition: SuggestionDisposition = SuggestionDisposition.PENDING,
) -> MagicMock:
    s = MagicMock(spec=AlternativeSuggestion)
    s.id = SUGGESTION_ID
    s.scenario_id = SCENARIO_ID
    s.suggestion_text = "Add validation gateway"
    s.rationale = "Reduces errors"
    s.disposition = disposition
    s.disposition_notes = None
    s.modified_content = None
    s.disposed_at = None
    s.disposed_by_user_id = None
    s.governance_flags = None
    s.evidence_gaps = None
    return s


class TestSuggestionReviewRoutes:
    """PATCH /api/v1/simulations/scenarios/{id}/suggestions/{suggestion_id}"""

    @patch("src.api.routes.simulations.review_suggestion")
    @patch("src.api.routes.simulations.log_audit")
    @patch("src.api.routes.simulations.get_scenario_or_404")
    def test_accept_returns_200(self, mock_get_scenario, mock_audit, mock_review) -> None:
        """ACCEPTED returns success with modification_id."""
        mock_get_scenario.return_value = _mock_scenario()
        mock_review.return_value = {
            "suggestion_id": str(SUGGESTION_ID),
            "disposition": "accepted",
            "disposed_at": "2026-02-27T00:00:00+00:00",
            "modification_id": str(uuid.uuid4()),
        }
        mock_audit.return_value = None

        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={"disposition": "accepted"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["disposition"] == "accepted"
        assert data["modification_id"] is not None

    @patch("src.api.routes.simulations.review_suggestion")
    @patch("src.api.routes.simulations.log_audit")
    @patch("src.api.routes.simulations.get_scenario_or_404")
    def test_modified_returns_200(self, mock_get_scenario, mock_audit, mock_review) -> None:
        """MODIFIED with content returns success."""
        mock_get_scenario.return_value = _mock_scenario()
        mock_review.return_value = {
            "suggestion_id": str(SUGGESTION_ID),
            "disposition": "modified",
            "disposed_at": "2026-02-27T00:00:00+00:00",
            "modification_id": str(uuid.uuid4()),
        }
        mock_audit.return_value = None

        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={
                "disposition": "modified",
                "modified_content": {"name": "Adjusted gateway"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["disposition"] == "modified"

    @patch("src.api.routes.simulations.review_suggestion")
    @patch("src.api.routes.simulations.log_audit")
    @patch("src.api.routes.simulations.get_scenario_or_404")
    def test_rejected_returns_200(self, mock_get_scenario, mock_audit, mock_review) -> None:
        """REJECTED with reason returns success."""
        mock_get_scenario.return_value = _mock_scenario()
        mock_review.return_value = {
            "suggestion_id": str(SUGGESTION_ID),
            "disposition": "rejected",
            "disposed_at": "2026-02-27T00:00:00+00:00",
            "modification_id": None,
        }
        mock_audit.return_value = None

        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={
                "disposition": "rejected",
                "rejection_reason": "Not aligned with goals",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["disposition"] == "rejected"
        assert data["modification_id"] is None

    def test_modified_without_content_returns_422(self) -> None:
        """MODIFIED without modified_content returns 422."""
        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={"disposition": "modified"},
        )
        assert resp.status_code == 422
        assert "modified_content" in resp.json()["detail"].lower()

    def test_rejected_without_reason_returns_422(self) -> None:
        """REJECTED without rejection_reason returns 422."""
        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={"disposition": "rejected"},
        )
        assert resp.status_code == 422
        assert "rejection_reason" in resp.json()["detail"].lower()

    @patch("src.api.routes.simulations.review_suggestion")
    @patch("src.api.routes.simulations.log_audit")
    @patch("src.api.routes.simulations.get_scenario_or_404")
    def test_not_found_returns_404(self, mock_get_scenario, mock_audit, mock_review) -> None:
        """Non-existent suggestion returns 404."""
        mock_get_scenario.return_value = _mock_scenario()
        mock_review.side_effect = ValueError("Suggestion not found")
        mock_audit.return_value = None

        session = AsyncMock()
        client = _make_client(session)
        resp = client.patch(
            f"/api/v1/simulations/scenarios/{SCENARIO_ID}/suggestions/{SUGGESTION_ID}",
            json={"disposition": "accepted"},
        )
        assert resp.status_code == 404
