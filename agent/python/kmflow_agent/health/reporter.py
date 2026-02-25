"""Health reporter: periodic heartbeats and CPU/memory self-monitoring.

Sends POST /api/v1/taskmining/heartbeat every 5 minutes with system metrics.
If CPU exceeds 3% for >60s, enables adaptive throttling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
import psutil

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 300  # 5 minutes
CPU_THRESHOLD_PERCENT = 3.0
CPU_THRESHOLD_DURATION_SECONDS = 60


@dataclass
class HealthMetrics:
    """Current agent health metrics."""

    cpu_percent: float
    memory_mb: float
    event_queue_size: int
    uptime_seconds: float
    throttle_active: bool


class HealthReporter:
    """Reports agent health to the KMFlow backend."""

    def __init__(
        self,
        backend_url: str,
        agent_id: str,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self.backend_url = backend_url
        self.agent_id = agent_id
        self.heartbeat_interval = heartbeat_interval
        self._start_time = time.time()
        self._throttle_active = False
        self._cpu_exceeded_since: float | None = None
        self._process = psutil.Process()

    @property
    def throttle_active(self) -> bool:
        return self._throttle_active

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Send periodic heartbeats until shutdown."""
        logger.info("Health reporter started (interval=%ds)", self.heartbeat_interval)
        while not shutdown_event.is_set():
            await self._send_heartbeat()
            self._check_cpu_threshold()
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=self.heartbeat_interval
                )
                break
            except asyncio.TimeoutError:
                pass
        logger.info("Health reporter stopped")

    def get_metrics(self, event_queue_size: int = 0) -> HealthMetrics:
        """Collect current health metrics."""
        cpu = self._process.cpu_percent(interval=0.1)
        memory = self._process.memory_info().rss / (1024 * 1024)
        uptime = time.time() - self._start_time
        return HealthMetrics(
            cpu_percent=cpu,
            memory_mb=round(memory, 1),
            event_queue_size=event_queue_size,
            uptime_seconds=round(uptime, 1),
            throttle_active=self._throttle_active,
        )

    def _check_cpu_threshold(self) -> None:
        """Check if CPU usage exceeds the 3% budget and enable throttle."""
        cpu = self._process.cpu_percent(interval=0.1)
        now = time.time()

        if cpu > CPU_THRESHOLD_PERCENT:
            if self._cpu_exceeded_since is None:
                self._cpu_exceeded_since = now
            elif now - self._cpu_exceeded_since > CPU_THRESHOLD_DURATION_SECONDS:
                if not self._throttle_active:
                    self._throttle_active = True
                    logger.warning(
                        "CPU threshold exceeded: %.1f%% — enabling adaptive throttle",
                        cpu,
                    )
        else:
            self._cpu_exceeded_since = None
            if self._throttle_active:
                self._throttle_active = False
                logger.info("CPU below threshold, disabling throttle")

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to the backend."""
        try:
            metrics = self.get_metrics()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.backend_url}/api/v1/taskmining/heartbeat",
                    json={"agent_id": self.agent_id},
                    timeout=10.0,
                )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "revoked":
                    logger.warning("Agent has been revoked by the backend")
                elif data.get("status") == "expired":
                    logger.warning("Agent engagement has expired")
            else:
                logger.warning("Heartbeat failed: %d", response.status_code)
        except httpx.HTTPError as e:
            logger.warning("Heartbeat network error: %s", str(e))
