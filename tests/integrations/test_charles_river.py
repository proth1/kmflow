"""Tests for the Charles River Development (CRD) integration connector."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.base import ConnectionConfig, ConnectorRegistry
from src.integrations.charles_river import CharlesRiverConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://api.charlesriver.com"),
    )


def _config(
    base_url: str = "https://api.charlesriver.com",
    api_key: str = "test-crd-token",
    environment: str = "sandbox",
) -> ConnectionConfig:
    return ConnectionConfig(
        base_url=base_url,
        api_key=api_key,
        extra={"environment": environment},
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestCharlesRiverRegistration:
    """Connector is registered in ConnectorRegistry."""

    def test_registered_as_charles_river(self) -> None:
        cls = ConnectorRegistry.get("charles_river")
        assert cls is CharlesRiverConnector

    def test_description_present(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        assert "Charles River" in connector.description


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestCharlesRiverInit:
    """Constructor correctly reads ConnectionConfig."""

    def test_base_url_stripped(self) -> None:
        config = ConnectionConfig(base_url="https://api.charlesriver.com/")
        connector = CharlesRiverConnector(config)
        assert connector._base_url == "https://api.charlesriver.com"

    def test_api_key_from_config(self) -> None:
        config = ConnectionConfig(api_key="crd-key-xyz")
        connector = CharlesRiverConnector(config)
        assert connector._api_key == "crd-key-xyz"

    def test_client_credentials_from_extra(self) -> None:
        config = ConnectionConfig(extra={"client_id": "crd-cid", "client_secret": "crd-sec"})
        connector = CharlesRiverConnector(config)
        assert connector._client_id == "crd-cid"
        assert connector._client_secret == "crd-sec"

    def test_default_environment_is_sandbox(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        assert connector._environment == "sandbox"

    def test_environment_override_to_production(self) -> None:
        config = ConnectionConfig(extra={"environment": "production"})
        connector = CharlesRiverConnector(config)
        assert connector._environment == "production"

    def test_access_token_initially_empty(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        assert connector._access_token == ""


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverAuthentication:
    """_authenticate() logic."""

    async def test_authenticate_skips_when_api_key_present(self) -> None:
        connector = CharlesRiverConnector(_config())
        result = await connector._authenticate()
        assert result is True

    async def test_authenticate_skips_when_access_token_cached(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        connector._access_token = "cached"
        result = await connector._authenticate()
        assert result is True

    async def test_authenticate_returns_false_without_credentials(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        result = await connector._authenticate()
        assert result is False

    async def test_authenticate_success_sets_access_token(self) -> None:
        config = ConnectionConfig(
            base_url="https://api.charlesriver.com",
            extra={"client_id": "cid", "client_secret": "csec"},
        )
        connector = CharlesRiverConnector(config)
        token_response = _mock_response(200, {"access_token": "fresh-crd-token"})
        with patch("src.integrations.charles_river.retry_request", return_value=token_response):
            result = await connector._authenticate()
        assert result is True
        assert connector._access_token == "fresh-crd-token"

    async def test_authenticate_http_error_returns_false(self) -> None:
        config = ConnectionConfig(
            base_url="https://api.charlesriver.com",
            extra={"client_id": "cid", "client_secret": "csec"},
        )
        connector = CharlesRiverConnector(config)
        with patch("src.integrations.charles_river.retry_request", side_effect=httpx.ConnectError("timeout")):
            result = await connector._authenticate()
        assert result is False

    async def test_authenticate_missing_token_key_returns_false(self) -> None:
        config = ConnectionConfig(
            base_url="https://api.charlesriver.com",
            extra={"client_id": "cid", "client_secret": "csec"},
        )
        connector = CharlesRiverConnector(config)
        bad_response = _mock_response(200, {"expires_in": 3600})  # no access_token
        with patch("src.integrations.charles_river.retry_request", return_value=bad_response):
            result = await connector._authenticate()
        assert result is False


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverTestConnection:
    """test_connection() behaviour."""

    async def test_missing_url_and_credentials_returns_false(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        result = await connector.test_connection()
        assert result is False

    async def test_auth_failure_returns_false(self) -> None:
        config = ConnectionConfig(base_url="https://api.charlesriver.com")
        connector = CharlesRiverConnector(config)
        result = await connector.test_connection()
        assert result is False

    async def test_success_returns_true(self) -> None:
        connector = CharlesRiverConnector(_config())
        ok_response = _mock_response(200)
        with patch("src.integrations.charles_river.retry_request", return_value=ok_response):
            result = await connector.test_connection()
        assert result is True

    async def test_non_200_returns_false(self) -> None:
        connector = CharlesRiverConnector(_config())
        with patch("src.integrations.charles_river.retry_request", return_value=_mock_response(503)):
            result = await connector.test_connection()
        assert result is False

    async def test_request_error_returns_false(self) -> None:
        connector = CharlesRiverConnector(_config())
        with patch("src.integrations.charles_river.retry_request", side_effect=httpx.ConnectError("fail")):
            result = await connector.test_connection()
        assert result is False


# ---------------------------------------------------------------------------
# sync_data — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverSyncDataErrors:
    """sync_data() error paths."""

    async def test_auth_failure_returns_zero_records(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert any("authentication" in e.lower() for e in result["errors"])

    async def test_missing_base_url_returns_error(self) -> None:
        config = ConnectionConfig(api_key="tok")
        connector = CharlesRiverConnector(config)
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert any("base_url" in e.lower() for e in result["errors"])

    async def test_http_status_error_recorded(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def raise_status(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "401",
                request=httpx.Request("GET", "https://api.charlesriver.com"),
                response=_mock_response(401),
            )
            yield  # makes this an async generator so paginate_offset can iterate it

        with patch("src.integrations.charles_river.paginate_offset", side_effect=raise_status):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0
        assert "401" in result["errors"][0]

    async def test_request_error_recorded(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def raise_connect(*args, **kwargs):
            raise httpx.ConnectError("network down")
            yield  # makes this an async generator so paginate_offset can iterate it

        with patch("src.integrations.charles_river.paginate_offset", side_effect=raise_connect):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# sync_data — successful paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverSyncDataSuccess:
    """sync_data() happy paths."""

    async def test_sync_all_domains_counts_records(self) -> None:
        connector = CharlesRiverConnector(_config())
        sample_page = [{"order_id": f"ord-{i}", "portfolio_id": f"port-{i}"} for i in range(4)]

        async def mock_paginate(*args, **kwargs):
            yield sample_page

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        # 5 resource endpoints × 4 records each
        assert result["records_synced"] == 20
        assert result["errors"] == []
        assert result["metadata"]["source"] == "charles_river"
        assert result["metadata"]["domain"] == "all"
        assert result["metadata"]["engagement_id"] == "eng-001"

    async def test_sync_orders_domain_only(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"order_id": "o1"}, {"order_id": "o2"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", domain="orders")

        # 1 endpoint × 2 records
        assert result["records_synced"] == 2
        assert result["metadata"]["domain"] == "orders"

    async def test_sync_portfolios_domain_only(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"portfolio_id": "p1"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", domain="portfolios")

        # 2 portfolio endpoints (portfolios + holdings) × 1 record each
        assert result["records_synced"] == 2

    async def test_sync_compliance_domain_only(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"order_id": "c1", "compliance_status": "passed"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", domain="compliance")

        assert result["records_synced"] == 1
        assert result["metadata"]["domain"] == "compliance"

    async def test_sync_allocations_domain_only(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"allocation_id": "al1"}, {"allocation_id": "al2"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", domain="allocations")

        assert result["records_synced"] == 2
        assert result["metadata"]["domain"] == "allocations"

    async def test_metadata_environment_field(self) -> None:
        connector = CharlesRiverConnector(_config(environment="production"))

        async def mock_paginate(*args, **kwargs):
            yield []

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-prod")

        assert result["metadata"]["environment"] == "production"

    async def test_persists_evidence_items_when_session_provided(self) -> None:
        connector = CharlesRiverConnector(_config())
        mock_session = AsyncMock()

        trade_record = {
            "order_id": "ord-777",
            "portfolio_id": "port-A",
            "security_id": "CUSIP123",
            "trade_type": "buy",
            "quantity": 100,
            "price": 50.0,
            "allocation_target": "port-A",
            "compliance_status": "passed",
        }

        async def mock_paginate(*args, **kwargs):
            yield [trade_record]

        mock_item = MagicMock()
        mock_module = MagicMock()
        mock_module.EvidenceItem.return_value = mock_item
        mock_module.EvidenceCategory = MagicMock()

        with (
            patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate),
            patch.dict("sys.modules", {"src.core.models": mock_module}),
        ):
            await connector.sync_data("eng-001", domain="orders", db_session=mock_session)

        assert mock_session.add.called
        assert mock_session.flush.called

    async def test_record_id_falls_back_to_uuid_when_no_order_id(self) -> None:
        """Records without order_id fall back to UUID-based naming."""
        connector = CharlesRiverConnector(_config())
        mock_session = AsyncMock()

        record_without_id = {"portfolio_id": "p1", "security_id": "SEC1"}

        async def mock_paginate(*args, **kwargs):
            yield [record_without_id]

        mock_module = MagicMock()
        mock_module.EvidenceItem.return_value = MagicMock()
        mock_module.EvidenceCategory = MagicMock()

        with (
            patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate),
            patch.dict("sys.modules", {"src.core.models": mock_module}),
        ):
            await connector.sync_data("eng-001", domain="portfolios", db_session=mock_session)

        assert mock_session.add.called


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverGetSchema:
    """get_schema() returns expected field names."""

    async def test_trade_order_fields_present(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert "order_id" in schema
        assert "portfolio_id" in schema
        assert "security_id" in schema
        assert "trade_type" in schema
        assert "quantity" in schema
        assert "price" in schema

    async def test_compliance_fields_present(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert "compliance_status" in schema
        assert "allocation_target" in schema

    async def test_portfolio_analytics_fields_present(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert "portfolio_name" in schema
        assert "performance_ytd" in schema
        assert "benchmark_id" in schema

    async def test_allocation_fields_present(self) -> None:
        connector = CharlesRiverConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert "allocation_id" in schema
        assert "allocated_quantity" in schema
        assert "confirm_date" in schema


# ---------------------------------------------------------------------------
# sync_incremental
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCharlesRiverSyncIncremental:
    """sync_incremental() delegates correctly."""

    async def test_without_since_falls_back_to_full_sync(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"order_id": "o1"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001", domain="orders")

        assert result["records_synced"] == 1

    async def test_with_since_result_structure_intact(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield []

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001", since="2026-01-01T00:00:00Z", domain="orders")

        assert "records_synced" in result
        assert "errors" in result
        assert "metadata" in result
        assert result["metadata"]["source"] == "charles_river"

    async def test_result_has_no_unexpected_errors(self) -> None:
        connector = CharlesRiverConnector(_config())

        async def mock_paginate(*args, **kwargs):
            yield [{"order_id": "x", "portfolio_id": "y"}]

        with patch("src.integrations.charles_river.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001", domain="orders")

        assert result["errors"] == []
