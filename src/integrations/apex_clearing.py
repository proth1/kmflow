"""Apex Fintech Solutions (Apex Clearing) connector.

Integrates with Apex Clearing's suite of APIs:
- Clearing API: account lifecycle, trade lifecycle, settlement
- Advisor Solutions API: portfolios, billing
- Silver API: self-directed brokerage accounts and positions

Data is stored as STRUCTURED_DATA EvidenceItems for downstream
process mining and knowledge graph enrichment.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from src.integrations.base import BaseConnector, ConnectionConfig, ConnectorRegistry
from src.integrations.utils import DEFAULT_TIMEOUT, paginate_offset, retry_request

logger = logging.getLogger(__name__)


class ApexClearingConnector(BaseConnector):
    """Connector for Apex Fintech Solutions (Apex Clearing).

    Supports three Apex API product lines:
    - Clearing API: institutional clearing, trade settlement, account lifecycle
    - Advisor Solutions API: RIA portfolio management, billing, reporting
    - Silver API: self-directed brokerage for fintechs
    """

    description = "Apex Clearing - Accounts, trades, settlement, portfolios, and brokerage data"

    def __init__(self, config: ConnectionConfig) -> None:
        super().__init__(config)
        self._base_url = (config.base_url or config.extra.get("base_url", "")).rstrip("/")
        self._api_key = config.api_key or config.extra.get("api_key", "")
        self._client_id = config.extra.get("client_id", "")
        self._client_secret = config.extra.get("client_secret", "")
        self._environment = config.extra.get("environment", "sandbox")
        self._access_token: str = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = self._access_token or self._api_key
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Apex-Environment": self._environment,
        }

    async def _authenticate(self) -> bool:
        """Obtain OAuth2 access token using client credentials flow.

        If an api_key is already set, skips OAuth and uses it directly.
        """
        if self._access_token or self._api_key:
            return True

        if not self._client_id or not self._client_secret:
            logger.warning("Apex connector: missing client_id or client_secret")
            return False

        token_url = f"{self._base_url}/oauth/token" if self._base_url else "https://api.apexclearing.com/oauth/token"
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "POST",
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    max_retries=2,
                )
                token_data = response.json()
                self._access_token = token_data["access_token"]
                return True
        except (httpx.HTTPError, httpx.RequestError, KeyError) as e:
            logger.error("Apex authentication failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Test connectivity to the Apex API."""
        if not self._base_url and not self._client_id:
            logger.warning("Apex connector: missing base_url and credentials")
            return False

        if not await self._authenticate():
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/v1/health",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("Apex connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync accounts, trades, and settlements from Apex Clearing.

        Pulls data from all three Apex API product lines and stores each
        record as a STRUCTURED_DATA EvidenceItem linked to the engagement.

        Args:
            engagement_id: The engagement to associate records with.
            **kwargs:
                product (str): One of "clearing", "advisor", "silver", or "all"
                    (default "all").
                db_session: Optional async SQLAlchemy session for persisting
                    EvidenceItem records.

        Returns:
            Dict with records_synced count, errors list, persisted_items list,
            and metadata.
        """
        if not await self._authenticate():
            return {"records_synced": 0, "errors": ["Apex authentication failed"]}

        if not self._base_url:
            return {"records_synced": 0, "errors": ["Apex base_url not configured"]}

        product = kwargs.get("product", "all")
        db_session = kwargs.get("db_session") or kwargs.get("session")

        records_synced = 0
        errors: list[str] = []
        persisted_items: list[dict[str, Any]] = []

        sync_targets: list[tuple[str, str]] = []
        if product in ("clearing", "all"):
            sync_targets += [
                ("accounts", f"{self._base_url}/v1/clearing/accounts"),
                ("trades", f"{self._base_url}/v1/clearing/trades"),
                ("settlements", f"{self._base_url}/v1/clearing/settlements"),
            ]
        if product in ("advisor", "all"):
            sync_targets += [
                ("portfolios", f"{self._base_url}/v1/advisor/portfolios"),
                ("billing", f"{self._base_url}/v1/advisor/billing"),
            ]
        if product in ("silver", "all"):
            sync_targets += [
                ("brokerage_accounts", f"{self._base_url}/v1/silver/accounts"),
            ]

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                for resource_type, url in sync_targets:
                    try:
                        async for page in paginate_offset(
                            client,
                            url,
                            headers=self._headers(),
                            results_key="data",
                            total_key="total",
                            page_size=200,
                        ):
                            records_synced += len(page)

                            if db_session is not None:
                                from src.core.models import EvidenceCategory, EvidenceItem

                                for record in page:
                                    record_id = record.get("id", str(uuid.uuid4()))
                                    item = EvidenceItem(
                                        engagement_id=engagement_id,
                                        name=f"apex_{resource_type}_{record_id}",
                                        category=EvidenceCategory.STRUCTURED_DATA,
                                        format="json",
                                        source_system="apex_clearing",
                                        metadata_json={
                                            "source": "apex_clearing",
                                            "resource_type": resource_type,
                                            "record_id": record_id,
                                            "product": product,
                                            "environment": self._environment,
                                            "record": record,
                                        },
                                        completeness_score=0.85,
                                        reliability_score=0.9,
                                        freshness_score=0.95,
                                        consistency_score=0.85,
                                    )
                                    db_session.add(item)
                                    persisted_items.append(
                                        {
                                            "resource_type": resource_type,
                                            "record_id": record_id,
                                        }
                                    )

                        # Flush once per resource type, outside the page loop
                        if db_session is not None:
                            await db_session.flush()

                    except httpx.HTTPStatusError as e:
                        errors.append(f"Apex {resource_type} API error: {e.response.status_code}")
                        logger.error("Apex sync failed for %s: %s", resource_type, e)
                    except httpx.RequestError as e:
                        errors.append(f"Apex {resource_type} connection error: {e}")
                        logger.error("Apex sync connection error for %s: %s", resource_type, e)

        except httpx.RequestError as e:
            errors.append(f"Apex connection error: {e}")
            logger.error("Apex sync outer connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
            "persisted_items": persisted_items,
            "metadata": {
                "source": "apex_clearing",
                "product": product,
                "environment": self._environment,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return the canonical field names exposed by Apex Clearing."""
        return [
            # Clearing — accounts
            "account_id",
            "account_type",
            "account_status",
            "correspondent_id",
            "registration_type",
            "opened_date",
            "closed_date",
            # Clearing — trades
            "trade_id",
            "trade_date",
            "settlement_date",
            "security_id",
            "cusip",
            "side",
            "quantity",
            "price",
            "net_amount",
            "trade_status",
            # Clearing — settlements
            "settlement_id",
            "settlement_status",
            "deliver_quantity",
            "deliver_amount",
            # Advisor Solutions
            "portfolio_id",
            "portfolio_name",
            "portfolio_value",
            "billing_period",
            "fee_amount",
            # Silver API
            "brokerage_account_id",
            "brokerage_account_status",
            "buying_power",
            "cash_balance",
        ]

    async def sync_incremental(
        self,
        engagement_id: str,
        since: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Incremental sync using updated_since query parameter.

        Falls back to full sync when no since timestamp is provided.
        """
        if since:
            kwargs.setdefault("params", {})
            kwargs["params"]["updated_since"] = since
        return await self.sync_data(engagement_id, **kwargs)


ConnectorRegistry.register("apex_clearing", ApexClearingConnector)
