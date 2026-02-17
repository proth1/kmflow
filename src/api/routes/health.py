"""Health check endpoint.

Returns overall system health and individual service statuses
for PostgreSQL, Neo4j, and Redis.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
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
    except Exception:
        logger.warning("PostgreSQL health check failed")
        services["postgres"] = "down"

    # Check Neo4j
    try:
        neo4j_driver = request.app.state.neo4j_driver
        await neo4j_driver.verify_connectivity()
        services["neo4j"] = "up"
    except Exception:
        logger.warning("Neo4j health check failed")
        services["neo4j"] = "down"

    # Check Redis
    try:
        redis_client = request.app.state.redis_client
        await redis_client.ping()
        services["redis"] = "up"
    except Exception:
        logger.warning("Redis health check failed")
        services["redis"] = "down"

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
        "version": "0.1.0",
    }
