"""Parametrized test: all engagement_id routes enforce membership.

Verifies that non-member, non-admin users receive 403 when accessing
engagement-scoped endpoints (Audit Batch 2 CRITICAL IDOR fix).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.auth import get_current_user
from src.core.config import Settings, get_settings
from src.core.models import User, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_analyst() -> MagicMock:
    """Create a non-admin user (process_analyst) for IDOR testing."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "analyst@kmflow.dev"
    user.name = "Test Analyst"
    user.role = UserRole.PROCESS_ANALYST
    user.is_active = True
    return user


@pytest.fixture
async def idor_client() -> AsyncClient:
    """Test client with a non-admin user (no engagement membership).

    The mock DB session returns None for EngagementMember queries,
    so require_engagement_access will 403 for all requests.
    """
    from src.api.routes import (
        audit_logs,
        cohort,
        conformance,
        consistency,
        incidents,
        integrations,
        llm_audit,
        micro_surveys,
        shelf_requests,
        suggestion_feedback,
        taskmining,
        transfer_controls,
    )

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):  # noqa: ANN001
        yield

    app = FastAPI(lifespan=noop_lifespan)

    # Register all engagement-scoped routers
    for router_mod in [
        cohort,
        conformance,
        consistency,
        llm_audit,
        suggestion_feedback,
        audit_logs,
        incidents,
        integrations,
        micro_surveys,
        shelf_requests,
        taskmining,
        transfer_controls,
    ]:
        app.include_router(router_mod.router)

    # Override auth to return a non-admin user
    analyst = _make_analyst()
    app.dependency_overrides[get_current_user] = lambda: analyst

    # Override settings
    test_settings = Settings(
        jwt_secret_key="test-key",
        jwt_algorithm="HS256",
        auth_dev_mode=True,
        debug=True,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    # Mock DB session that returns None for membership lookups
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    class MockSessionFactory:
        def __call__(self) -> MockSessionFactory:
            return self

        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    app.state.db_session_factory = MockSessionFactory()
    app.state.db_engine = MagicMock()
    app.state.neo4j_driver = MagicMock()
    app.state.redis_client = AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# PATH parameter routes — should get 403
# ---------------------------------------------------------------------------

FAKE_ENG_ID = str(uuid.uuid4())

PATH_PARAM_ROUTES = [
    ("PATCH", f"/api/v1/cohort/engagements/{FAKE_ENG_ID}/settings"),
    ("GET", f"/api/v1/cohort/engagements/{FAKE_ENG_ID}/settings"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/reports/disagreement"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/consistency-metrics"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/consistency-metrics/trend"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/llm-audit"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/llm-audit/stats"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/rejection-feedback"),
    ("GET", f"/api/v1/engagements/{FAKE_ENG_ID}/rejection-feedback/exclusion-prompt"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PATH_PARAM_ROUTES)
async def test_path_param_route_returns_403_for_non_member(
    idor_client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Non-member should get 403 on engagement-scoped path param routes."""
    if method == "GET":
        response = await idor_client.get(path)
    elif method == "PATCH":
        response = await idor_client.patch(path, json={"min_cohort_size": 5})
    else:
        response = await idor_client.request(method, path)

    assert response.status_code == 403, f"{method} {path} returned {response.status_code}, expected 403"


# ---------------------------------------------------------------------------
# QUERY parameter routes — should get 403
# ---------------------------------------------------------------------------

QUERY_PARAM_ROUTES = [
    ("GET", "/api/v1/incidents", {"engagement_id": FAKE_ENG_ID}),
    ("GET", "/api/v1/micro-surveys", {"engagement_id": FAKE_ENG_ID}),
    ("GET", "/api/v1/transfer-controls/log", {"engagement_id": FAKE_ENG_ID}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,params", QUERY_PARAM_ROUTES)
async def test_query_param_route_returns_403_for_non_member(
    idor_client: AsyncClient,
    method: str,
    path: str,
    params: dict[str, str],
) -> None:
    """Non-member should get 403 on engagement-scoped query param routes."""
    response = await idor_client.get(path, params=params)
    assert response.status_code == 403, f"{method} {path} returned {response.status_code}, expected 403"
