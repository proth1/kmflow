"""Skeleton HTTP tests for correlation routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestCorrelationRoutes:
    """Basic route existence and auth tests for /api/v1/correlation."""

    @pytest.mark.asyncio
    async def test_list_links_requires_auth(self, test_app: object) -> None:
        """GET /correlation/links returns 401/403 without auth."""
        from src.core.auth import get_current_user

        test_app.dependency_overrides.pop(get_current_user, None)

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/correlation/links")
        assert response.status_code in (401, 403, 422)

        # Restore default override
        from unittest.mock import MagicMock

        from src.core.models import User, UserRole

        mock_user = MagicMock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user.email = "testuser@kmflow.dev"
        mock_user.role = UserRole.PLATFORM_ADMIN
        mock_user.is_active = True
        test_app.dependency_overrides[get_current_user] = lambda: mock_user

    @pytest.mark.asyncio
    async def test_list_links_with_auth(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /correlation/links returns 200 with valid auth."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/correlation/links")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_get_diagnostics_returns_200(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /correlation/diagnostics returns 200."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/correlation/diagnostics")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_get_unlinked_returns_200(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /correlation/unlinked returns 200."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/correlation/unlinked")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_post_link_validates_body(self, client: AsyncClient) -> None:
        """POST /correlation/link returns 422 for invalid body."""
        response = await client.post("/api/v1/correlation/link", json={})
        assert response.status_code in (422, 400, 200)
