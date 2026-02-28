"""Route-level tests for cohort suppression API endpoints (Story #391)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.core.models import User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = str(uuid.uuid4())


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "lead@example.com"
    user.role = role
    return user


def _make_app(mock_session: AsyncMock, user_role: UserRole = UserRole.ENGAGEMENT_LEAD):
    from src.api.routes.auth import get_current_user

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(user_role)
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _setup_cohort_query(session: AsyncMock, cohort_size: int | None) -> None:
    """Set up mock to return cohort_minimum_size from query.

    _get_minimum selects (Engagement.id, Engagement.cohort_minimum_size)
    and calls one_or_none() which returns a row tuple.
    """
    engagement_id = uuid.UUID(ENGAGEMENT_ID)
    row_result = MagicMock()
    row_result.one_or_none.return_value = (engagement_id, cohort_size)
    session.execute = AsyncMock(return_value=row_result)


# ---------------------------------------------------------------------------
# POST /api/v1/cohort/check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_suppressed() -> None:
    """POST /check with small cohort returns suppressed=true."""
    session = _mock_session()
    _setup_cohort_query(session, 5)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/cohort/check",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "cohort_size": 3,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["suppressed"] is True
    assert data["reason"] == "insufficient_cohort_size"


@pytest.mark.asyncio
async def test_check_not_suppressed() -> None:
    """POST /check with large cohort returns suppressed=false."""
    session = _mock_session()
    _setup_cohort_query(session, 5)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/cohort/check",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "cohort_size": 10,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["suppressed"] is False


# ---------------------------------------------------------------------------
# POST /api/v1/cohort/export-check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_blocked_returns_422() -> None:
    """POST /export-check with small cohort returns 422."""
    session = _mock_session()
    _setup_cohort_query(session, 5)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/cohort/export-check",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "cohort_size": 3,
            },
        )

    assert resp.status_code == 422
    assert "below minimum threshold" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_allowed_returns_200() -> None:
    """POST /export-check with large cohort returns allowed."""
    session = _mock_session()
    _setup_cohort_query(session, 5)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/cohort/export-check",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "cohort_size": 10,
            },
        )

    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/cohort/engagements/{id}/settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_returns_config() -> None:
    """GET /engagements/{id}/settings returns cohort config."""
    session = _mock_session()
    _setup_cohort_query(session, 10)
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/cohort/engagements/{ENGAGEMENT_ID}/settings",
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["cohort_minimum_size"] == 10
    assert data["is_default"] is False
