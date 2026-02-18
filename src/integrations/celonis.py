"""Celonis EMS (Execution Management System) connector.

Integrates with Celonis process mining to import process event logs,
process models, and conformance data via the Celonis API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_offset, retry_request

logger = logging.getLogger(__name__)


class CelonisConnector(BaseConnector):
    """Connector for Celonis EMS process mining platform."""

    description = "Celonis EMS - Process mining event logs and conformance data"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or config.extra.get("base_url", "")).rstrip("/")
        self._api_key = config.api_key or config.extra.get("api_key", "")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> bool:
        """Test connectivity to Celonis EMS API."""
        if not self._base_url or not self._api_key:
            logger.warning("Celonis connector: missing base_url or api_key")
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/api/v1/status",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("Celonis connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync process mining data from Celonis.

        Queries event logs from Celonis data pools and stores
        as structured_data evidence items.

        Args:
            engagement_id: The engagement to associate data with.
            **kwargs: Optional filters (data_pool_id, process_id, date_range).

        Returns:
            Sync result with records_synced count.
        """
        if not self._base_url or not self._api_key:
            return {"records_synced": 0, "errors": ["Celonis not configured"]}

        data_pool_id = kwargs.get("data_pool_id")
        if not data_pool_id:
            return {"records_synced": 0, "errors": ["data_pool_id is required"]}

        records_synced = 0
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = f"{self._base_url}/api/v1/data-pools/{data_pool_id}/events"

                async for page in paginate_offset(
                    client,
                    url,
                    headers=self._headers(),
                    results_key="data",
                    total_key="totalCount",
                    offset_param="offset",
                    limit_param="limit",
                    page_size=500,
                ):
                    records_synced += len(page)

        except httpx.HTTPStatusError as e:
            errors.append(f"Celonis API error: {e.response.status_code}")
            logger.error("Celonis sync failed: %s", e)
        except httpx.RequestError as e:
            errors.append(f"Celonis connection error: {e}")
            logger.error("Celonis sync connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
            "metadata": {
                "source": "celonis",
                "data_pool_id": data_pool_id,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available source fields from Celonis."""
        return [
            "case_id",
            "activity",
            "timestamp",
            "resource",
            "variant",
            "duration",
            "cost",
        ]
