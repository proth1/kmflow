"""Configuration manager: pulls capture config from the KMFlow backend.

Periodically fetches GET /api/v1/taskmining/config/{agent_id} and caches
the response locally. Falls back to cached config when offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.expanduser("~/Library/Application Support/KMFlowAgent")
REFRESH_INTERVAL_SECONDS = 1800  # 30 minutes


@dataclass
class EngagementConfig:
    """Parsed capture configuration from the backend."""

    capture_granularity: str = "action_level"
    app_allowlist: list[str] | None = None
    app_blocklist: list[str] | None = None
    url_domain_only: bool = True
    screenshot_enabled: bool = False
    screenshot_interval_seconds: int = 30
    batch_size: int = 1000
    batch_interval_seconds: int = 30
    idle_timeout_seconds: int = 300
    pii_patterns_version: str = "1.0"


class ConfigManager:
    """Manages agent configuration with periodic server refresh."""

    def __init__(
        self,
        backend_url: str,
        agent_id: str,
        http_client: httpx.AsyncClient | None = None,
        refresh_interval: int = REFRESH_INTERVAL_SECONDS,
    ) -> None:
        self.backend_url = backend_url
        self.agent_id = agent_id
        self._client = http_client
        self.refresh_interval = refresh_interval
        self._config = EngagementConfig()
        self._cache_path = os.path.join(CACHE_DIR, "config_cache.json")
        self._load_cached()

    @property
    def config(self) -> EngagementConfig:
        return self._config

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Periodically refresh configuration from the backend."""
        logger.info("Config manager started (refresh=%ds)", self.refresh_interval)
        while not shutdown_event.is_set():
            await self._refresh()
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=self.refresh_interval
                )
                break
            except asyncio.TimeoutError:
                pass
        logger.info("Config manager stopped")

    async def _refresh(self) -> None:
        """Fetch config from the backend and update local state."""
        if self._client is None:
            return
        try:
            response = await self._client.get(
                f"{self.backend_url}/api/v1/taskmining/config/{self.agent_id}",
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                self._apply_config(data)
                self._save_cache(data)
                logger.info("Config refreshed from backend")
            else:
                logger.warning("Config refresh failed: %d", response.status_code)
        except httpx.HTTPError as e:
            logger.warning("Config refresh network error: %s", str(e))

    def _apply_config(self, data: dict[str, Any]) -> None:
        """Apply config data to the EngagementConfig."""
        self._config = EngagementConfig(
            capture_granularity=data.get("capture_granularity", "action_level"),
            app_allowlist=data.get("app_allowlist"),
            app_blocklist=data.get("app_blocklist"),
            url_domain_only=data.get("url_domain_only", True),
            screenshot_enabled=data.get("screenshot_enabled", False),
            screenshot_interval_seconds=data.get("screenshot_interval_seconds", 30),
            batch_size=data.get("batch_size", 1000),
            batch_interval_seconds=data.get("batch_interval_seconds", 30),
            idle_timeout_seconds=data.get("idle_timeout_seconds", 300),
            pii_patterns_version=data.get("pii_patterns_version", "1.0"),
        )

    def _save_cache(self, data: dict[str, Any]) -> None:
        """Cache config to disk for offline fallback."""
        try:
            Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, "w") as f:
                json.dump(data, f)
        except OSError:
            logger.warning("Failed to cache config")

    def _load_cached(self) -> None:
        """Load cached config from disk if available."""
        try:
            with open(self._cache_path) as f:
                data = json.load(f)
            self._apply_config(data)
            logger.info("Loaded cached config")
        except (OSError, json.JSONDecodeError):
            pass  # No cache or invalid — use defaults
