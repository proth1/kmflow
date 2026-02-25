"""Unix domain socket server for receiving events from the Swift capture layer.

Listens on /tmp/kmflow-agent.sock and reads newline-delimited JSON events.
Each event is L2-filtered and written to the local SQLite buffer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.pii.l2_filter import L2Filter

logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/kmflow-agent.sock"


class SocketServer:
    """Async Unix domain socket server for Swift → Python IPC."""

    def __init__(
        self,
        buffer: BufferManager,
        socket_path: str = SOCKET_PATH,
    ) -> None:
        self.buffer = buffer
        self.socket_path = socket_path
        self.l2_filter = L2Filter()
        self._event_count = 0

    async def serve(self, shutdown_event: asyncio.Event) -> None:
        """Start the socket server and accept connections until shutdown."""
        # Remove stale socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        server = await asyncio.start_unix_server(
            self._handle_client, path=self.socket_path
        )
        logger.info("Socket server listening on %s", self.socket_path)

        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            server.close()
            await server.wait_closed()
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            logger.info("Socket server stopped (processed %d events)", self._event_count)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single Swift client connection."""
        logger.info("Swift client connected")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    event_data = json.loads(line.decode("utf-8").strip())
                    await self._process_event(event_data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received: %s", line[:100])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Client handler error")
        finally:
            writer.close()
            logger.info("Swift client disconnected")

    async def _process_event(self, event_data: dict) -> None:
        """Apply L2 PII filter and buffer the event."""
        # L2 PII filtering
        filtered = self.l2_filter.filter_event(event_data)

        # Write to local buffer
        await self.buffer.write_event(filtered)
        self._event_count += 1

    @property
    def event_count(self) -> int:
        return self._event_count
