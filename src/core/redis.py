"""Redis connection management.

Provides async Redis client creation and health checking.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from src.core.config import Settings

logger = logging.getLogger(__name__)


def create_redis_client(settings: Settings) -> aioredis.Redis:
    """Create an async Redis client.

    Args:
        settings: Application settings with Redis connection details.

    Returns:
        An async Redis client instance.
    """
    client: aioredis.Redis = aioredis.from_url(
        settings.redis_url or f"redis://{settings.redis_host}:{settings.redis_port}/0",
        decode_responses=True,
    )
    return client


async def verify_redis_connectivity(client: aioredis.Redis) -> bool:
    """Check if Redis is reachable.

    Returns:
        True if Redis responds to PING, False otherwise.
    """
    try:
        return bool(await client.ping())
    except Exception:
        logger.exception("Failed to connect to Redis")
        return False
