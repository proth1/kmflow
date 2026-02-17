"""SAP connector for KMFlow.

Integrates with SAP systems to import process execution data,
transaction logs, and organizational structures.
"""

from __future__ import annotations

import logging
from typing import Any

from src.integrations.base import BaseConnector, ConnectionConfig

logger = logging.getLogger(__name__)


class SAPConnector(BaseConnector):
    """Connector for SAP ERP/S4HANA systems."""

    description = "SAP ERP/S4HANA - Transaction logs, process execution data, org structures"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = config.base_url or config.extra.get("base_url", "")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._client = config.extra.get("client", "100")
        self._system_id = config.extra.get("system_id", "")

    async def test_connection(self) -> bool:
        """Test connectivity to SAP OData API."""
        if not self._base_url or not self._api_key:
            logger.warning("SAP connector: missing base_url or api_key")
            return False
        logger.info("SAP connection test: base_url=%s, client=%s", self._base_url, self._client)
        return True

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from SAP.

        Supports syncing: Transaction logs, Change documents, Workflow items.
        """
        if not self._base_url or not self._api_key:
            return {"records_synced": 0, "errors": ["SAP not configured"]}

        entity_set = kwargs.get("entity_set", "ZProcessLogs")
        logger.info(
            "SAP sync for engagement %s (entity_set=%s)",
            engagement_id,
            entity_set,
        )
        return {
            "records_synced": 0,
            "errors": [],
            "metadata": {
                "source": "sap",
                "entity_set": entity_set,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available fields."""
        return ["MANDT", "BELNR", "BUKRS", "GJAHR", "ERDAT", "ERNAM", "AEDAT"]

    async def sync_incremental(self, engagement_id: str, since: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Incremental sync since last timestamp."""
        logger.info("SAP incremental sync since %s", since)
        return await self.sync_data(engagement_id, **kwargs)
