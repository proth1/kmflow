"""Health check endpoint.

Returns overall system health and individual service statuses
for PostgreSQL, Neo4j, and Redis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from neo4j.exceptions import Neo4jError
from sqlalchemy.exc import SQLAlchemyError

from src.api.version import API_VERSION

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/api/v1/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Check the health of all platform services.

    Returns:
        JSON object with overall status and per-service health:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "services": {
                "postgres": "up" | "down",
                "neo4j": "up" | "down",
                "redis": "up" | "down"
            },
            "version": "0.1.0"
        }
    """
    services: dict[str, str] = {}

    # Check PostgreSQL
    try:
        db_session_factory = request.app.state.db_session_factory
        async with db_session_factory() as session:
            result = await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            result.scalar()
            services["postgres"] = "up"
    except (SQLAlchemyError, ConnectionError, OSError):
        logger.warning("PostgreSQL health check failed")
        services["postgres"] = "down"

    # Check Neo4j
    try:
        neo4j_driver = request.app.state.neo4j_driver
        await neo4j_driver.verify_connectivity()
        services["neo4j"] = "up"
    except (Neo4jError, OSError, AttributeError):
        logger.warning("Neo4j health check failed")
        services["neo4j"] = "down"

    # Check Redis
    try:
        redis_client = request.app.state.redis_client
        await redis_client.ping()
        services["redis"] = "up"
    except (aioredis.RedisError, ConnectionError, OSError):
        logger.warning("Redis health check failed")
        services["redis"] = "down"

    # Check Camunda (CIB7)
    try:
        camunda_client = getattr(request.app.state, "camunda_client", None)
        if camunda_client and await camunda_client.verify_connectivity():
            services["camunda"] = "up"
        else:
            services["camunda"] = "down"
    except (ConnectionError, OSError):
        logger.warning("Camunda health check failed")
        services["camunda"] = "down"

    # Determine overall status
    down_count = sum(1 for s in services.values() if s == "down")
    if down_count == 0:
        status = "healthy"
    elif down_count < len(services):
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "status": status,
        "services": services,
        "version": API_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
    }
