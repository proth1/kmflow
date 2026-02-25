"""Batch uploader: gzip-compressed event batches with exponential backoff.

Reads pending events from the SQLite buffer, compresses with gzip,
uploads to POST /api/v1/taskmining/events, and marks them as uploaded.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import uuid
from typing import Any

import httpx

from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.config.manager import ConfigManager

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 2


class BatchUploader:
    """Uploads buffered events to the KMFlow backend."""

    def __init__(
        self,
        buffer: BufferManager,
        config: ConfigManager,
        batch_size: int = 100,
        interval_seconds: int = 30,
    ) -> None:
        self.buffer = buffer
        self.config = config
        self.batch_size = batch_size
        self.interval_seconds = interval_seconds
        self._upload_count = 0

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Periodically drain the buffer and upload batches."""
        logger.info("Batch uploader started (interval=%ds)", self.interval_seconds)
        while not shutdown_event.is_set():
            try:
                await self._upload_pending()
            except Exception:
                logger.exception("Upload cycle error")
            # Wait for interval or shutdown
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=self.interval_seconds
                )
                break  # shutdown requested
            except asyncio.TimeoutError:
                pass  # normal interval elapsed
        logger.info("Batch uploader stopped (%d batches uploaded)", self._upload_count)

    async def _upload_pending(self) -> None:
        """Upload all pending events from the buffer."""
        while True:
            events = await self.buffer.read_pending(limit=self.batch_size)
            if not events:
                break

            batch_id = str(uuid.uuid4())
            event_ids = [e.pop("_buffer_id") for e in events]

            success = await self._upload_batch(batch_id, events)
            if success:
                await self.buffer.mark_uploaded(event_ids)
                self._upload_count += 1
            else:
                break  # stop trying, will retry next cycle

        # Prune uploaded events
        await self.buffer.prune_uploaded()

    async def _upload_batch(
        self, batch_id: str, events: list[dict[str, Any]]
    ) -> bool:
        """Upload a single batch with gzip compression and retry logic."""
        payload = json.dumps({
            "agent_id": self.config.agent_id,
            "session_id": str(uuid.uuid4()),
            "events": events,
        }).encode("utf-8")

        compressed = gzip.compress(payload)
        checksum = hashlib.sha256(payload).hexdigest()

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.config.backend_url}/api/v1/taskmining/events",
                        content=compressed,
                        headers={
                            "Content-Type": "application/json",
                            "Content-Encoding": "gzip",
                            "X-Batch-Id": batch_id,
                            "X-Checksum": checksum,
                        },
                        timeout=30.0,
                    )
                if response.status_code in (200, 201, 202):
                    logger.info(
                        "Batch %s uploaded (%d events)", batch_id[:8], len(events)
                    )
                    return True
                elif response.status_code >= 500:
                    logger.warning(
                        "Server error %d for batch %s (attempt %d/%d)",
                        response.status_code,
                        batch_id[:8],
                        attempt + 1,
                        MAX_RETRIES,
                    )
                else:
                    logger.error(
                        "Upload rejected: %d %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return False
            except httpx.HTTPError as e:
                logger.warning(
                    "Network error for batch %s (attempt %d/%d): %s",
                    batch_id[:8],
                    attempt + 1,
                    MAX_RETRIES,
                    str(e),
                )

            # Exponential backoff: 2, 4, 8, 16, 32 seconds
            backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
            await asyncio.sleep(backoff)

        logger.error(
            "Batch %s failed after %d retries, will retry next cycle",
            batch_id[:8],
            MAX_RETRIES,
        )
        return False
