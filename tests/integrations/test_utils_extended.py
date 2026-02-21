"""Extended tests for integration utility functions.

These tests cover paths not exercised in test_utils.py:
- paginate_offset with total_key=None
- paginate_offset with custom offset/limit param names
- paginate_offset max_pages safety limit
- paginate_cursor with custom results_key and next_url_key
- paginate_cursor max_pages safety limit
- retry_request exhausting retries on status codes (last attempt raises)
- retry_request passes through extra kwargs to client.request
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.integrations.utils import DEFAULT_RETRY_DELAYS, DEFAULT_TIMEOUT, paginate_cursor, paginate_offset, retry_request


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create a minimal httpx.Response for mocking."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://api.example.com"),
    )


# =============================================================================
# Module-level constant checks
# =============================================================================


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_default_retry_delays_is_tuple(self) -> None:
        assert isinstance(DEFAULT_RETRY_DELAYS, tuple)
        assert len(DEFAULT_RETRY_DELAYS) == 3

    def test_default_timeout_is_float(self) -> None:
        assert isinstance(DEFAULT_TIMEOUT, float)
        assert DEFAULT_TIMEOUT > 0


# =============================================================================
# retry_request — additional edge cases
# =============================================================================


@pytest.mark.asyncio
class TestRetryRequestEdgeCases:
    """Additional edge cases for retry_request not covered in test_utils.py."""

    async def test_passes_extra_kwargs_to_client_request(self) -> None:
        """Extra kwargs (headers, params, json) are forwarded to client.request."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = _make_response(200, {"ok": True})

        await retry_request(
            mock_client,
            "POST",
            "https://api.example.com/items",
            headers={"Authorization": "Bearer tok"},
            json={"key": "value"},
            params={"q": "test"},
        )

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer tok"
        assert call_kwargs["json"] == {"key": "value"}
        assert call_kwargs["params"] == {"q": "test"}

    async def test_exhausts_all_status_retries_then_raises_on_final_4xx(self) -> None:
        """When the server returns a 5xx on every attempt, the last raise_for_status fires."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        # All attempts return 503 (in retry_on_status), but on the final attempt
        # raise_for_status fires because attempt == max_retries
        mock_client.request.return_value = _make_response(503)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_request(
                mock_client,
                "GET",
                "https://api.example.com/test",
                max_retries=2,
                retry_delays=(0.01, 0.01),
            )

        assert mock_client.request.call_count == 3  # initial + 2 retries

    async def test_does_not_retry_on_status_not_in_retry_set(self) -> None:
        """Status codes not in retry_on_status raise immediately without retry."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = _make_response(400)

        with pytest.raises(httpx.HTTPStatusError):
            await retry_request(
                mock_client,
                "GET",
                "https://api.example.com/test",
                retry_on_status=(429, 500, 502, 503, 504),
            )

        mock_client.request.assert_called_once()

    async def test_zero_max_retries_makes_single_attempt(self) -> None:
        """max_retries=0 means exactly one attempt — no retries."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = httpx.ConnectError("fail")

        with pytest.raises(httpx.ConnectError):
            await retry_request(
                mock_client,
                "GET",
                "https://api.example.com/test",
                max_retries=0,
                retry_delays=(0.01,),
            )

        mock_client.request.assert_called_once()

    async def test_retry_succeeds_on_last_attempt(self) -> None:
        """When the request fails on all-but-last attempts, the final success is returned."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = [
            httpx.ConnectError("fail"),
            httpx.ConnectError("fail"),
            _make_response(200, {"ok": True}),
        ]

        result = await retry_request(
            mock_client,
            "GET",
            "https://api.example.com/test",
            max_retries=2,
            retry_delays=(0.01, 0.01),
        )

        assert result.status_code == 200
        assert mock_client.request.call_count == 3


# =============================================================================
# paginate_offset — additional edge cases
# =============================================================================


@pytest.mark.asyncio
class TestPaginateOffsetEdgeCases:
    """Extended tests for paginate_offset."""

    async def test_no_total_key_paginates_until_empty(self) -> None:
        """When total_key is None, pagination stops when a page returns fewer than page_size records."""
        call_count = 0

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            offset = params.get("offset", 0)
            if offset == 0:
                return _make_response(200, {"results": [{"id": 1}, {"id": 2}]})
            return _make_response(200, {"results": []})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            page_size=2,
            total_key=None,
        ):
            pages.append(page)

        # First page has 2 records (== page_size), second page is empty → stop
        assert len(pages) == 1
        assert len(pages[0]) == 2

    async def test_custom_offset_and_limit_param_names(self) -> None:
        """Custom offset_param and limit_param names are used in the query."""
        captured_params: list[dict] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            params = dict(kwargs.get("params", {}))
            captured_params.append(params)
            return _make_response(200, {"items": [{"id": 1}], "total": 1})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        async for _ in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            results_key="items",
            total_key="total",
            offset_param="sysparm_offset",
            limit_param="sysparm_limit",
            page_size=50,
        ):
            pass

        assert "sysparm_offset" in captured_params[0]
        assert "sysparm_limit" in captured_params[0]
        assert captured_params[0]["sysparm_limit"] == 50

    async def test_max_pages_safety_limit_stops_iteration(self) -> None:
        """When max_pages is reached, pagination stops even if there are more records."""
        call_count = 0

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            offset = params.get("offset", 0)
            return _make_response(
                200,
                {"results": [{"id": offset + 1}, {"id": offset + 2}], "total": 1000},
            )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            page_size=2,
            max_pages=3,
        ):
            pages.append(page)

        assert len(pages) == 3
        assert call_count == 3

    async def test_passes_extra_params_in_all_requests(self) -> None:
        """Additional params passed to paginate_offset appear in every page request."""
        captured_params: list[dict] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            params = dict(kwargs.get("params", {}))
            captured_params.append(params)
            return _make_response(200, {"results": [{"id": 1}], "total": 1})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        async for _ in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            params={"$format": "json", "$filter": "active eq true"},
        ):
            pass

        assert captured_params[0]["$format"] == "json"
        assert captured_params[0]["$filter"] == "active eq true"

    async def test_passes_headers_to_requests(self) -> None:
        """Headers passed to paginate_offset are forwarded to every page request."""
        captured_headers: list[dict | None] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            captured_headers.append(kwargs.get("headers"))
            return _make_response(200, {"results": [{"id": 1}], "total": 1})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        async for _ in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            headers={"Authorization": "Bearer token", "Accept": "application/json"},
        ):
            pass

        assert captured_headers[0] is not None
        assert captured_headers[0]["Authorization"] == "Bearer token"

    async def test_stops_when_results_smaller_than_page_size(self) -> None:
        """When a page returns fewer records than page_size, iteration ends after that page."""
        call_count = 0

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(200, {"results": [{"id": 1}]})  # 1 record, page_size=10

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(
            mock_client,
            "https://api.example.com/data",
            page_size=10,
            total_key=None,
        ):
            pages.append(page)

        assert call_count == 1
        assert len(pages) == 1


# =============================================================================
# paginate_cursor — additional edge cases
# =============================================================================


@pytest.mark.asyncio
class TestPaginateCursorEdgeCases:
    """Extended tests for paginate_cursor."""

    async def test_custom_results_key(self) -> None:
        """A non-default results_key is used to extract the page data."""
        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            return _make_response(200, {"items": [{"id": 1}, {"id": 2}]})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            results_key="items",
        ):
            pages.append(page)

        assert len(pages) == 1
        assert len(pages[0]) == 2

    async def test_custom_next_url_key(self) -> None:
        """A non-default next_url_key is followed for subsequent pages."""
        call_urls: list[str] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            call_urls.append(url)
            if url == "https://api.example.com/data":
                return _make_response(
                    200,
                    {"results": [{"id": 1}], "__next": "https://api.example.com/data?page=2"},
                )
            return _make_response(200, {"results": [{"id": 2}]})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            next_url_key="__next",
        ):
            pages.append(page)

        assert len(pages) == 2
        assert len(call_urls) == 2

    async def test_max_pages_safety_limit_stops_cursor_pagination(self) -> None:
        """When max_pages is reached, cursor pagination stops even if next URL exists."""
        call_count = 0

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(
                200,
                {
                    "results": [{"id": call_count}],
                    "next": f"https://api.example.com/data?page={call_count + 1}",
                },
            )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            max_pages=4,
        ):
            pages.append(page)

        assert len(pages) == 4
        assert call_count == 4

    async def test_params_only_sent_on_first_request(self) -> None:
        """Initial params are sent on the first request but NOT on subsequent pages."""
        captured_params: list[dict | None] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            captured_params.append(kwargs.get("params"))
            if "page=2" not in url:
                return _make_response(
                    200,
                    {"results": [{"id": 1}], "next": "https://api.example.com/data?page=2"},
                )
            return _make_response(200, {"results": [{"id": 2}]})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        async for _ in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            params={"$filter": "active eq true"},
        ):
            pass

        assert len(captured_params) == 2
        # First request gets the params
        assert captured_params[0] == {"$filter": "active eq true"}
        # Subsequent requests get None (cursor URL carries its own query string)
        assert captured_params[1] is None

    async def test_headers_forwarded_to_all_pages(self) -> None:
        """Headers are forwarded on every page request, including cursor-based ones."""
        captured_headers: list[dict | None] = []

        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            captured_headers.append(kwargs.get("headers"))
            if "page=2" not in url:
                return _make_response(
                    200,
                    {"results": [{"id": 1}], "next": "https://api.example.com/data?page=2"},
                )
            return _make_response(200, {"results": [{"id": 2}]})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        async for _ in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            headers={"Authorization": "Bearer sn-key"},
        ):
            pass

        for h in captured_headers:
            assert h is not None
            assert h["Authorization"] == "Bearer sn-key"

    async def test_empty_first_page_yields_nothing(self) -> None:
        """If the very first page has no results, the generator yields nothing."""
        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            return _make_response(200, {"results": [], "next": "https://api.example.com/data?page=2"})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(mock_client, "https://api.example.com/data"):
            pages.append(page)

        assert pages == []

    async def test_missing_results_key_yields_nothing(self) -> None:
        """If the response body doesn't contain the expected results key, iteration stops."""
        async def mock_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            # Response uses "data" instead of "results"
            return _make_response(200, {"data": [{"id": 1}], "next": "..."})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(
            mock_client,
            "https://api.example.com/data",
            results_key="results",  # expecting "results" but response has "data"
        ):
            pages.append(page)

        assert pages == []
