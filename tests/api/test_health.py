"""Tests for the health check endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_all_services_up(client: AsyncClient, mock_db_session: AsyncMock) -> None:
    """Health endpoint should return 'healthy' when all services are up."""
    # Mock PostgreSQL query
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["services"]["postgres"] == "up"
    assert data["services"]["neo4j"] == "up"
    assert data["services"]["redis"] == "up"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_degraded_when_redis_down(
    client: AsyncClient,
    mock_db_session: AsyncMock,
    mock_redis_client: AsyncMock,
) -> None:
    """Health endpoint should return 'degraded' when one service is down."""
    # Mock PostgreSQL query
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    # Redis fails
    mock_redis_client.ping.side_effect = ConnectionError("Redis down")

    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["redis"] == "down"


@pytest.mark.asyncio
async def test_health_unhealthy_when_all_down(
    client: AsyncClient,
    mock_db_session: AsyncMock,
    mock_neo4j_driver: MagicMock,
    mock_redis_client: AsyncMock,
) -> None:
    """Health endpoint should return 'unhealthy' when all services are down."""
    # All services fail
    mock_db_session.execute.side_effect = ConnectionError("DB down")
    mock_neo4j_driver.verify_connectivity.side_effect = ConnectionError("Neo4j down")
    mock_redis_client.ping.side_effect = ConnectionError("Redis down")

    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "unhealthy"
    assert all(s == "down" for s in data["services"].values())


@pytest.mark.asyncio
async def test_health_response_structure(client: AsyncClient, mock_db_session: AsyncMock) -> None:
    """Health response should have the expected structure."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    response = await client.get("/health")
    data = response.json()

    assert "status" in data
    assert "services" in data
    assert "version" in data
    assert isinstance(data["services"], dict)
    assert set(data["services"].keys()) == {"postgres", "neo4j", "redis"}
