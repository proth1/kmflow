"""Route-level tests for Survey Session endpoints (Story #319)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.seed_term import SeedTerm, TermCategory
from src.core.models.survey_session import SurveySession, SurveySessionStatus
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()
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


class TestCreateSession:
    def test_returns_201(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions",
            json={"respondent_role": "operations_team"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "active"

    def test_returns_422_for_empty_role(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions",
            json={"respondent_role": ""},
        )
        assert resp.status_code == 422


class TestListSessions:
    def test_returns_200(self) -> None:
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.respondent_role = "operations_team"
        s.status = SurveySessionStatus.ACTIVE
        s.claims_count = 0
        s.created_at = datetime(2026, 2, 27, tzinfo=UTC)
        s.completed_at = None

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [s]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions")
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 1


class TestGetSession:
    def test_returns_200_for_existing(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.respondent_role = "operations_team"
        s.status = SurveySessionStatus.ACTIVE
        s.claims_count = 0
        s.summary = None
        s.created_at = datetime(2026, 2, 27, tzinfo=UTC)
        s.completed_at = None

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = s
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}")
        assert resp.status_code == 200
        assert resp.json()["respondent_role"] == "operations_team"

    def test_returns_404_for_wrong_engagement(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = uuid.uuid4()  # Different engagement

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = s
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.get(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}")
        assert resp.status_code == 404


class TestCompleteSession:
    def test_returns_200_on_completion(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.status = SurveySessionStatus.ACTIVE

        # 3 executes: get_session (route), get_session (service), get claims
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = s

        claims_result = MagicMock()
        claims_scalars = MagicMock()
        claims_scalars.all.return_value = []
        claims_result.scalars.return_value = claims_scalars

        mock_session.execute = AsyncMock(side_effect=[session_result, session_result, claims_result])

        client = _make_app(mock_session)
        resp = client.patch(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


class TestGenerateProbes:
    def test_returns_200_with_probes(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.status = SurveySessionStatus.ACTIVE

        term = MagicMock(spec=SeedTerm)
        term.id = uuid.uuid4()
        term.term = "KYC Review"
        term.domain = "compliance"
        term.category = TermCategory.ACTIVITY

        # 1st: get_session, 2nd: get seed terms
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = s

        terms_result = MagicMock()
        terms_scalars = MagicMock()
        terms_scalars.all.return_value = [term]
        terms_result.scalars.return_value = terms_scalars

        mock_session.execute = AsyncMock(side_effect=[session_result, terms_result])

        client = _make_app(mock_session)
        resp = client.post(f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}/generate-probes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["terms_used"] == 1
        assert data["probes_generated"] == 8


class TestCreateClaim:
    def test_returns_201(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.status = SurveySessionStatus.ACTIVE
        s.respondent_role = "operations_team"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = s
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}/claims",
            json={
                "probe_type": "existence",
                "claim_text": "KYC review happens daily",
                "certainty_tier": "known",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["probe_type"] == "existence"

    def test_returns_422_for_non_active_session(self) -> None:
        mock_session = AsyncMock()

        s = MagicMock(spec=SurveySession)
        s.id = SESSION_ID
        s.engagement_id = ENGAGEMENT_ID
        s.status = SurveySessionStatus.COMPLETED

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = s
        mock_session.execute = AsyncMock(return_value=result_mock)

        client = _make_app(mock_session)
        resp = client.post(
            f"/api/v1/engagements/{ENGAGEMENT_ID}/survey-sessions/{SESSION_ID}/claims",
            json={
                "probe_type": "existence",
                "claim_text": "Test claim",
                "certainty_tier": "known",
            },
        )
        assert resp.status_code == 422
