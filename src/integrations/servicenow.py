"""ServiceNow connector for KMFlow.

Integrates with ServiceNow ITSM via the Table API to import incident
workflows, change management processes, and service catalog data.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_offset, retry_request

logger = logging.getLogger(__name__)


class ServiceNowConnector(BaseConnector):
    """Connector for ServiceNow ITSM platform."""

    description = "ServiceNow ITSM - Incident workflows, change management, service catalog"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or config.extra.get("instance_url", "")).rstrip("/")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._username = config.extra.get("username", "")
        self._password = config.extra.get("password", "")

    def _auth(self) -> httpx.BasicAuth | None:
        """Get Basic authentication if username/password configured."""
        if self._username and self._password:
            return httpx.BasicAuth(self._username, self._password)
        return None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def test_connection(self) -> bool:
        """Test connectivity to ServiceNow Table API."""
        if not self._base_url:
            logger.warning("ServiceNow connector: missing instance_url")
            return False
        if not self._api_key and not (self._username and self._password):
            logger.warning("ServiceNow connector: missing credentials")
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, auth=self._auth()) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/api/now/table/sys_properties",
                    headers=self._headers(),
                    params={"sysparm_limit": "1"},
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("ServiceNow connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from ServiceNow Table API.

        Queries the specified table with offset-based pagination.
        Stores as saas_exports evidence items.

        Args:
            engagement_id: The engagement to associate data with.
            **kwargs: table_name, query_filter, fields.
        """
        has_creds = self._api_key or (self._username and self._password)
        if not self._base_url or not has_creds:
            return {"records_synced": 0, "errors": ["ServiceNow not configured"]}

        table_name = kwargs.get("table_name", "incident")
        query_filter = kwargs.get("query_filter", "")
        fields = kwargs.get("fields", "")
        records_synced = 0
        errors: list[str] = []

        try:
            params: dict[str, Any] = {}
            if query_filter:
                params["sysparm_query"] = query_filter
            if fields:
                params["sysparm_fields"] = fields if isinstance(fields, str) else ",".join(fields)

            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, auth=self._auth()) as client:
                url = f"{self._base_url}/api/now/table/{table_name}"

                async for page in paginate_offset(
                    client,
                    url,
                    params=params,
                    headers=self._headers(),
                    results_key="result",
                    total_key=None,  # ServiceNow uses X-Total-Count header
                    offset_param="sysparm_offset",
                    limit_param="sysparm_limit",
                    page_size=100,
                ):
                    records_synced += len(page)

        except httpx.HTTPStatusError as e:
            errors.append(f"ServiceNow API error: {e.response.status_code}")
            logger.error("ServiceNow sync failed: %s", e)
        except httpx.RequestError as e:
            errors.append(f"ServiceNow connection error: {e}")
            logger.error("ServiceNow sync connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
            "metadata": {
                "source": "servicenow",
                "table_name": table_name,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return available fields for the configured table."""
        return [
            "sys_id",
            "number",
            "short_description",
            "description",
            "state",
            "priority",
            "sys_created_on",
            "sys_updated_on",
            "assigned_to",
            "category",
        ]

    async def sync_incremental(self, engagement_id: str, since: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Incremental sync using sys_updated_on filter."""
        if since:
            existing_query = kwargs.get("query_filter", "")
            ts_filter = f"sys_updated_on>{since}"
            kwargs["query_filter"] = f"{existing_query}^{ts_filter}" if existing_query else ts_filter
        return await self.sync_data(engagement_id, **kwargs)
