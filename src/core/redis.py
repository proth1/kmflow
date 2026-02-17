"""Redis connection management with Streams and Pub/Sub support.

Provides async Redis client creation, health checking, Redis Streams
helpers for background workers, and Pub/Sub channel management for
real-time WebSocket fan-out.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from src.core.config import Settings

logger = logging.getLogger(__name__)

# -- Stream names --------------------------------------------------------------

MONITORING_STREAM = "kmflow:monitoring:tasks"
ALERT_STREAM = "kmflow:alerts:events"

# -- Pub/Sub channels ----------------------------------------------------------

CHANNEL_DEVIATIONS = "kmflow:realtime:deviations"
CHANNEL_ALERTS = "kmflow:realtime:alerts"
CHANNEL_MONITORING = "kmflow:realtime:monitoring"


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


# -- Redis Streams helpers -----------------------------------------------------


async def stream_add(
    client: aioredis.Redis,
    stream: str,
    data: dict[str, Any],
    max_len: int = 10000,
) -> str:
    """Add a message to a Redis Stream.

    Args:
        client: Redis client.
        stream: Stream name.
        data: Message data (will be JSON-encoded under 'payload' key).
        max_len: Maximum stream length (approximate trimming).

    Returns:
        The message ID assigned by Redis.
    """
    msg_id: str = await client.xadd(
        stream,
        {"payload": json.dumps(data)},
        maxlen=max_len,
        approximate=True,
    )
    return msg_id


async def stream_read(
    client: aioredis.Redis,
    stream: str,
    last_id: str = "0-0",
    count: int = 10,
    block_ms: int = 5000,
) -> list[tuple[str, dict[str, Any]]]:
    """Read messages from a Redis Stream.

    Args:
        client: Redis client.
        stream: Stream name.
        last_id: Read messages after this ID.
        count: Max messages to read.
        block_ms: Block timeout in milliseconds.

    Returns:
        List of (message_id, parsed_data) tuples.
    """
    result = await client.xread({stream: last_id}, count=count, block=block_ms)
    messages: list[tuple[str, dict[str, Any]]] = []
    if result:
        for _stream_name, entries in result:
            for msg_id, fields in entries:
                try:
                    data = json.loads(fields.get("payload", "{}"))
                except (json.JSONDecodeError, TypeError):
                    data = dict(fields)
                messages.append((msg_id, data))
    return messages


async def stream_ack(
    client: aioredis.Redis,
    stream: str,
    group: str,
    *msg_ids: str,
) -> int:
    """Acknowledge messages in a consumer group.

    Args:
        client: Redis client.
        stream: Stream name.
        group: Consumer group name.
        msg_ids: Message IDs to acknowledge.

    Returns:
        Number of messages acknowledged.
    """
    if not msg_ids:
        return 0
    count: int = await client.xack(stream, group, *msg_ids)
    return count


async def ensure_consumer_group(
    client: aioredis.Redis,
    stream: str,
    group: str,
) -> None:
    """Create a consumer group if it doesn't exist.

    Args:
        client: Redis client.
        stream: Stream name.
        group: Consumer group name.
    """
    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


# -- Pub/Sub helpers -----------------------------------------------------------


async def publish_event(
    client: aioredis.Redis,
    channel: str,
    data: dict[str, Any],
) -> int:
    """Publish an event to a Redis Pub/Sub channel.

    Args:
        client: Redis client.
        channel: Channel name.
        data: Event data (will be JSON-encoded).

    Returns:
        Number of subscribers that received the message.
    """
    count: int = await client.publish(channel, json.dumps(data))
    return count
