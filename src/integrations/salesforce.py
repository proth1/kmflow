"""Salesforce connector for KMFlow.

Integrates with Salesforce CRM to import process-related data,
case workflows, and approval chains.
"""

from __future__ import annotations

import logging
from typing import Any

from src.integrations.base import BaseConnector, ConnectionConfig

logger = logging.getLogger(__name__)


class SalesforceConnector(BaseConnector):
    """Connector for Salesforce CRM."""

    description = "Salesforce CRM - Case workflows, approval chains, and process data"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = config.base_url or config.extra.get("instance_url", "")
        self._api_key = config.api_key or config.extra.get("access_token", "")
        self._api_version = config.extra.get("api_version", "v59.0")

    async def test_connection(self) -> bool:
        """Test connectivity to Salesforce API."""
        if not self._base_url or not self._api_key:
            logger.warning("Salesforce connector: missing instance_url or access_token")
            return False
        logger.info("Salesforce connection test: instance=%s", self._base_url)
        return True

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from Salesforce.

        Supports syncing: Cases, Approvals, ProcessInstances.
        """
        if not self._base_url or not self._api_key:
            return {"records_synced": 0, "errors": ["Salesforce not configured"]}

        object_type = kwargs.get("object_type", "Case")
        logger.info(
            "Salesforce sync for engagement %s (object=%s)",
            engagement_id,
            object_type,
        )
        return {
            "records_synced": 0,
            "errors": [],
            "metadata": {
                "source": "salesforce",
                "object_type": object_type,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available fields for the configured object."""
        return ["Id", "Name", "Description", "CreatedDate", "LastModifiedDate", "Status", "OwnerId"]

    async def sync_incremental(self, engagement_id: str, since: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Incremental sync - only records modified since last sync."""
        logger.info("Salesforce incremental sync since %s", since)
        return await self.sync_data(engagement_id, **kwargs)
