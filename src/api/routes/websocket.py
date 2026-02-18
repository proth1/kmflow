"""WebSocket handlers for real-time monitoring dashboard.

Provides WebSocket endpoints that subscribe to Redis Pub/Sub channels
and push events to connected clients. Includes heartbeat and
connection management.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from src.core.auth import decode_token
from src.core.config import get_settings
from src.core.redis import CHANNEL_ALERTS, CHANNEL_DEVIATIONS, CHANNEL_MONITORING

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections per engagement."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, engagement_id: str) -> None:
        await websocket.accept()
        if engagement_id not in self._connections:
            self._connections[engagement_id] = []
        self._connections[engagement_id].append(websocket)
        logger.info("WebSocket connected for engagement %s", engagement_id)

    def disconnect(self, websocket: WebSocket, engagement_id: str) -> None:
        if engagement_id in self._connections:
            self._connections[engagement_id] = [ws for ws in self._connections[engagement_id] if ws != websocket]
            if not self._connections[engagement_id]:
                del self._connections[engagement_id]
        logger.info("WebSocket disconnected for engagement %s", engagement_id)

    async def broadcast(self, engagement_id: str, message: dict[str, Any]) -> None:
        """Send a message to all connections for an engagement."""
        if engagement_id not in self._connections:
            return
        dead: list[WebSocket] = []
        for ws in self._connections[engagement_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[engagement_id].remove(ws)

    @property
    def active_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())

    def get_engagement_ids(self) -> list[str]:
        return list(self._connections.keys())

    def get_connection_count(self, engagement_id: str) -> int:
        """Get the number of active connections for an engagement."""
        if engagement_id not in self._connections:
            return 0
        return len(self._connections[engagement_id])


manager = ConnectionManager()


async def _redis_subscriber(
    request: Request,
    engagement_id: str,
    shutdown: asyncio.Event,
) -> None:
    """Subscribe to Redis Pub/Sub and forward events to WebSocket clients."""
    redis_client = request.app.state.redis_client
    pubsub = redis_client.pubsub()

    channels = [CHANNEL_DEVIATIONS, CHANNEL_ALERTS, CHANNEL_MONITORING]
    await pubsub.subscribe(*channels)

    try:
        while not shutdown.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    # Only forward events for this engagement
                    if data.get("engagement_id") == engagement_id:
                        await manager.broadcast(engagement_id, data)
                except (json.JSONDecodeError, TypeError):
                    pass
            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()


@router.websocket("/ws/monitoring/{engagement_id}")
async def monitoring_websocket(
    websocket: WebSocket,
    engagement_id: str,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for real-time monitoring events.

    Subscribes to Redis Pub/Sub and forwards matching events.
    Sends heartbeats every 30 seconds.

    Authentication:
        Requires JWT token as query parameter: ?token=<jwt>

    Connection Limits:
        Max connections per engagement is configurable (default: 10).
        Exceeding the limit results in close code 1008 (Policy Violation).
    """
    # Authenticate the connection
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        settings = get_settings()
        decode_token(token, settings)
    except Exception as e:
        logger.warning("WebSocket authentication failed: %s", e)
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    # Check connection limit
    settings = get_settings()
    current_count = manager.get_connection_count(engagement_id)
    if current_count >= settings.ws_max_connections_per_engagement:
        logger.warning(
            "Connection limit reached for engagement %s (%d/%d)",
            engagement_id,
            current_count,
            settings.ws_max_connections_per_engagement,
        )
        await websocket.close(
            code=1008,
            reason=f"Connection limit reached ({settings.ws_max_connections_per_engagement} max)",
        )
        return

    await manager.connect(websocket, engagement_id)
    shutdown = asyncio.Event()

    # Start Redis subscriber in background
    subscriber_task = asyncio.create_task(
        _redis_subscriber(websocket, engagement_id, shutdown)  # type: ignore[arg-type]
    )

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client messages (ping/pong)
                if data == "ping":
                    await websocket.send_text("pong")
            except TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for engagement %s", engagement_id)
    finally:
        shutdown.set()
        subscriber_task.cancel()
        manager.disconnect(websocket, engagement_id)


@router.websocket("/ws/alerts/{engagement_id}")
async def alerts_websocket(
    websocket: WebSocket,
    engagement_id: str,
    token: str | None = Query(default=None),
) -> None:
    """WebSocket endpoint for real-time alert notifications only.

    Authentication:
        Requires JWT token as query parameter: ?token=<jwt>

    Connection Limits:
        Max connections per engagement is configurable (default: 10).
        Exceeding the limit results in close code 1008 (Policy Violation).
    """
    # Authenticate the connection
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        settings = get_settings()
        decode_token(token, settings)
    except Exception as e:
        logger.warning("WebSocket authentication failed: %s", e)
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    # Check connection limit
    settings = get_settings()
    current_count = manager.get_connection_count(engagement_id)
    if current_count >= settings.ws_max_connections_per_engagement:
        logger.warning(
            "Connection limit reached for engagement %s (%d/%d)",
            engagement_id,
            current_count,
            settings.ws_max_connections_per_engagement,
        )
        await websocket.close(
            code=1008,
            reason=f"Connection limit reached ({settings.ws_max_connections_per_engagement} max)",
        )
        return

    await manager.connect(websocket, engagement_id)
    shutdown = asyncio.Event()

    redis_client = websocket.app.state.redis_client
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL_ALERTS)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    if data.get("engagement_id") == engagement_id:
                        await websocket.send_json(data)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Check for client disconnect
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                if data == "ping":
                    await websocket.send_text("pong")
            except TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Alert WebSocket error")
    finally:
        shutdown.set()
        await pubsub.unsubscribe(CHANNEL_ALERTS)
        await pubsub.close()
        manager.disconnect(websocket, engagement_id)


@router.get("/api/v1/ws/status")
async def websocket_status() -> dict[str, Any]:
    """Get WebSocket connection status."""
    return {
        "active_connections": manager.active_connections,
        "engagement_ids": manager.get_engagement_ids(),
    }
