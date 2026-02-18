"""SAP connector for KMFlow.

Integrates with SAP systems via OData API to import process execution
data, transaction logs, and organizational structures.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_cursor, retry_request

logger = logging.getLogger(__name__)


class SAPConnector(BaseConnector):
    """Connector for SAP ERP/S4HANA systems."""

    description = "SAP ERP/S4HANA - Transaction logs, process execution data, org structures"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or config.extra.get("base_url", "")).rstrip("/")
        self._username = config.extra.get("username", "")
        self._password = config.extra.get("password", "")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._client = config.extra.get("client", "100")
        self._system_id = config.extra.get("system_id", "")

    def _auth(self) -> httpx.BasicAuth | None:
        """Get Basic authentication for SAP OData."""
        if self._username and self._password:
            return httpx.BasicAuth(self._username, self._password)
        return None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "sap-client": self._client,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def test_connection(self) -> bool:
        """Test connectivity to SAP OData API."""
        if not self._base_url:
            logger.warning("SAP connector: missing base_url")
            return False
        if not self._api_key and not (self._username and self._password):
            logger.warning("SAP connector: missing credentials")
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, auth=self._auth()) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/sap/opu/odata/sap/API_BUSINESS_PARTNER/",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("SAP connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from SAP via OData.

        Queries the specified entity set with OData pagination.
        Stores as saas_exports evidence items.

        Args:
            engagement_id: The engagement to associate data with.
            **kwargs: entity_set, select_fields, filter_query.
        """
        if not self._base_url:
            return {"records_synced": 0, "errors": ["SAP not configured"]}

        entity_set = kwargs.get("entity_set", "ZProcessLogs")
        select = kwargs.get("select_fields", "")
        filter_query = kwargs.get("filter_query", "")
        records_synced = 0
        errors: list[str] = []

        try:
            params: dict[str, str] = {"$format": "json", "$top": "500"}
            if select:
                params["$select"] = select
            if filter_query:
                params["$filter"] = filter_query

            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, auth=self._auth()) as client:
                url = f"{self._base_url}/sap/opu/odata/sap/{entity_set}"

                async for page in paginate_cursor(
                    client,
                    url,
                    params=params,
                    headers=self._headers(),
                    results_key="d",
                    next_url_key="__next",
                ):
                    # SAP OData wraps results in d.results
                    results = page if isinstance(page, list) else page.get("results", [page])
                    records_synced += len(results) if isinstance(results, list) else 1

        except httpx.HTTPStatusError as e:
            errors.append(f"SAP OData error: {e.response.status_code}")
            logger.error("SAP sync failed: %s", e)
        except httpx.RequestError as e:
            errors.append(f"SAP connection error: {e}")
            logger.error("SAP sync connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
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
        """Incremental sync using timestamp filter."""
        if since:
            existing_filter = kwargs.get("filter_query", "")
            ts_filter = f"AEDAT ge datetime'{since}'"
            kwargs["filter_query"] = f"{existing_filter} and {ts_filter}" if existing_filter else ts_filter
        return await self.sync_data(engagement_id, **kwargs)
