"""Route-level tests for Consent Architecture endpoints (Story #382)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.permissions import require_engagement_access
from src.security.consent.models import (
    ConsentStatus,
    EndpointConsentRecord,
    EndpointConsentType,
)

ENGAGEMENT_ID = uuid.uuid4()
PARTICIPANT_ID = uuid.uuid4()
POLICY_BUNDLE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
CONSENT_ID = uuid.uuid4()


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


def _mock_consent_record() -> EndpointConsentRecord:
    record = MagicMock(spec=EndpointConsentRecord)
    record.id = CONSENT_ID
    record.participant_id = PARTICIPANT_ID
    record.engagement_id = ENGAGEMENT_ID
    record.consent_type = EndpointConsentType.OPT_IN
    record.scope = "application-usage-monitoring"
    record.policy_bundle_id = POLICY_BUNDLE_ID
    record.status = ConsentStatus.ACTIVE
    record.recorded_by = USER_ID
    record.recorded_at = datetime(2026, 2, 27, tzinfo=UTC)
    record.withdrawn_at = None
    record.retention_expires_at = datetime(2033, 2, 27, tzinfo=UTC)
    return record


class TestRecordConsent:
    def test_returns_201_for_engagement_lead(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)

        resp = client.post(
            f"/api/v1/consent/engagement/{ENGAGEMENT_ID}",
            json={
                "participant_id": str(PARTICIPANT_ID),
                "consent_type": "opt_in",
                "scope": "application-usage-monitoring",
                "policy_bundle_id": str(POLICY_BUNDLE_ID),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["consent_type"] == "opt_in"
        assert data["status"] == "active"

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)

        resp = client.post(
            f"/api/v1/consent/engagement/{ENGAGEMENT_ID}",
            json={
                "participant_id": str(PARTICIPANT_ID),
                "consent_type": "opt_in",
                "scope": "application-usage-monitoring",
                "policy_bundle_id": str(POLICY_BUNDLE_ID),
            },
        )
        assert resp.status_code == 403


class TestWithdrawConsent:
    def test_returns_200_for_valid_withdrawal(self) -> None:
        mock_session = AsyncMock()
        record = _mock_consent_record()
        mock_session.get = AsyncMock(return_value=record)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.post(f"/api/v1/consent/{CONSENT_ID}/withdraw")

        assert resp.status_code == 200
        data = resp.json()
        assert data["deletion_task_id"] is not None
        assert "postgresql" in data["deletion_targets"]

    def test_returns_404_for_nonexistent(self) -> None:
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.post(f"/api/v1/consent/{uuid.uuid4()}/withdraw")
        assert resp.status_code == 404


class TestQueryConsent:
    def test_returns_200_with_filters(self) -> None:
        mock_session = AsyncMock()
        record = _mock_consent_record()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = [record]
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.get(
            "/api/v1/consent",
            params={"participant_id": str(PARTICIPANT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_analyst_can_read_consent(self) -> None:
        """Process analysts have engagement:read so can query consent."""
        mock_session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = []
        list_result.scalars.return_value = list_scalars

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.get("/api/v1/consent")
        assert resp.status_code == 200


class TestUpdateOrgScope:
    def test_returns_200_with_affected_participants(self) -> None:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        record = _mock_consent_record()
        record.consent_type = EndpointConsentType.ORG_AUTHORIZED

        select_result = MagicMock()
        select_scalars = MagicMock()
        select_scalars.all.return_value = [record]
        select_result.scalars.return_value = select_scalars
        mock_session.execute = AsyncMock(return_value=select_result)

        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.patch(
            f"/api/v1/consent/org/{ENGAGEMENT_ID}",
            json={"new_scope": "screen-content-capture"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_scope"] == "screen-content-capture"
        assert data["notification_required"] is True
