"""Tests for the health check endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Minimal health endpoint (unauthenticated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_minimal_returns_ok(client: AsyncClient) -> None:
    """Minimal health endpoint should return 'ok' status."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    # Minimal endpoint should NOT expose service details
    assert "services" not in data
    assert "version" not in data


# ---------------------------------------------------------------------------
# Detailed health endpoint (authenticated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_detail_all_services_up(client: AsyncClient, mock_db_session: AsyncMock) -> None:
    """Detailed health endpoint should return 'healthy' when all services are up."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    response = await client.get("/api/v1/health/detail")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["services"]["postgres"] == "up"
    assert data["services"]["neo4j"] == "up"
    assert data["services"]["redis"] == "up"
    from src.api.version import API_VERSION

    assert data["version"] == API_VERSION
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_detail_degraded_when_redis_down(
    client: AsyncClient,
    mock_db_session: AsyncMock,
    mock_redis_client: AsyncMock,
) -> None:
    """Detailed health endpoint should return 'degraded' when one service is down."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    mock_redis_client.ping.side_effect = ConnectionError("Redis down")

    response = await client.get("/api/v1/health/detail")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["redis"] == "down"


@pytest.mark.asyncio
async def test_health_detail_unhealthy_when_all_down(
    client: AsyncClient,
    mock_db_session: AsyncMock,
    mock_neo4j_driver: MagicMock,
    mock_redis_client: AsyncMock,
) -> None:
    """Detailed health endpoint should return 'unhealthy' when all services are down."""
    mock_db_session.execute.side_effect = ConnectionError("DB down")
    mock_neo4j_driver.verify_connectivity.side_effect = ConnectionError("Neo4j down")
    mock_redis_client.ping.side_effect = ConnectionError("Redis down")

    response = await client.get("/api/v1/health/detail")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "unhealthy"
    assert all(s == "down" for s in data["services"].values())


@pytest.mark.asyncio
async def test_health_detail_response_structure(client: AsyncClient, mock_db_session: AsyncMock) -> None:
    """Detailed health response should have the expected structure."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db_session.execute.return_value = mock_result

    response = await client.get("/api/v1/health/detail")
    data = response.json()

    assert "status" in data
    assert "services" in data
    assert "version" in data
    assert "timestamp" in data
    assert isinstance(data["services"], dict)
    assert {"postgres", "neo4j", "redis"} <= set(data["services"].keys())
