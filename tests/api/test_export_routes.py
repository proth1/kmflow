"""Route-level tests for Export Watermarking endpoints (Story #387)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import User, UserRole
from src.core.models.export_log import ExportLog
from src.core.permissions import require_engagement_access

ENGAGEMENT_ID = uuid.uuid4()
EXPORT_ID = uuid.uuid4()
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


def _setup_export_logs_query(mock_session: AsyncMock) -> None:
    """Set up mock for paginated export logs query."""
    log_entry = MagicMock(spec=ExportLog)
    log_entry.id = EXPORT_ID
    log_entry.recipient_id = USER_ID
    log_entry.document_type = "PDF"
    log_entry.engagement_id = ENGAGEMENT_ID
    log_entry.exported_at = datetime(2026, 2, 27, tzinfo=UTC)

    count_result = MagicMock()
    count_result.scalar.return_value = 1

    list_result = MagicMock()
    list_scalars = MagicMock()
    list_scalars.all.return_value = [log_entry]
    list_result.scalars.return_value = list_scalars

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])


class TestListExports:
    def test_returns_200_for_engagement_lead(self) -> None:
        mock_session = AsyncMock()
        _setup_export_logs_query(mock_session)
        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.get(
            "/api/v1/exports",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.get(
            "/api/v1/exports",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 403


class TestExtractWatermark:
    def test_returns_422_for_invalid_watermark(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.post(
            "/api/v1/exports/extract-watermark",
            json={"encoded_watermark": "garbage"},
        )
        assert resp.status_code == 422

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.post(
            "/api/v1/exports/extract-watermark",
            json={"encoded_watermark": "anything"},
        )
        assert resp.status_code == 403
