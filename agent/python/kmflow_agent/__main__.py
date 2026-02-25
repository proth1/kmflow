"""Entry point for the Python intelligence layer.

Starts all async services:
- Unix domain socket server (IPC from Swift)
- Batch uploader (periodic buffer drain)
- Config manager (periodic refresh)
- Health reporter (5-minute heartbeat)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from kmflow_agent.auth import create_http_client, get_auth_token
from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.config.manager import ConfigManager
from kmflow_agent.health.reporter import HealthReporter
from kmflow_agent.ipc.socket_server import SocketServer
from kmflow_agent.upload.batch_uploader import BatchUploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kmflow_agent")


async def main() -> None:
    """Start all agent services."""
    shutdown_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    # Configuration from environment
    backend_url = os.environ.get("KMFLOW_BACKEND_URL", "http://localhost:8000")
    agent_id = os.environ.get("KMFLOW_AGENT_ID", "default")

    if backend_url == "http://localhost:8000":
        logger.warning("Using default backend URL — set KMFLOW_BACKEND_URL for production")

    # Shared authenticated HTTP client
    token = get_auth_token()
    if not token:
        logger.warning("No agent token found — HTTP requests will be unauthenticated")
    http_client = create_http_client(token)

    # Initialize services
    buffer = BufferManager()
    config = ConfigManager(
        backend_url=backend_url,
        agent_id=agent_id,
        http_client=http_client,
    )
    uploader = BatchUploader(
        buffer=buffer,
        config=config,
        http_client=http_client,
    )
    health = HealthReporter(
        backend_url=backend_url,
        agent_id=agent_id,
        http_client=http_client,
    )
    server = SocketServer(buffer=buffer)

    logger.info("KMFlow Agent Python layer starting (backend=%s, agent=%s)", backend_url, agent_id)

    # Run all services concurrently
    try:
        await asyncio.gather(
            server.serve(shutdown_event),
            uploader.run(shutdown_event),
            config.run(shutdown_event),
            health.run(shutdown_event),
        )
    except Exception:
        logger.exception("Service error")
    finally:
        await http_client.aclose()
        await buffer.close()
        logger.info("KMFlow Agent Python layer stopped")


if __name__ == "__main__":
    asyncio.run(main())
