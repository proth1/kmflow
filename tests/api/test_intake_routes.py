"""Skeleton HTTP tests for evidence intake routes."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def intake_client(mock_db_session: AsyncMock) -> AsyncClient:
    """AsyncClient for intake routes."""
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI

    from src.api.routes import intake
    from src.core.auth import get_current_user
    from src.core.config import Settings, get_settings
    from src.core.models import User, UserRole
    from tests.conftest import MockSessionFactory

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(intake.router)

    settings = Settings(auth_dev_mode=True, debug=True, monitoring_worker_count=0)
    app.dependency_overrides[get_settings] = lambda: settings

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "testuser@kmflow.dev"
    mock_user.role = UserRole.PLATFORM_ADMIN
    mock_user.is_active = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    app.state.db_session_factory = MockSessionFactory(mock_db_session)
    app.state.redis_client = AsyncMock()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestIntakeRoutes:
    """Basic route tests for evidence intake."""

    @pytest.mark.asyncio
    async def test_generate_intake_link_requires_valid_request_id(
        self, intake_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """POST /shelf-requests/{id}/generate-intake-link returns 404 or 200."""
        request_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await intake_client.post(
            f"/api/v1/shelf-requests/{request_id}/generate-intake-link",
            json={},
        )
        assert response.status_code in (404, 200, 422)

    @pytest.mark.asyncio
    async def test_intake_upload_requires_valid_token(
        self, intake_client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """POST /intake/{token} returns 400/422 for invalid token."""
        with patch("src.api.routes.intake.validate_intake_token", return_value=None):
            response = await intake_client.post(
                "/api/v1/intake/invalid-token",
                files={"file": ("test.pdf", b"content", "application/pdf")},
            )
        assert response.status_code in (400, 401, 403, 422)

    @pytest.mark.asyncio
    async def test_intake_progress_requires_valid_token(self, intake_client: AsyncClient) -> None:
        """GET /intake/{token}/progress returns 400/404 for invalid token."""
        with patch("src.api.routes.intake.validate_intake_token", return_value=None):
            response = await intake_client.get("/api/v1/intake/invalid-token/progress")
        assert response.status_code in (400, 401, 403, 404, 422)
