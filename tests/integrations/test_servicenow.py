"""Tests for the ServiceNow integration connector."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.integrations.base import ConnectionConfig
from src.integrations.servicenow import ServiceNowConnector


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a minimal httpx.Response for mocking."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.service-now.com"),
    )


# =============================================================================
# ServiceNowConnector initialisation
# =============================================================================


class TestServiceNowConnectorInit:
    """Tests for ServiceNowConnector construction and field extraction."""

    def test_description_present(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        assert "ServiceNow" in connector.description

    def test_base_url_from_config_base_url(self) -> None:
        config = ConnectionConfig(base_url="https://myinstance.service-now.com/")
        connector = ServiceNowConnector(config)
        assert connector._base_url == "https://myinstance.service-now.com"

    def test_base_url_from_extra_instance_url(self) -> None:
        config = ConnectionConfig(extra={"instance_url": "https://extra.service-now.com/"})
        connector = ServiceNowConnector(config)
        assert connector._base_url == "https://extra.service-now.com"

    def test_api_key_from_config(self) -> None:
        config = ConnectionConfig(api_key="sn-api-key")
        connector = ServiceNowConnector(config)
        assert connector._api_key == "sn-api-key"

    def test_api_key_from_extra(self) -> None:
        config = ConnectionConfig(extra={"api_key": "sn-extra-key"})
        connector = ServiceNowConnector(config)
        assert connector._api_key == "sn-extra-key"

    def test_username_and_password_from_extra(self) -> None:
        config = ConnectionConfig(extra={"username": "snuser", "password": "snpass"})
        connector = ServiceNowConnector(config)
        assert connector._username == "snuser"
        assert connector._password == "snpass"

    def test_empty_config_defaults(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        assert connector._base_url == ""
        assert connector._api_key == ""
        assert connector._username == ""
        assert connector._password == ""


# =============================================================================
# _auth
# =============================================================================


class TestServiceNowAuth:
    """Tests for _auth()."""

    def test_returns_basic_auth_when_credentials_present(self) -> None:
        config = ConnectionConfig(extra={"username": "snuser", "password": "snpass"})
        connector = ServiceNowConnector(config)
        auth = connector._auth()
        assert isinstance(auth, httpx.BasicAuth)

    def test_returns_none_when_no_credentials(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        assert connector._auth() is None

    def test_returns_none_when_only_username(self) -> None:
        config = ConnectionConfig(extra={"username": "snuser"})
        connector = ServiceNowConnector(config)
        assert connector._auth() is None

    def test_returns_none_when_only_password(self) -> None:
        config = ConnectionConfig(extra={"password": "snpass"})
        connector = ServiceNowConnector(config)
        assert connector._auth() is None


# =============================================================================
# _headers
# =============================================================================


class TestServiceNowHeaders:
    """Tests for _headers()."""

    def test_headers_include_accept_json(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        headers = connector._headers()
        assert headers["Accept"] == "application/json"

    def test_headers_include_content_type_json(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        headers = connector._headers()
        assert headers["Content-Type"] == "application/json"

    def test_headers_include_bearer_when_api_key_set(self) -> None:
        config = ConnectionConfig(api_key="sn-token")
        connector = ServiceNowConnector(config)
        headers = connector._headers()
        assert headers["Authorization"] == "Bearer sn-token"

    def test_headers_no_authorization_when_no_api_key(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        headers = connector._headers()
        assert "Authorization" not in headers


# =============================================================================
# test_connection
# =============================================================================


@pytest.mark.asyncio
class TestServiceNowTestConnection:
    """Tests for test_connection()."""

    async def test_returns_false_when_no_base_url(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        result = await connector.test_connection()
        assert result is False

    async def test_returns_false_when_no_credentials(self) -> None:
        config = ConnectionConfig(base_url="https://myinstance.service-now.com")
        connector = ServiceNowConnector(config)
        result = await connector.test_connection()
        assert result is False

    async def test_returns_true_on_200_with_api_key(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        with patch("src.integrations.servicenow.retry_request", return_value=_mock_response(200)):
            result = await connector.test_connection()
        assert result is True

    async def test_returns_true_on_200_with_basic_auth(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            extra={"username": "snuser", "password": "snpass"},
        )
        connector = ServiceNowConnector(config)
        with patch("src.integrations.servicenow.retry_request", return_value=_mock_response(200)):
            result = await connector.test_connection()
        assert result is True

    async def test_returns_false_on_non_200(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        with patch("src.integrations.servicenow.retry_request", return_value=_mock_response(403)):
            result = await connector.test_connection()
        assert result is False

    async def test_returns_false_on_connect_error(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        with patch("src.integrations.servicenow.retry_request", side_effect=httpx.ConnectError("refused")):
            result = await connector.test_connection()
        assert result is False

    async def test_returns_false_on_http_status_error(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        with patch(
            "src.integrations.servicenow.retry_request",
            side_effect=httpx.HTTPStatusError(
                "503",
                request=httpx.Request("GET", "https://myinstance.service-now.com"),
                response=_mock_response(503),
            ),
        ):
            result = await connector.test_connection()
        assert result is False

    async def test_test_connection_hits_sys_properties_endpoint(self) -> None:
        """The connectivity check queries the sys_properties table."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        captured_url: list[str] = []

        async def capture(*args: object, **kwargs: object) -> httpx.Response:
            # retry_request(client, method, url, ...)
            captured_url.append(args[2])
            return _mock_response(200)

        with patch("src.integrations.servicenow.retry_request", side_effect=capture):
            await connector.test_connection()

        assert any("sys_properties" in u for u in captured_url)


# =============================================================================
# sync_data
# =============================================================================


@pytest.mark.asyncio
class TestServiceNowSyncData:
    """Tests for sync_data()."""

    async def test_returns_zero_when_not_configured(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert "ServiceNow not configured" in result["errors"][0]

    async def test_returns_zero_when_base_url_present_but_no_creds(self) -> None:
        config = ConnectionConfig(base_url="https://myinstance.service-now.com")
        connector = ServiceNowConnector(config)
        result = await connector.sync_data("eng-001")
        assert result["records_synced"] == 0
        assert len(result["errors"]) > 0

    async def test_returns_metadata_with_correct_source(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"sys_id": "abc", "number": "INC001"}]

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["metadata"]["source"] == "servicenow"
        assert result["metadata"]["engagement_id"] == "eng-001"

    async def test_uses_default_table_incident(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["metadata"]["table_name"] == "incident"

    async def test_uses_custom_table_name(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001", table_name="change_request")

        assert result["metadata"]["table_name"] == "change_request"

    async def test_counts_records_from_single_page(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"sys_id": "1"}, {"sys_id": "2"}, {"sys_id": "3"}]

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 3
        assert result["errors"] == []

    async def test_counts_records_across_multiple_pages(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield [{"sys_id": "1"}, {"sys_id": "2"}]
            yield [{"sys_id": "3"}, {"sys_id": "4"}]

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 4

    async def test_applies_query_filter_param(self) -> None:
        """A query_filter kwarg should be passed as sysparm_query."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        captured_params: list[dict] = []

        async def mock_paginate(client: object, url: str, *, params: dict, **kwargs: object):
            captured_params.append(dict(params))
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            await connector.sync_data("eng-001", query_filter="priority=1")

        assert captured_params[0].get("sysparm_query") == "priority=1"

    async def test_applies_fields_as_string(self) -> None:
        """A fields kwarg (string) becomes sysparm_fields."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        captured_params: list[dict] = []

        async def mock_paginate(client: object, url: str, *, params: dict, **kwargs: object):
            captured_params.append(dict(params))
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            await connector.sync_data("eng-001", fields="sys_id,number,state")

        assert captured_params[0].get("sysparm_fields") == "sys_id,number,state"

    async def test_applies_fields_as_list(self) -> None:
        """A fields kwarg (list) is joined to sysparm_fields."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)
        captured_params: list[dict] = []

        async def mock_paginate(client: object, url: str, *, params: dict, **kwargs: object):
            captured_params.append(dict(params))
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            await connector.sync_data("eng-001", fields=["sys_id", "number", "state"])

        assert captured_params[0].get("sysparm_fields") == "sys_id,number,state"

    async def test_handles_http_status_error(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            raise httpx.HTTPStatusError(
                "401",
                request=httpx.Request("GET", "https://myinstance.service-now.com"),
                response=_mock_response(401),
            )
            yield

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "401" in result["errors"][0]

    async def test_handles_request_error(self) -> None:
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            raise httpx.ConnectError("timeout")
            yield

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_data("eng-001")

        assert result["records_synced"] == 0
        assert len(result["errors"]) == 1
        assert "connection error" in result["errors"][0].lower()


# =============================================================================
# get_schema
# =============================================================================


@pytest.mark.asyncio
class TestServiceNowGetSchema:
    """Tests for get_schema()."""

    async def test_returns_list_of_strings(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        schema = await connector.get_schema()
        assert isinstance(schema, list)
        assert all(isinstance(f, str) for f in schema)

    async def test_includes_expected_servicenow_fields(self) -> None:
        connector = ServiceNowConnector(ConnectionConfig())
        schema = await connector.get_schema()
        for field in [
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
        ]:
            assert field in schema


# =============================================================================
# sync_incremental
# =============================================================================


@pytest.mark.asyncio
class TestServiceNowSyncIncremental:
    """Tests for sync_incremental()."""

    async def test_without_since_delegates_to_sync_data_unchanged(self) -> None:
        """No since timestamp → sync_data is called without injecting a filter."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        async def mock_paginate(*args: object, **kwargs: object):
            yield []

        with patch("src.integrations.servicenow.paginate_offset", side_effect=mock_paginate):
            result = await connector.sync_incremental("eng-001")

        assert result["records_synced"] == 0

    async def test_with_since_adds_sys_updated_on_filter(self) -> None:
        """A since timestamp is added as a sys_updated_on filter."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        captured: list[dict] = []

        async def spy_sync(engagement_id: str, **kwargs: object) -> dict:
            captured.append(dict(kwargs))
            return {"records_synced": 0, "errors": [], "metadata": {}}

        connector.sync_data = spy_sync  # type: ignore[method-assign]

        await connector.sync_incremental("eng-001", since="2024-06-01T00:00:00Z")

        assert captured
        query_filter = captured[0].get("query_filter", "")
        assert "sys_updated_on" in query_filter
        assert "2024-06-01T00:00:00Z" in query_filter

    async def test_with_since_and_existing_query_filter_combines_with_caret(self) -> None:
        """The since filter is combined with existing filter using ServiceNow's ^ delimiter."""
        config = ConnectionConfig(
            base_url="https://myinstance.service-now.com",
            api_key="sn-key",
        )
        connector = ServiceNowConnector(config)

        captured: list[dict] = []

        async def spy_sync(engagement_id: str, **kwargs: object) -> dict:
            captured.append(dict(kwargs))
            return {"records_synced": 0, "errors": [], "metadata": {}}

        connector.sync_data = spy_sync  # type: ignore[method-assign]

        await connector.sync_incremental(
            "eng-001",
            since="2024-06-01T00:00:00Z",
            query_filter="category=network",
        )

        query_filter = captured[0]["query_filter"]
        assert "category=network" in query_filter
        assert "sys_updated_on" in query_filter
        assert "^" in query_filter
