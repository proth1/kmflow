"""Route-level tests for suggestion feedback endpoints (Story #390)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import (
    SimulationScenario,
    User,
    UserRole,
)
from src.core.permissions import require_engagement_access

SCENARIO_ID = uuid.uuid4()
MODIFICATION_ID = uuid.uuid4()
ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "lead@example.com"
    user.role = UserRole.PLATFORM_ADMIN
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
    s.engagement_id = ENGAGEMENT_ID
    return s


class TestTraceabilityRoute:
    """GET /api/v1/scenarios/{id}/modifications/{mid}/traceability."""

    @patch("src.api.routes.suggestion_feedback.build_traceability_chain")
    def test_returns_full_chain(self, mock_chain: MagicMock) -> None:
        session = AsyncMock()
        mock_scenario_result = MagicMock()
        mock_scenario_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_scenario_result

        mock_chain.return_value = {
            "modification": {"id": str(MODIFICATION_ID)},
            "suggestion": {"id": str(uuid.uuid4())},
            "audit_log": {"id": str(uuid.uuid4())},
            "traceability_complete": True,
        }

        client = _make_client(session)
        resp = client.get(
            f"/api/v1/scenarios/{SCENARIO_ID}/modifications/{MODIFICATION_ID}/traceability"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["traceability_complete"] is True

    @patch("src.api.routes.suggestion_feedback.build_traceability_chain")
    def test_returns_404_for_missing_modification(self, mock_chain: MagicMock) -> None:
        session = AsyncMock()
        mock_scenario_result = MagicMock()
        mock_scenario_result.scalar_one_or_none.return_value = _mock_scenario()
        session.execute.return_value = mock_scenario_result

        mock_chain.return_value = None

        client = _make_client(session)
        resp = client.get(
            f"/api/v1/scenarios/{SCENARIO_ID}/modifications/{uuid.uuid4()}/traceability"
        )

        assert resp.status_code == 404

    def test_returns_404_for_missing_scenario(self) -> None:
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        client = _make_client(session)
        resp = client.get(
            f"/api/v1/scenarios/{uuid.uuid4()}/modifications/{MODIFICATION_ID}/traceability"
        )

        assert resp.status_code == 404


class TestRejectionFeedbackRoute:
    """GET /api/v1/engagements/{id}/rejection-feedback."""

    @patch("src.api.routes.suggestion_feedback.get_rejection_patterns")
    def test_lists_patterns(self, mock_patterns: MagicMock) -> None:
        session = AsyncMock()
        mock_patterns.return_value = ["Pattern A", "Pattern B"]

        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/rejection-feedback")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rejection_count"] == 2
        assert data["patterns"] == ["Pattern A", "Pattern B"]

    @patch("src.api.routes.suggestion_feedback.get_rejection_patterns")
    def test_empty_patterns(self, mock_patterns: MagicMock) -> None:
        session = AsyncMock()
        mock_patterns.return_value = []

        client = _make_client(session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/rejection-feedback")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rejection_count"] == 0
        assert data["patterns"] == []


class TestExclusionPromptRoute:
    """GET /api/v1/engagements/{id}/rejection-feedback/exclusion-prompt."""

    @patch("src.api.routes.suggestion_feedback.get_rejection_patterns")
    def test_returns_formatted_prompt(self, mock_patterns: MagicMock) -> None:
        session = AsyncMock()
        mock_patterns.return_value = ["Automate using RPA", "Remove quality checks"]

        client = _make_client(session)
        resp = client.get(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/rejection-feedback/exclusion-prompt"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pattern_count"] == 2
        assert "previously rejected" in data["exclusion_prompt"]

    @patch("src.api.routes.suggestion_feedback.get_rejection_patterns")
    def test_empty_prompt_when_no_rejections(self, mock_patterns: MagicMock) -> None:
        session = AsyncMock()
        mock_patterns.return_value = []

        client = _make_client(session)
        resp = client.get(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/rejection-feedback/exclusion-prompt"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["exclusion_prompt"] == ""


class TestEngagementAccessControl:
    """IDOR protection tests — non-members get 403."""

    @patch("src.api.routes.suggestion_feedback.get_rejection_patterns")
    def test_non_member_gets_403_on_rejection_feedback(self, mock_patterns: MagicMock) -> None:
        """Non-admin user who is NOT an engagement member should be denied."""
        session = AsyncMock()
        # Membership check returns None → not a member
        mock_member_result = MagicMock()
        mock_member_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_member_result

        # Create a non-admin user
        non_admin = MagicMock(spec=User)
        non_admin.id = uuid.uuid4()
        non_admin.email = "analyst@example.com"
        non_admin.role = UserRole.PROCESS_ANALYST

        app = create_app()
        app.state.neo4j_driver = MagicMock()
        app.state.db_session_factory = AsyncMock()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: non_admin
        client = TestClient(app)

        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/rejection-feedback")
        assert resp.status_code == 403

    @patch("src.api.routes.suggestion_feedback.build_traceability_chain")
    def test_non_member_gets_403_on_traceability(self, mock_chain: MagicMock) -> None:
        """Non-admin user who is NOT an engagement member should be denied on traceability."""
        session = AsyncMock()
        call_count = 0

        async def side_effect(*_args: Any, **_kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # First call: load scenario
                result.scalar_one_or_none.return_value = _mock_scenario()
            else:
                # Second call: membership check → not a member
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=side_effect)

        non_admin = MagicMock(spec=User)
        non_admin.id = uuid.uuid4()
        non_admin.email = "analyst@example.com"
        non_admin.role = UserRole.PROCESS_ANALYST

        app = create_app()
        app.state.neo4j_driver = MagicMock()
        app.state.db_session_factory = AsyncMock()
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: non_admin
        client = TestClient(app)

        resp = client.get(
            f"/api/v1/scenarios/{SCENARIO_ID}/modifications/{MODIFICATION_ID}/traceability"
        )
        assert resp.status_code == 403
