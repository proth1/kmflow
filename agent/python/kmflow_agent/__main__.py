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
import signal
import sys

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

    # Initialize services
    buffer = BufferManager()
    config = ConfigManager(
        backend_url="http://localhost:8000",
        agent_id="default",
    )
    uploader = BatchUploader(buffer=buffer, config=config)
    health = HealthReporter(
        backend_url="http://localhost:8000",
        agent_id="default",
    )
    server = SocketServer(buffer=buffer)

    logger.info("KMFlow Agent Python layer starting")

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
        await buffer.close()
        logger.info("KMFlow Agent Python layer stopped")


if __name__ == "__main__":
    asyncio.run(main())
