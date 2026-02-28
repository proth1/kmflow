"""Route-level tests for PDP API endpoints (Story #377)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_session
from src.api.main import create_app
from src.api.services.pdp import _recent_latencies
from src.core.models import PDPDecisionType, User, UserRole
from src.core.models.pdp import DEFAULT_POLICIES, PDPPolicy

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


def _invalidate_cache() -> None:
    """Force cache refresh for test isolation."""
    import src.api.services.pdp as pdp_mod

    pdp_mod._cache_loaded_at = 0.0
    pdp_mod._policy_cache.clear()


def _setup_policies(session: AsyncMock, policies: list[dict]) -> None:
    """Set up mock session to return given policies from execute()."""
    mock_policies = []
    for p in policies:
        policy = MagicMock(spec=PDPPolicy)
        policy.id = p.get("id", uuid.uuid4())
        policy.name = p["name"]
        policy.conditions_json = p["conditions_json"]
        policy.decision = PDPDecisionType(p["decision"]) if isinstance(p["decision"], str) else p["decision"]
        policy.obligations_json = p.get("obligations_json")
        policy.reason = p.get("reason")
        policy.priority = p.get("priority", 100)
        policy.is_active = True
        mock_policies.append(policy)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = mock_policies
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)


# ---------------------------------------------------------------------------
# POST /api/v1/pdp/evaluate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_public_returns_permit() -> None:
    """POST /evaluate for public data returns PERMIT."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pdp/evaluate",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "resource_id": "evidence-001",
                "classification": "public",
                "operation": "read",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == PDPDecisionType.PERMIT
    assert "audit_id" in data


@pytest.mark.asyncio
async def test_evaluate_restricted_denied_for_analyst() -> None:
    """POST /evaluate for restricted data as process_analyst returns DENY."""
    _invalidate_cache()
    session = _mock_session()
    _setup_policies(session, DEFAULT_POLICIES)

    app = _make_app(session, user_role=UserRole.PROCESS_ANALYST)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pdp/evaluate",
            json={
                "engagement_id": ENGAGEMENT_ID,
                "resource_id": "evidence-002",
                "classification": "restricted",
                "operation": "read",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == PDPDecisionType.DENY
    assert data["reason"] == "insufficient_clearance"


# ---------------------------------------------------------------------------
# POST /api/v1/pdp/rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_returns_201() -> None:
    """POST /rules creates a policy rule and returns 201."""
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pdp/rules",
            json={
                "name": "block_delete_public",
                "conditions_json": {"classification": "public", "operation": "delete"},
                "decision": "deny",
                "reason": "delete_not_allowed",
                "priority": 5,
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "block_delete_public"
    assert data["decision"] == "deny"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_rule_forbidden_for_analyst() -> None:
    """POST /rules as process_analyst returns 403 (pdp:admin required)."""
    session = _mock_session()
    app = _make_app(session, user_role=UserRole.PROCESS_ANALYST)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pdp/rules",
            json={
                "name": "test_rule",
                "conditions_json": {"classification": "public"},
                "decision": "deny",
            },
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/pdp/rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules_returns_policies() -> None:
    """GET /rules returns list of active policies."""
    session = _mock_session()

    mock_policy = MagicMock(spec=PDPPolicy)
    mock_policy.id = uuid.uuid4()
    mock_policy.name = "test_policy"
    mock_policy.description = None
    mock_policy.conditions_json = {"classification": "restricted"}
    mock_policy.decision = "deny"
    mock_policy.obligations_json = None
    mock_policy.reason = "test"
    mock_policy.priority = 10
    mock_policy.is_active = True

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_policy]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)

    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/pdp/rules")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "test_policy"


# ---------------------------------------------------------------------------
# GET /api/v1/pdp/health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_metrics() -> None:
    """GET /health returns health metrics."""
    _recent_latencies.clear()
    session = _mock_session()
    app = _make_app(session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/pdp/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["decisions_tracked"] == 0
    assert data["p99_latency_ms"] == 0.0
