"""Base monitoring agent with lifecycle management (Story #346).

Defines the abstract base class for all monitoring agents with:
- Lifecycle: start → connect → poll loop → stop
- Health state machine: STARTING → CONNECTED → POLLING → DEGRADED → UNHEALTHY
- Exponential backoff retry on connection/poll failures
- Watermark tracking for incremental data extraction
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from src.monitoring.agents.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentHealth(enum.StrEnum):
    """Health state machine for monitoring agents."""

    STARTING = "starting"
    CONNECTED = "connected"
    POLLING = "polling"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class HealthEvent:
    """Health status change event emitted by agents."""

    def __init__(self, agent_id: str, status: AgentHealth, detail: str = "") -> None:
        self.agent_id = agent_id
        self.status = status
        self.detail = detail
        self.timestamp = datetime.now(UTC)


class ExtractionEvent:
    """Event emitted when data is extracted during a poll cycle."""

    def __init__(
        self,
        agent_id: str,
        item_count: int,
        source_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.item_count = item_count
        self.source_metadata = source_metadata or {}
        self.timestamp = datetime.now(UTC)


class BaseMonitoringAgent(ABC):
    """Abstract base class for monitoring agents.

    Subclasses must implement:
    - connect() — establish connection to data source
    - poll() — check for new data since watermark
    - extract(raw_data) — transform and forward to pipeline
    - alert(message, severity) — raise alert to alerting system
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.agent_id = config.agent_id
        self.health = AgentHealth.STOPPED
        self.watermark: datetime | None = None
        self.items_processed_total: int = 0
        self.last_poll_time: datetime | None = None
        self.consecutive_failures: int = 0
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._health_events: list[HealthEvent] = []
        self._extraction_events: list[ExtractionEvent] = []

    def _emit_health(self, status: AgentHealth, detail: str = "") -> None:
        """Record a health status change."""
        self.health = status
        event = HealthEvent(self.agent_id, status, detail)
        self._health_events.append(event)
        logger.info("Agent %s health: %s %s", self.agent_id, status.value, detail)

    def _emit_extraction(self, item_count: int, metadata: dict[str, Any] | None = None) -> None:
        """Record an extraction event."""
        event = ExtractionEvent(self.agent_id, item_count, metadata)
        self._extraction_events.append(event)

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source.

        Raises:
            ConnectionError: If connection cannot be established.
        """

    @abstractmethod
    async def poll(self) -> Any:
        """Poll the data source for new data since the watermark.

        Returns:
            Raw data from the source, or None if no new data.
        """

    @abstractmethod
    async def extract(self, raw_data: Any) -> int:
        """Extract and forward data to the processing pipeline.

        Args:
            raw_data: Raw data returned by poll().

        Returns:
            Number of items extracted.
        """

    @abstractmethod
    async def alert(self, message: str, severity: str = "warning") -> None:
        """Raise an alert to the alerting system.

        Args:
            message: Alert description.
            severity: Alert severity level.
        """

    async def start(self) -> None:
        """Start the agent's polling loop."""
        if self._running:
            return
        self._running = True
        self._emit_health(AgentHealth.STARTING)
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._emit_health(AgentHealth.STOPPED)

    def _compute_backoff(self) -> float:
        """Compute exponential backoff delay based on consecutive failures."""
        retry = self.config.retry
        delay = retry.initial_delay_seconds * (retry.backoff_multiplier ** (self.consecutive_failures - 1))
        return min(delay, retry.max_delay_seconds)

    async def _run_loop(self) -> None:
        """Main polling loop with connection and retry logic."""
        # Attempt initial connection
        try:
            await self.connect()
            self.consecutive_failures = 0
            self._emit_health(AgentHealth.CONNECTED)
        except Exception as exc:
            logger.warning("Agent %s connection failed: %s", self.agent_id, exc)
            self.consecutive_failures += 1
            self._emit_health(AgentHealth.UNHEALTHY, str(exc))
            await self.alert(f"Connection failed: {exc}", severity="critical")
            return

        # Poll loop
        while self._running:
            try:
                self._emit_health(AgentHealth.POLLING)
                raw_data = await self.poll()

                if raw_data is not None:
                    item_count = await self.extract(raw_data)
                    self.items_processed_total += item_count
                    self.watermark = datetime.now(UTC)
                    self._emit_extraction(item_count, {"source_type": self.config.source_type})

                self.last_poll_time = datetime.now(UTC)
                self.consecutive_failures = 0

                # Wait for next poll interval
                await asyncio.sleep(self.config.polling_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.consecutive_failures += 1
                logger.warning(
                    "Agent %s poll failure #%d: %s",
                    self.agent_id,
                    self.consecutive_failures,
                    exc,
                )

                max_failures = self.config.retry.max_consecutive_failures
                if self.consecutive_failures >= max_failures:
                    self._emit_health(AgentHealth.UNHEALTHY, str(exc))
                    await self.alert(
                        f"Agent unhealthy after {self.consecutive_failures} failures: {exc}",
                        severity="critical",
                    )
                else:
                    self._emit_health(AgentHealth.DEGRADED, str(exc))

                backoff = self._compute_backoff()
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    break

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status for the health endpoint."""
        return {
            "agent_id": self.agent_id,
            "status": self.health.value,
            "last_poll_time": self.last_poll_time.isoformat() if self.last_poll_time else None,
            "items_processed_total": self.items_processed_total,
            "consecutive_failures": self.consecutive_failures,
            "watermark": self.watermark.isoformat() if self.watermark else None,
        }
