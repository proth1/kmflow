"""Tests for integration connector utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.integrations.utils import paginate_cursor, paginate_offset, retry_request


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.com"),
    )


class TestRetryRequest:
    """Tests for retry_request utility."""

    @pytest.mark.asyncio
    async def test_successful_request(self) -> None:
        """Should return response on success."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = _make_response(200, {"ok": True})

        result = await retry_request(mock_client, "GET", "https://api.example.com/test")
        assert result.status_code == 200
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self) -> None:
        """Should retry on 500 status codes."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = [
            _make_response(500),
            _make_response(200, {"ok": True}),
        ]

        result = await retry_request(
            mock_client,
            "GET",
            "https://api.example.com/test",
            retry_delays=(0.01, 0.02, 0.04),
        )
        assert result.status_code == 200
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self) -> None:
        """Should retry on connection errors."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = [
            httpx.ConnectError("fail"),
            _make_response(200, {"ok": True}),
        ]

        result = await retry_request(
            mock_client,
            "GET",
            "https://api.example.com/test",
            retry_delays=(0.01,),
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self) -> None:
        """Should raise after max retries."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = httpx.ConnectError("fail")

        with pytest.raises(httpx.ConnectError):
            await retry_request(
                mock_client,
                "GET",
                "https://api.example.com/test",
                max_retries=2,
                retry_delays=(0.01, 0.01),
            )
        assert mock_client.request.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self) -> None:
        """Should not retry 4xx errors."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = _make_response(404, {"detail": "Not found"})

        with pytest.raises(httpx.HTTPStatusError):
            await retry_request(mock_client, "GET", "https://api.example.com/test")
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_429(self) -> None:
        """Should retry on rate limit (429)."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.side_effect = [
            _make_response(429),
            _make_response(200, {"ok": True}),
        ]

        result = await retry_request(
            mock_client,
            "GET",
            "https://api.example.com/test",
            retry_delays=(0.01,),
        )
        assert result.status_code == 200


class TestPaginateOffset:
    """Tests for offset-based pagination."""

    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        """Should yield a single page when results < page_size."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def mock_request(method, url, **kwargs):
            return _make_response(
                200,
                {
                    "results": [{"id": 1}, {"id": 2}],
                    "total": 2,
                },
            )

        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(mock_client, "https://api.example.com/data", page_size=10):
            pages.append(page)

        assert len(pages) == 1
        assert len(pages[0]) == 2

    @pytest.mark.asyncio
    async def test_multiple_pages(self) -> None:
        """Should yield multiple pages based on total."""
        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            params = kwargs.get("params", {})
            offset = params.get("offset", 0)
            if offset == 0:
                call_count += 1
                return _make_response(
                    200,
                    {
                        "results": [{"id": 1}, {"id": 2}],
                        "total": 3,
                    },
                )
            else:
                call_count += 1
                return _make_response(
                    200,
                    {
                        "results": [{"id": 3}],
                        "total": 3,
                    },
                )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(mock_client, "https://api.example.com/data", page_size=2):
            pages.append(page)

        assert len(pages) == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        """Should stop on empty results."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def mock_request(method, url, **kwargs):
            return _make_response(200, {"results": []})

        mock_client.request = mock_request

        pages = []
        async for page in paginate_offset(mock_client, "https://api.example.com/data"):
            pages.append(page)

        assert len(pages) == 0


class TestPaginateCursor:
    """Tests for cursor-based pagination."""

    @pytest.mark.asyncio
    async def test_single_page_no_next(self) -> None:
        """Should yield one page when no next URL."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def mock_request(method, url, **kwargs):
            return _make_response(
                200,
                {
                    "results": [{"id": 1}],
                },
            )

        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(mock_client, "https://api.example.com/data"):
            pages.append(page)

        assert len(pages) == 1

    @pytest.mark.asyncio
    async def test_follows_next_url(self) -> None:
        """Should follow next URL for pagination."""
        call_urls: list[str] = []

        async def mock_request(method, url, **kwargs):
            call_urls.append(url)
            if "page2" not in url:
                return _make_response(
                    200,
                    {
                        "results": [{"id": 1}],
                        "next": "https://api.example.com/data?page2",
                    },
                )
            else:
                return _make_response(
                    200,
                    {
                        "results": [{"id": 2}],
                    },
                )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = mock_request

        pages = []
        async for page in paginate_cursor(mock_client, "https://api.example.com/data"):
            pages.append(page)

        assert len(pages) == 2
        assert len(call_urls) == 2
