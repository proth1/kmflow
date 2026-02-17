"""Notification dispatch for monitoring alerts.

Extensible notification system that currently supports WebSocket
push via Redis Pub/Sub. Can be extended with email, Slack, etc.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from src.core.redis import CHANNEL_ALERTS, CHANNEL_DEVIATIONS, publish_event
from src.monitoring.events import alert_event, deviation_event

logger = logging.getLogger(__name__)


async def notify_deviation(
    redis_client: aioredis.Redis,
    engagement_id: str,
    deviation_id: str,
    category: str,
    magnitude: float,
    affected_element: str | None = None,
    description: str = "",
) -> None:
    """Publish a deviation detection notification."""
    event = deviation_event(
        engagement_id=engagement_id,
        deviation_id=deviation_id,
        category=category,
        magnitude=magnitude,
        affected_element=affected_element,
        description=description,
    )
    await publish_event(redis_client, CHANNEL_DEVIATIONS, event)
    logger.debug("Deviation notification published: %s", deviation_id)


async def notify_alert(
    redis_client: aioredis.Redis,
    engagement_id: str,
    alert_id: str,
    severity: str,
    title: str,
    description: str = "",
) -> None:
    """Publish an alert generation notification."""
    event = alert_event(
        engagement_id=engagement_id,
        alert_id=alert_id,
        severity=severity,
        title=title,
        description=description,
    )
    await publish_event(redis_client, CHANNEL_ALERTS, event)
    logger.debug("Alert notification published: %s", alert_id)
