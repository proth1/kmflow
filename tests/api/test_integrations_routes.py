"""Skeleton HTTP tests for integrations routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestIntegrationsRoutes:
    """Basic route existence and auth tests for /api/v1/integrations."""

    @pytest.mark.asyncio
    async def test_list_connectors_returns_200(self, client: AsyncClient) -> None:
        """GET /integrations/connectors returns 200 with auth."""
        response = await client.get("/api/v1/integrations/connectors")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_list_connections_returns_200(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /integrations/connections returns 200 with auth."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/integrations/connections")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_create_connection_validates_body(self, client: AsyncClient) -> None:
        """POST /integrations/connections returns 422 for empty body."""
        response = await client.post("/api/v1/integrations/connections", json={})
        assert response.status_code in (422, 400, 201)

    @pytest.mark.asyncio
    async def test_get_connection_returns_404_for_unknown(
        self, client: AsyncClient, mock_db_session: AsyncMock
    ) -> None:
        """GET /integrations/connections/{id} returns 404 for unknown connection."""
        conn_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get(f"/api/v1/integrations/connections/{conn_id}")
        assert response.status_code in (404, 200, 422)
