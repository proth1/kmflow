"""Salesforce connector for KMFlow.

Integrates with Salesforce CRM via OAuth2 client credentials flow
and REST API for SOQL queries and data extraction.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_cursor, retry_request

logger = logging.getLogger(__name__)

VALID_SOBJECT_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
VALID_FIELD_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def _validate_sobject_name(name: str) -> str:
    if not VALID_SOBJECT_PATTERN.match(name):
        raise ValueError(f"Invalid Salesforce object name: {name}")
    return name


def _validate_field_name(name: str) -> str:
    if not VALID_FIELD_PATTERN.match(name):
        raise ValueError(f"Invalid Salesforce field name: {name}")
    return name


class SalesforceConnector(BaseConnector):
    """Connector for Salesforce CRM."""

    description = "Salesforce CRM - Case workflows, approval chains, and process data"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._instance_url = (config.base_url or config.extra.get("instance_url", "")).rstrip("/")
        self._client_id = config.extra.get("client_id", "")
        self._client_secret = config.extra.get("client_secret", "")
        self._access_token = config.api_key or config.extra.get("access_token", "")
        self._api_version = config.extra.get("api_version", "v59.0")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def _authenticate(self) -> bool:
        """Authenticate with Salesforce using OAuth2 client credentials."""
        if self._access_token:
            return True

        if not self._client_id or not self._client_secret:
            return False

        try:
            login_url = self._instance_url or "https://login.salesforce.com"
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "POST",
                    f"{login_url}/services/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    max_retries=2,
                )
                token_data = response.json()
                self._access_token = token_data["access_token"]
                if not self._instance_url:
                    self._instance_url = token_data.get("instance_url", self._instance_url)
                return True
        except (httpx.HTTPError, httpx.RequestError, KeyError) as e:
            logger.error("Salesforce authentication failed: %s", e)
            return False

    async def test_connection(self) -> bool:
        """Test connectivity to Salesforce API."""
        if not self._instance_url and not self._client_id:
            logger.warning("Salesforce connector: missing instance_url or credentials")
            return False

        if not await self._authenticate():
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._instance_url}/services/data/{self._api_version}/",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("Salesforce connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync data from Salesforce using SOQL queries.

        Queries specified object types and paginates through results.
        Stores as saas_exports evidence items.

        Args:
            engagement_id: The engagement to associate data with.
            **kwargs: object_type (default "Case"), soql_query, fields.
        """
        if not await self._authenticate():
            return {"records_synced": 0, "errors": ["Salesforce authentication failed"]}

        object_type = _validate_sobject_name(kwargs.get("object_type", "Case"))
        fields = [_validate_field_name(f) for f in kwargs.get("fields", ["Id", "Name", "Description", "CreatedDate", "Status"])]
        # _soql_override is set internally by sync_incremental for WHERE-clause queries only
        soql = kwargs.get("_soql_override") or f"SELECT {', '.join(fields)} FROM {object_type}"

        records_synced = 0
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = f"{self._instance_url}/services/data/{self._api_version}/query/"

                async for page in paginate_cursor(
                    client,
                    url,
                    params={"q": soql},
                    headers=self._headers(),
                    results_key="records",
                    next_url_key="nextRecordsUrl",
                ):
                    records_synced += len(page)

        except httpx.HTTPStatusError as e:
            errors.append(f"Salesforce API error: {e.response.status_code}")
            logger.error("Salesforce sync failed: %s", e)
        except httpx.RequestError as e:
            errors.append(f"Salesforce connection error: {e}")
            logger.error("Salesforce sync connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
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
        """Incremental sync using LastModifiedDate filter."""
        if since:
            object_type = _validate_sobject_name(kwargs.get("object_type", "Case"))
            fields = [_validate_field_name(f) for f in kwargs.get("fields", ["Id", "Name", "Description", "CreatedDate", "Status"])]
            # Build SOQL directly here so sync_data does not need to accept a raw soql_query
            kwargs["_soql_override"] = f"SELECT {', '.join(fields)} FROM {object_type} WHERE LastModifiedDate > {since}"
            kwargs["object_type"] = object_type
            kwargs["fields"] = fields
        return await self.sync_data(engagement_id, **kwargs)
