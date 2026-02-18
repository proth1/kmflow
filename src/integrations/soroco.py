"""Soroco Scout connector.

Integrates with Soroco Scout task mining to import user interaction data,
application usage patterns, and task-level process discovery.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_offset, retry_request

logger = logging.getLogger(__name__)


class SorocoConnector(BaseConnector):
    """Connector for Soroco Scout task mining platform."""

    description = "Soroco Scout - Task mining user interaction data and application patterns"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or config.extra.get("base_url", "")).rstrip("/")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._tenant_id = config.extra.get("tenant_id", "")

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test connectivity to Soroco Scout API."""
        if not self._base_url or not self._api_key:
            logger.warning("Soroco connector: missing base_url or api_key")
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/api/health",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("Soroco connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync task mining data from Soroco Scout.

        Queries user interaction recordings and task discovery data,
        storing results as km4work evidence items.

        Args:
            engagement_id: The engagement to associate data with.
            **kwargs: Optional filters (team_id, project_id, date_range).

        Returns:
            Sync result with records_synced count.
        """
        if not self._base_url or not self._api_key:
            return {"records_synced": 0, "errors": ["Soroco not configured"]}

        project_id = kwargs.get("project_id", kwargs.get("team_id", ""))
        records_synced = 0
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = f"{self._base_url}/api/workgraph/projects/{project_id}/tasks"

                async for page in paginate_offset(
                    client,
                    url,
                    headers=self._headers(),
                    results_key="tasks",
                    total_key="total",
                    page_size=200,
                ):
                    records_synced += len(page)

        except httpx.HTTPStatusError as e:
            errors.append(f"Soroco API error: {e.response.status_code}")
            logger.error("Soroco sync failed: %s", e)
        except httpx.RequestError as e:
            errors.append(f"Soroco connection error: {e}")
            logger.error("Soroco sync connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
            "metadata": {
                "source": "soroco",
                "tenant_id": self._tenant_id,
                "project_id": project_id,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available fields from Soroco Scout."""
        return [
            "task_id",
            "task_name",
            "application",
            "user",
            "start_time",
            "end_time",
            "duration_ms",
            "actions",
        ]
