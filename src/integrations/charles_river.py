"""Charles River Development (CRD) Investment Management System connector.

Integrates with Charles River IMS APIs:
- Trade Order Management: order lifecycle, execution, blotter
- Portfolio Analytics: holdings, performance, attribution
- Compliance Pre-Trade: rule evaluation, order blocking
- Post-Trade Allocation: allocation records, confirms

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


class CharlesRiverConnector(BaseConnector):
    """Connector for Charles River Development (CRD) Investment Management System.

    Covers the four primary IMS capability areas:
    - Trade Order Management (TOM): order creation, routing, execution
    - Portfolio Analytics: holdings, performance, benchmark comparison
    - Compliance: pre-trade rule checks, violation tracking
    - Post-Trade Allocation: trade allocation and confirmation
    """

    description = "Charles River IMS - Trade orders, portfolio analytics, compliance, and allocations"

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
            "X-CRD-Environment": self._environment,
        }

    async def _authenticate(self) -> bool:
        """Obtain OAuth2 access token using client credentials flow.

        If an api_key is already set, skips OAuth and uses it directly.
        """
        if self._access_token or self._api_key:
            return True

        if not self._client_id or not self._client_secret:
            logger.warning("CRD connector: missing client_id or client_secret")
            return False

        token_url = f"{self._base_url}/oauth2/token" if self._base_url else "https://api.charlesriver.com/oauth2/token"
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
            logger.error("CRD authentication failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Test connectivity to the Charles River IMS API."""
        if not self._base_url and not self._client_id:
            logger.warning("CRD connector: missing base_url and credentials")
            return False

        if not await self._authenticate():
            return False

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await retry_request(
                    client,
                    "GET",
                    f"{self._base_url}/api/v1/health",
                    headers=self._headers(),
                    max_retries=1,
                )
                return response.status_code == 200
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.warning("CRD connection test failed: %s", e)
            return False

    async def sync_data(self, engagement_id: str, **kwargs: Any) -> dict[str, Any]:
        """Sync trade orders, portfolios, compliance checks, and allocations from CRD.

        Pulls data across CRD's four primary domains and stores each record
        as a STRUCTURED_DATA EvidenceItem linked to the engagement.

        Args:
            engagement_id: The engagement to associate records with.
            **kwargs:
                domain (str): One of "orders", "portfolios", "compliance",
                    "allocations", or "all" (default "all").
                db_session: Optional async SQLAlchemy session for persisting
                    EvidenceItem records.

        Returns:
            Dict with records_synced count, errors list, persisted_items list,
            and metadata.
        """
        if not await self._authenticate():
            return {"records_synced": 0, "errors": ["CRD authentication failed"]}

        if not self._base_url:
            return {"records_synced": 0, "errors": ["CRD base_url not configured"]}

        domain = kwargs.get("domain", "all")
        db_session = kwargs.get("db_session") or kwargs.get("session")

        records_synced = 0
        errors: list[str] = []
        persisted_items: list[dict[str, Any]] = []

        sync_targets: list[tuple[str, str]] = []
        if domain in ("orders", "all"):
            sync_targets += [
                ("orders", f"{self._base_url}/api/v1/orders"),
            ]
        if domain in ("portfolios", "all"):
            sync_targets += [
                ("portfolios", f"{self._base_url}/api/v1/portfolios"),
                ("holdings", f"{self._base_url}/api/v1/portfolios/holdings"),
            ]
        if domain in ("compliance", "all"):
            sync_targets += [
                ("compliance_checks", f"{self._base_url}/api/v1/compliance/pre-trade"),
            ]
        if domain in ("allocations", "all"):
            sync_targets += [
                ("allocations", f"{self._base_url}/api/v1/allocations"),
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
                                    record_id = record.get("order_id") or record.get("id", str(uuid.uuid4()))
                                    item = EvidenceItem(
                                        engagement_id=engagement_id,
                                        name=f"crd_{resource_type}_{record_id}",
                                        category=EvidenceCategory.STRUCTURED_DATA,
                                        format="json",
                                        source_system="charles_river",
                                        metadata_json={
                                            "source": "charles_river",
                                            "resource_type": resource_type,
                                            "record_id": record_id,
                                            "domain": domain,
                                            "environment": self._environment,
                                            # CRD canonical fields
                                            "order_id": record.get("order_id", ""),
                                            "portfolio_id": record.get("portfolio_id", ""),
                                            "security_id": record.get("security_id", ""),
                                            "trade_type": record.get("trade_type", ""),
                                            "quantity": record.get("quantity"),
                                            "price": record.get("price"),
                                            "allocation_target": record.get("allocation_target", ""),
                                            "compliance_status": record.get("compliance_status", ""),
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
                                            "order_id": record.get("order_id", ""),
                                            "portfolio_id": record.get("portfolio_id", ""),
                                        }
                                    )

                        # Flush once per resource type, outside the page loop
                        if db_session is not None:
                            await db_session.flush()

                    except httpx.HTTPStatusError as e:
                        errors.append(f"CRD {resource_type} API error: {e.response.status_code}")
                        logger.error("CRD sync failed for %s: %s", resource_type, e)
                    except httpx.RequestError as e:
                        errors.append(f"CRD {resource_type} connection error: {e}")
                        logger.error("CRD sync connection error for %s: %s", resource_type, e)

        except httpx.RequestError as e:
            errors.append(f"CRD connection error: {e}")
            logger.error("CRD sync outer connection error: %s", e)

        return {
            "records_synced": records_synced,
            "errors": errors,
            "persisted_items": persisted_items,
            "metadata": {
                "source": "charles_river",
                "domain": domain,
                "environment": self._environment,
                "engagement_id": engagement_id,
            },
        }

    async def get_schema(self) -> list[str]:
        """Return canonical CRD field names across all four domains."""
        return [
            # Trade Order Management
            "order_id",
            "portfolio_id",
            "security_id",
            "trade_type",
            "quantity",
            "price",
            "order_status",
            "trader_id",
            "broker_id",
            "execution_venue",
            "order_date",
            "execution_date",
            # Portfolio Analytics
            "portfolio_name",
            "portfolio_value",
            "benchmark_id",
            "performance_ytd",
            "holding_quantity",
            "holding_market_value",
            "weight",
            # Compliance
            "compliance_status",
            "rule_id",
            "rule_name",
            "violation_type",
            "override_user",
            "override_reason",
            # Post-Trade Allocation
            "allocation_target",
            "allocation_id",
            "allocation_status",
            "allocated_quantity",
            "allocated_price",
            "confirm_date",
        ]

    async def sync_incremental(
        self,
        engagement_id: str,
        since: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Incremental sync using modified_since query parameter.

        Falls back to full sync when no since timestamp is provided.
        """
        if since:
            kwargs.setdefault("params", {})
            kwargs["params"]["modified_since"] = since
        return await self.sync_data(engagement_id, **kwargs)


ConnectorRegistry.register("charles_river", CharlesRiverConnector)
