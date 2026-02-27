"""Route-level tests for LLM Audit Trail endpoints (Story #386)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.core.models import User, UserRole


def _mock_user(role: UserRole = UserRole.ENGAGEMENT_LEAD) -> User:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = role
    user.is_active = True
    return user


def _make_app(mock_session: AsyncMock, user_role: UserRole = UserRole.ENGAGEMENT_LEAD) -> Any:
    from src.api.routes.auth import get_current_user

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user(user_role)
    app.state.neo4j_driver = MagicMock()
    return app


@pytest.fixture()
def mock_session() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{id}/llm-audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_llm_audit_returns_paginated(mock_session: AsyncMock) -> None:
    app = _make_app(mock_session)
    engagement_id = uuid.uuid4()

    count_result = MagicMock()
    count_result.scalar.return_value = 0

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/engagements/{engagement_id}/llm-audit")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["limit"] == 20
    assert data["offset"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/suggestions/{id}/flag-hallucination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_hallucination_returns_updated_entry(mock_session: AsyncMock) -> None:
    app = _make_app(mock_session)
    audit_log_id = uuid.uuid4()

    log_mock = MagicMock()
    log_mock.id = audit_log_id
    log_mock.scenario_id = uuid.uuid4()
    log_mock.user_id = None
    log_mock.prompt_tokens = 100
    log_mock.completion_tokens = 200
    log_mock.model_name = "gpt-4"
    log_mock.evidence_ids = None
    log_mock.error_message = None
    log_mock.hallucination_flagged = False
    log_mock.hallucination_reason = None
    log_mock.flagged_at = None
    log_mock.flagged_by_user_id = None
    log_mock.created_at = datetime.now(UTC)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = log_mock
    mock_session.execute = AsyncMock(return_value=result_mock)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/suggestions/{audit_log_id}/flag-hallucination",
            json={"reason": "Invented citation"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["hallucination_flagged"] is True
    assert data["hallucination_reason"] == "Invented citation"


@pytest.mark.asyncio
async def test_flag_hallucination_not_found_returns_404(mock_session: AsyncMock) -> None:
    app = _make_app(mock_session)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/suggestions/{uuid.uuid4()}/flag-hallucination",
            json={"reason": "Bad data"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/engagements/{id}/llm-audit/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats_returns_rates(mock_session: AsyncMock) -> None:
    app = _make_app(mock_session)
    engagement_id = uuid.uuid4()

    count_result = MagicMock()
    count_result.scalar.return_value = 5

    from src.core.models.simulation import SuggestionDisposition

    sugg_result = MagicMock()
    sugg_result.__iter__ = MagicMock(
        return_value=iter([
            (SuggestionDisposition.ACCEPTED, 3),
            (SuggestionDisposition.REJECTED, 2),
        ])
    )

    halluc_result = MagicMock()
    halluc_result.scalar.return_value = 1

    mock_session.execute = AsyncMock(
        side_effect=[count_result, sugg_result, halluc_result]
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/engagements/{engagement_id}/llm-audit/stats")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 5
    assert data["accepted_count"] == 3
    assert data["rejected_count"] == 2
    assert data["hallucination_flagged_count"] == 1
    assert data["acceptance_rate"] == 60.0


@pytest.mark.asyncio
async def test_flag_hallucination_empty_reason_rejected(mock_session: AsyncMock) -> None:
    """FlagHallucinationRequest requires non-empty reason (min_length=1)."""
    app = _make_app(mock_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/suggestions/{uuid.uuid4()}/flag-hallucination",
            json={"reason": ""},
        )

    assert resp.status_code == 422
