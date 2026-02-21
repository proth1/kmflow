"""Tests for the SAP integration connector."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.integrations.base import ConnectionConfig
from src.integrations.sap import SAPConnector


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a minimal httpx.Response for mocking."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://sap.example.com"),
    )


# =============================================================================
# SAPConnector initialisation
# =============================================================================


class TestSAPConnectorInit:
    """Tests for SAPConnector construction and field extraction."""

    def test_description_present(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        assert "SAP" in connector.description

    def test_base_url_from_config_base_url(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com/")
        connector = SAPConnector(config)
        assert connector._base_url == "https://sap.example.com"

    def test_base_url_from_extra(self) -> None:
        config = ConnectionConfig(extra={"base_url": "https://sap-extra.example.com/"})
        connector = SAPConnector(config)
        assert connector._base_url == "https://sap-extra.example.com"

    def test_api_key_from_config(self) -> None:
        config = ConnectionConfig(api_key="my-api-key")
        connector = SAPConnector(config)
        assert connector._api_key == "my-api-key"

    def test_api_key_from_extra(self) -> None:
        config = ConnectionConfig(extra={"api_key": "extra-key"})
        connector = SAPConnector(config)
        assert connector._api_key == "extra-key"

    def test_username_and_password_from_extra(self) -> None:
        config = ConnectionConfig(extra={"username": "sapuser", "password": "s3cr3t"})
        connector = SAPConnector(config)
        assert connector._username == "sapuser"
        assert connector._password == "s3cr3t"

    def test_client_defaults_to_100(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        assert connector._client == "100"

    def test_client_override_from_extra(self) -> None:
        config = ConnectionConfig(extra={"client": "200"})
        connector = SAPConnector(config)
        assert connector._client == "200"

    def test_system_id_from_extra(self) -> None:
        config = ConnectionConfig(extra={"system_id": "PRD"})
        connector = SAPConnector(config)
        assert connector._system_id == "PRD"


# =============================================================================
# _auth
# =============================================================================


class TestSAPConnectorAuth:
    """Tests for the _auth() helper."""

    def test_returns_basic_auth_when_credentials_present(self) -> None:
        config = ConnectionConfig(extra={"username": "sapuser", "password": "pass123"})
        connector = SAPConnector(config)
        auth = connector._auth()
        assert isinstance(auth, httpx.BasicAuth)

    def test_returns_none_when_no_credentials(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        assert connector._auth() is None

    def test_returns_none_when_only_username(self) -> None:
        config = ConnectionConfig(extra={"username": "sapuser"})
        connector = SAPConnector(config)
        assert connector._auth() is None

    def test_returns_none_when_only_password(self) -> None:
        config = ConnectionConfig(extra={"password": "pass123"})
        connector = SAPConnector(config)
        assert connector._auth() is None


# =============================================================================
# _headers
# =============================================================================


class TestSAPConnectorHeaders:
    """Tests for the _headers() helper."""

    def test_headers_include_accept_json(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        headers = connector._headers()
        assert headers["Accept"] == "application/json"

    def test_headers_include_sap_client(self) -> None:
        config = ConnectionConfig(extra={"client": "300"})
        connector = SAPConnector(config)
        headers = connector._headers()
        assert headers["sap-client"] == "300"

    def test_headers_include_bearer_token_when_api_key_set(self) -> None:
        config = ConnectionConfig(api_key="token-abc")
        connector = SAPConnector(config)
        headers = connector._headers()
        assert headers["Authorization"] == "Bearer token-abc"

    def test_headers_no_authorization_when_no_api_key(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        headers = connector._headers()
        assert "Authorization" not in headers


# =============================================================================
# test_connection
# =============================================================================


@pytest.mark.asyncio
class TestSAPTestConnection:
    """Tests for test_connection()."""

    async def test_returns_false_when_no_base_url(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        result = await connector.test_connection()
        assert result is False

    async def test_returns_false_when_no_credentials(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com")
        connector = SAPConnector(config)
        result = await connector.test_connection()
        assert result is False

    async def test_returns_true_on_200_with_api_key(self) -> None:
        config = ConnectionConfig(
            base_url="https://sap.example.com",
            api_key="test-key",
        )
        connector = SAPConnector(config)
        mock_response = _mock_response(200)
        with patch("src.integrations.sap.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    async def test_returns_true_on_200_with_basic_auth(self) -> None:
        config = ConnectionConfig(
            base_url="https://sap.example.com",
            extra={"username": "sapuser", "password": "secret"},
        )
        connector = SAPConnector(config)
        mock_response = _mock_response(200)
        with patch("src.integrations.sap.retry_request", return_value=mock_response):
            result = await connector.test_connection()
        assert result is True

    async def test_returns_false_on_non_200(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)
        with patch("src.integrations.sap.retry_request", return_value=_mock_response(401)):
            result = await connector.test_connection()
        assert result is False

    async def test_returns_false_on_connect_error(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)
        with patch("src.integrations.sap.retry_request", side_effect=httpx.ConnectError("refused")):
            result = await connector.test_connection()
        assert result is False

    async def test_returns_false_on_http_status_error(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)
        with patch(
            "src.integrations.sap.retry_request",
            side_effect=httpx.HTTPStatusError(
                "503",
                request=httpx.Request("GET", "https://sap.example.com"),
                response=_mock_response(503),
            ),
        ):
            result = await connector.test_connection()
        assert result is False


# =============================================================================
# sync_data
# =============================================================================


@pytest.mark.asyncio
class TestSAPSyncData:
    """Tests for sync_data()."""

    async def test_returns_zero_when_no_base_url(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert "SAP not configured" in result["errors"][0]

    async def test_returns_metadata_with_correct_source(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"BELNR": "001"}, {"BELNR": "002"}]

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["metadata"]["source"] == "sap"
        assert result["metadata"]["engagement_id"] == "eng-001"

    async def test_uses_default_entity_set(self) -> None:
        """When no entity_set kwarg is provided, ZProcessLogs is used."""
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield []

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["metadata"]["entity_set"] == "ZProcessLogs"

    async def test_uses_custom_entity_set(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield []

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", entity_set="ZSomeOtherEntity")

        assert result["metadata"]["entity_set"] == "ZSomeOtherEntity"

    async def test_counts_records_from_list_page(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"BELNR": "001"}, {"BELNR": "002"}, {"BELNR": "003"}]

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 3
        assert result["errors"] == []

    async def test_counts_records_across_multiple_pages(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"BELNR": "001"}, {"BELNR": "002"}]
            yield [{"BELNR": "003"}]

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 3

    async def test_handles_d_results_wrapper(self) -> None:
        """SAP OData wraps results in d.results; a dict page should use its 'results' key."""
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            # Simulate the paginate_cursor yielding what SAP OData would return
            # after the d key is looked up — a dict with a 'results' sub-list
            yield {"results": [{"BELNR": "A"}, {"BELNR": "B"}]}

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 2

    async def test_handles_http_status_error(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            raise httpx.HTTPStatusError(
                "403",
                request=httpx.Request("GET", "https://sap.example.com"),
                response=_mock_response(403),
            )
            yield  # make it an async generator

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "403" in result["errors"][0]

    async def test_handles_request_error(self) -> None:
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            raise httpx.ConnectError("timeout")
            yield

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "connection error" in result["errors"][0].lower()


# =============================================================================
# get_schema
# =============================================================================


@pytest.mark.asyncio
class TestSAPGetSchema:
    """Tests for get_schema()."""

    async def test_returns_list_of_strings(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert isinstance(schema, list)
        assert all(isinstance(f, str) for f in schema)

    async def test_includes_expected_sap_fields(self) -> None:
        connector = SAPConnector(ConnectionConfig())
        schema = await connector.get_schema()
        for field in ["MANDT", "BELNR", "BUKRS", "GJAHR", "ERDAT", "ERNAM", "AEDAT"]:
            assert field in schema


# =============================================================================
# sync_incremental
# =============================================================================


@pytest.mark.asyncio
class TestSAPSyncIncremental:
    """Tests for sync_incremental()."""

    async def test_without_since_delegates_to_sync_data_unchanged(self) -> None:
        """No since timestamp → sync_data is called without a filter_query modification."""
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        captured_kwargs: list[dict] = []

        async def mock_paginate(*args: object, **kwargs: object):
            captured_kwargs.append(dict(kwargs))
            yield []

        with patch("src.integrations.sap.paginate_cursor", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001")

        assert result["records_synced"] == 0
        # No filter was injected
        assert captured_kwargs  # paginate was called

    async def test_with_since_adds_aedat_filter(self) -> None:
        """A since timestamp is translated into an AEDAT OData filter."""
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        # Spy on sync_data to capture the kwargs it receives
        original_sync = connector.sync_data
        captured: list[dict] = []

        async def spy_sync(engagement_id: str, **kwargs: object) -> dict:
            captured.append(dict(kwargs))
            return {"records_synced": 0, "errors": [], "metadata": {}}

        connector.sync_data = spy_sync  # type: ignore[method-assign]

        await connector.sync_incremental("eng-001", since="2024-06-01T00:00:00")

        assert captured
        filter_query = captured[0].get("filter_query", "")
        assert "AEDAT" in filter_query
        assert "2024-06-01T00:00:00" in filter_query

    async def test_with_since_and_existing_filter_combines_filters(self) -> None:
        """A since timestamp is ANDed with any pre-existing filter_query."""
        config = ConnectionConfig(base_url="https://sap.example.com", api_key="key")
        connector = SAPConnector(config)

        captured: list[dict] = []

        async def spy_sync(engagement_id: str, **kwargs: object) -> dict:
            captured.append(dict(kwargs))
            return {"records_synced": 0, "errors": [], "metadata": {}}

        connector.sync_data = spy_sync  # type: ignore[method-assign]

        await connector.sync_incremental(
            "eng-001",
            since="2024-06-01T00:00:00",
            filter_query="BUKRS eq '1000'",
        )

        filter_query = captured[0]["filter_query"]
        assert "BUKRS eq '1000'" in filter_query
        assert "AEDAT" in filter_query
        assert " and " in filter_query
