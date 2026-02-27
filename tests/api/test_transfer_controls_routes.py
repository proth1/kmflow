"""Route-level tests for transfer control API endpoints (Story #395)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.core.models import TIAStatus, TransferDecision, User, UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENGAGEMENT_ID = str(uuid.uuid4())


def _mock_user() -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "dpo@example.com"
    user.role = UserRole.PLATFORM_ADMIN
    return user


def _make_app(mock_session: AsyncMock):
    from src.api.routes.auth import get_current_user

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    app.state.neo4j_driver = MagicMock()
    return app


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# POST /api/v1/transfer-controls/evaluate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_transfer_no_restriction_permits() -> None:
    """POST /evaluate with NONE restriction returns PERMITTED."""
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/transfer-controls/evaluate",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "connector_id": "anthropic",
                "data_residency": "none",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == TransferDecision.PERMITTED
    assert data["reason"] == "no_residency_restriction"


@pytest.mark.asyncio
async def test_evaluate_transfer_eu_only_blocked() -> None:
    """POST /evaluate with EU_ONLY and no TIA returns BLOCKED_NO_TIA."""
    session = _mock_session()

    no_tia_result = MagicMock()
    no_tia_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_tia_result)

    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/transfer-controls/evaluate",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "connector_id": "anthropic",
                "data_residency": "eu_only",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == TransferDecision.BLOCKED_NO_TIA


# ---------------------------------------------------------------------------
# POST /api/v1/transfer-controls/tia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tia_returns_201() -> None:
    """POST /tia creates a TIA and returns 201."""
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/transfer-controls/tia",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "connector_id": "anthropic",
                "assessor": "dpo_user",
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == TIAStatus.PENDING
    assert data["destination_jurisdiction"] == "US"


# ---------------------------------------------------------------------------
# POST /api/v1/transfer-controls/tia/{id}/approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_tia_not_found_returns_404() -> None:
    """POST /tia/{id}/approve for non-existent TIA returns 404."""
    session = _mock_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    app = _make_app(session)
    fake_id = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/transfer-controls/tia/{fake_id}/approve",
            json={"approved_by": "ciso"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/transfer-controls/scc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_scc_returns_201() -> None:
    """POST /scc records an SCC and returns 201."""
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/transfer-controls/scc",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "connector_id": "anthropic",
                "scc_version": "EU-2021",
                "reference_id": "SCC-2024-001",
                "executed_at": datetime.now(UTC).isoformat(),
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["reference_id"] == "SCC-2024-001"


# ---------------------------------------------------------------------------
# GET /api/v1/transfer-controls/log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_transfer_logs() -> None:
    """GET /log returns transfer log entries."""
    session = _mock_session()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/transfer-controls/log",
            params={"engagement_id": ENGAGEMENT_ID},
        )

    assert resp.status_code == 200
    assert resp.json() == []
