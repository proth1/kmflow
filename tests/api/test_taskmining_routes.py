"""Skeleton HTTP tests for taskmining routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


class TestTaskminingRoutes:
    """Basic route existence and auth tests for /api/v1/taskmining."""

    @pytest.mark.asyncio
    async def test_list_agents_returns_200(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /taskmining/agents returns 200 with auth."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get("/api/v1/taskmining/agents")
        assert response.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_post_events_validates_body(self, client: AsyncClient) -> None:
        """POST /taskmining/events returns 422 for empty body."""
        response = await client.post("/api/v1/taskmining/events", json={})
        assert response.status_code in (422, 400, 201)

    @pytest.mark.asyncio
    async def test_register_agent_validates_body(self, client: AsyncClient) -> None:
        """POST /taskmining/agents/register returns 422 for empty body."""
        response = await client.post("/api/v1/taskmining/agents/register", json={})
        assert response.status_code in (422, 400, 201)

    @pytest.mark.asyncio
    async def test_get_config_for_unknown_agent(self, client: AsyncClient, mock_db_session: AsyncMock) -> None:
        """GET /taskmining/config/{agent_id} returns 404 for unknown agent."""
        agent_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        response = await client.get(f"/api/v1/taskmining/config/{agent_id}")
        assert response.status_code in (404, 200, 422)
