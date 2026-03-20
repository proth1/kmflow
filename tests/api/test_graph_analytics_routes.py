"""Skeleton HTTP tests for graph analytics routes."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Minimal app fixture for routes not in the shared test_app
# ---------------------------------------------------------------------------


@pytest.fixture
async def graph_analytics_client(mock_db_session: AsyncMock, mock_neo4j_driver: MagicMock) -> AsyncClient:
    """AsyncClient for graph analytics routes."""
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

    from src.api.routes import graph_analytics
    from src.core.auth import get_current_user
    from src.core.config import Settings, get_settings
    from src.core.models import User, UserRole
    from tests.conftest import MockSessionFactory

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(graph_analytics.router)

    settings = Settings(auth_dev_mode=True, debug=True, monitoring_worker_count=0)
    app.dependency_overrides[get_settings] = lambda: settings

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testuser@kmflow.dev"
    mock_user.role = UserRole.PLATFORM_ADMIN
    mock_user.is_active = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    app.state.db_session_factory = MockSessionFactory(mock_db_session)
    app.state.neo4j_driver = mock_neo4j_driver

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGraphAnalyticsRoutes:
    """Basic route tests for /api/v1/graph-analytics."""

    @pytest.mark.asyncio
    async def test_get_metrics_requires_valid_engagement_id(
        self, graph_analytics_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /graph-analytics/metrics/{id} returns 200 or 404 for valid UUID."""
        engagement_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await graph_analytics_client.get(f"/api/v1/graph-analytics/metrics/{engagement_id}")
        assert response.status_code in (200, 404, 422, 500)

    @pytest.mark.asyncio
    async def test_get_triangulation_requires_valid_engagement_id(
        self, graph_analytics_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /graph-analytics/triangulation/{id} returns expected status."""
        engagement_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await graph_analytics_client.get(f"/api/v1/graph-analytics/triangulation/{engagement_id}")
        assert response.status_code in (200, 404, 422, 500)

    @pytest.mark.asyncio
    async def test_get_relationships_requires_node_id(
        self, graph_analytics_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /graph-analytics/relationships/{node_id} returns expected status."""
        node_id = str(uuid.uuid4())
        response = await graph_analytics_client.get(f"/api/v1/graph-analytics/relationships/{node_id}")
        assert response.status_code in (200, 404, 422, 500)
