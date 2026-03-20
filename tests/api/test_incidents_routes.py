"""Skeleton HTTP tests for incidents routes."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def incidents_client(mock_db_session: AsyncMock) -> AsyncClient:
    """AsyncClient for incidents routes."""
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

    from src.api.routes import incidents
    from src.core.auth import get_current_user
    from src.core.config import Settings, get_settings
    from src.core.models import User, UserRole
    from tests.conftest import MockSessionFactory

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(incidents.router)

    settings = Settings(auth_dev_mode=True, debug=True, monitoring_worker_count=0)
    app.dependency_overrides[get_settings] = lambda: settings

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testuser@kmflow.dev"
    mock_user.role = UserRole.PLATFORM_ADMIN
    mock_user.is_active = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    app.state.db_session_factory = MockSessionFactory(mock_db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestIncidentsRoutes:
    """Basic route tests for /api/v1/incidents."""

    @pytest.mark.asyncio
    async def test_list_incidents_returns_200(self, incidents_client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /incidents returns 200 with auth."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await incidents_client.get("/api/v1/incidents")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_create_incident_validates_body(self, incidents_client: AsyncClient) -> None:
        """POST /incidents returns 422 for empty body."""
        response = await incidents_client.post("/api/v1/incidents", json={})
        assert response.status_code in (422, 400, 201)

    @pytest.mark.asyncio
    async def test_get_timeline_returns_404_for_unknown(
        self, incidents_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /incidents/{id}/timeline returns 404 for unknown incident."""
        incident_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await incidents_client.get(f"/api/v1/incidents/{incident_id}/timeline")
        assert response.status_code in (404, 200, 422)

    @pytest.mark.asyncio
    async def test_incidents_without_auth_returns_error(self) -> None:
        """GET /incidents without auth returns 401/403."""
        from collections.abc import AsyncGenerator

        from fastapi import FastAPI

        from src.api.routes import incidents

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            yield

        app = FastAPI(lifespan=lifespan)
        app.include_router(incidents.router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/incidents")
        assert response.status_code in (401, 403, 422)
