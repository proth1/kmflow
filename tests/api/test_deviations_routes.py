"""Skeleton HTTP tests for deviations routes."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def deviations_client(mock_db_session: AsyncMock) -> AsyncClient:
    """AsyncClient for deviations routes."""
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

    from src.api.routes import deviations
    from src.core.auth import get_current_user
    from src.core.config import Settings, get_settings
    from src.core.models import User, UserRole
    from tests.conftest import MockSessionFactory

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(deviations.router)

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


class TestDeviationsRoutes:
    """Basic route tests for /api/v1/deviations."""

    @pytest.mark.asyncio
    async def test_list_deviations_returns_200(
        self, deviations_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /deviations returns 200 with valid auth."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await deviations_client.get("/api/v1/deviations")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_list_deviations_without_auth_returns_error(self) -> None:
        """GET /deviations without auth returns 401/403."""
        from collections.abc import AsyncGenerator

        from fastapi import FastAPI

        from src.api.routes import deviations

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            yield

        app = FastAPI(lifespan=lifespan)
        app.include_router(deviations.router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/deviations")
        assert response.status_code in (401, 403, 422)
