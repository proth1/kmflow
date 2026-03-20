"""Route-level tests for audit log query endpoints.

Tests the /api/v1/audit-logs endpoints for filtering, pagination,
and role-based access control (PLATFORM_ADMIN only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.routes.auth import get_current_user
from src.core.models import AuditAction, AuditLog, User, UserRole

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
LOG_ID = uuid.uuid4()


def _mock_user(role: UserRole = UserRole.PLATFORM_ADMIN) -> User:
    user = MagicMock(spec=User)
    user.id = USER_ID
    user.email = "admin@example.com"
    user.role = role
    return user


def _make_app(
    mock_session: AsyncMock,
    role: UserRole = UserRole.PLATFORM_ADMIN,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(role)
    return TestClient(app)


def _make_audit_log() -> MagicMock:
    entry = MagicMock(spec=AuditLog)
    entry.id = LOG_ID
    entry.engagement_id = ENGAGEMENT_ID
    entry.action = AuditAction.CREATE
    entry.actor = "admin@example.com"
    entry.details = "Created evidence item"
    entry.user_id = USER_ID
    entry.resource_type = "evidence"
    entry.resource_id = uuid.uuid4()
    entry.before_value = None
    entry.after_value = None
    entry.ip_address = "127.0.0.1"
    entry.user_agent = "test-agent"
    entry.result_status = 200
    entry.created_at = datetime(2026, 3, 1, tzinfo=UTC)
    return entry


def _setup_list_query(mock_session: AsyncMock, entries: list | None = None) -> None:
    if entries is None:
        entries = [_make_audit_log()]

    count_result = MagicMock()
    count_result.scalar.return_value = len(entries)

    list_result = MagicMock()
    list_scalars = MagicMock()
    list_scalars.all.return_value = entries
    list_result.scalars.return_value = list_scalars

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])


class TestListAuditLogs:
    def test_returns_200_for_platform_admin(self) -> None:
        mock_session = AsyncMock()
        _setup_list_query(mock_session)
        client = _make_app(mock_session, UserRole.PLATFORM_ADMIN)
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 1

    def test_returns_403_for_engagement_lead(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.ENGAGEMENT_LEAD)
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 403

    def test_returns_403_for_analyst(self) -> None:
        mock_session = AsyncMock()
        client = _make_app(mock_session, UserRole.PROCESS_ANALYST)
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 403

    def test_returns_empty_list(self) -> None:
        mock_session = AsyncMock()
        _setup_list_query(mock_session, entries=[])
        client = _make_app(mock_session, UserRole.PLATFORM_ADMIN)
        resp = client.get("/api/v1/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_pagination_params(self) -> None:
        mock_session = AsyncMock()
        _setup_list_query(mock_session)
        client = _make_app(mock_session, UserRole.PLATFORM_ADMIN)
        resp = client.get("/api/v1/audit-logs", params={"limit": 5, "offset": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 5
        assert data["offset"] == 10

    def test_filter_by_engagement_id(self) -> None:
        mock_session = AsyncMock()
        _setup_list_query(mock_session)
        client = _make_app(mock_session, UserRole.PLATFORM_ADMIN)
        resp = client.get(
            "/api/v1/audit-logs",
            params={"engagement_id": str(ENGAGEMENT_ID)},
        )
        assert resp.status_code == 200

    def test_filter_by_resource_type(self) -> None:
        mock_session = AsyncMock()
        _setup_list_query(mock_session)
        client = _make_app(mock_session, UserRole.PLATFORM_ADMIN)
        resp = client.get(
            "/api/v1/audit-logs",
            params={"resource_type": "evidence"},
        )
        assert resp.status_code == 200
