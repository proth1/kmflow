"""Route-level tests for Data Classification endpoints (Story #317)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.gdpr import (
    RetentionAction,
    RetentionPolicy,
)
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


class TestSetRetentionPolicy:
    def test_returns_200_for_engagement_lead(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        # No existing policy
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.put(
            f"/api/v1/data-classification/retention/{ENGAGEMENT_ID}",
            json={"retention_days": 90, "action": "archive"},
        )
        assert resp.status_code == 200

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.put(
            f"/api/v1/data-classification/retention/{ENGAGEMENT_ID}",
            json={"retention_days": 90},
        )
        assert resp.status_code == 403


class TestGetRetentionPolicy:
    def test_returns_200_when_exists(self) -> None:
        mock_session = AsyncMock()
        policy = MagicMock(spec=RetentionPolicy)
        policy.id = uuid.uuid4()
        policy.engagement_id = ENGAGEMENT_ID
        policy.retention_days = 90
        policy.action = RetentionAction.ARCHIVE

        result = MagicMock()
        result.scalar_one_or_none.return_value = policy
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.get(f"/api/v1/data-classification/retention/{ENGAGEMENT_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["retention_days"] == 90

    def test_returns_404_when_not_exists(self) -> None:
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.get(f"/api/v1/data-classification/retention/{ENGAGEMENT_ID}")
        assert resp.status_code == 404


class TestCreateProcessingActivity:
    def test_returns_201_for_valid_activity(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.post(
            f"/api/v1/data-classification/processing-activities/{ENGAGEMENT_ID}",
            json={
                "name": "Evidence ingestion",
                "lawful_basis": "legitimate_interests",
                "article_6_basis": "Art. 6(1)(f)",
            },
        )
        assert resp.status_code == 201

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.post(
            f"/api/v1/data-classification/processing-activities/{ENGAGEMENT_ID}",
            json={
                "name": "Evidence ingestion",
                "lawful_basis": "consent",
            },
        )
        assert resp.status_code == 403
