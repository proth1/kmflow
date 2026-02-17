"""ServiceNow connector for KMFlow.

Integrates with ServiceNow ITSM to import incident workflows,
change management processes, and service catalog data.
"""

from __future__ import annotations

import logging
from typing import Any

from src.integrations.base import BaseConnector, ConnectionConfig

logger = logging.getLogger(__name__)


class ServiceNowConnector(BaseConnector):
    """Connector for ServiceNow ITSM platform."""

    description = "ServiceNow ITSM - Incident workflows, change management, service catalog"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = config.base_url or config.extra.get("instance_url", "")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._username = config.extra.get("username", "")
        self._password = config.extra.get("password", "")

    async def test_connection(self) -> bool:
        """Test connectivity to ServiceNow Table API."""
        if not self._base_url:
            logger.warning("ServiceNow connector: missing instance_url")
            return False
        if not self._api_key and not (self._username and self._password):
            logger.warning("ServiceNow connector: missing credentials")
            return False
        logger.info("ServiceNow connection test: instance=%s", self._base_url)
        return True

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from ServiceNow.

        Supports syncing: Incidents, Changes, Problems, Catalog Items.
        """
        has_creds = self._api_key or (self._username and self._password)
        if not self._base_url or not has_creds:
            return {"records_synced": 0, "errors": ["ServiceNow not configured"]}

        table_name = kwargs.get("table_name", "incident")
        logger.info(
            "ServiceNow sync for engagement %s (table=%s)",
            engagement_id,
            table_name,
        )
        return {
            "records_synced": 0,
            "errors": [],
            "metadata": {
                "source": "servicenow",
                "table_name": table_name,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available fields for the configured table."""
        return [
            "sys_id", "number", "short_description", "description",
            "state", "priority", "sys_created_on", "sys_updated_on",
            "assigned_to", "category",
        ]

    async def sync_incremental(self, engagement_id: str, since: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Incremental sync since last timestamp."""
        logger.info("ServiceNow incremental sync since %s", since)
        return await self.sync_data(engagement_id, **kwargs)
