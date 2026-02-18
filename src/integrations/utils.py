"""Shared utilities for integration connectors.

Provides retry logic with exponential backoff and async pagination
helpers used by all connector implementations.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0)
DEFAULT_TIMEOUT = 30.0


async def retry_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504),
    **kwargs: Any,
) -> httpx.Response:
    """Make an HTTP request with exponential backoff retry.

    Args:
        client: The httpx AsyncClient to use.
        method: HTTP method (GET, POST, etc.).
        url: The URL to request.
        max_retries: Maximum number of retry attempts.
        retry_delays: Tuple of delay seconds for each retry (1s, 2s, 4s).
        retry_on_status: HTTP status codes that trigger a retry.
        **kwargs: Additional arguments passed to client.request().

    Returns:
        The HTTP response.

    Raises:
        httpx.HTTPStatusError: If the request fails after all retries.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)

            if response.status_code in retry_on_status and attempt < max_retries:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(
                    "Request to %s returned %d, retrying in %.1fs (attempt %d/%d)",
                    url, response.status_code, delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response

        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(
                    "Request to %s failed: %s, retrying in %.1fs (attempt %d/%d)",
                    url, exc, delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(delay)
            else:
                raise

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")


async def paginate_offset(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    page_size: int = 100,
    results_key: str = "results",
    total_key: str | None = "total",
    offset_param: str = "offset",
    limit_param: str = "limit",
    max_pages: int = 100,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Async generator for offset-based pagination.

    Args:
        client: The httpx AsyncClient.
        url: Base URL to paginate.
        params: Additional query parameters.
        headers: Additional headers.
        page_size: Number of records per page.
        results_key: JSON key containing the results array.
        total_key: JSON key containing total count (None to paginate until empty).
        offset_param: Query parameter name for offset.
        limit_param: Query parameter name for limit.
        max_pages: Safety limit on number of pages.

    Yields:
        Lists of records from each page.
    """
    offset = 0
    request_params = dict(params or {})

    for _ in range(max_pages):
        request_params[offset_param] = offset
        request_params[limit_param] = page_size

        response = await retry_request(
            client, "GET", url,
            params=request_params,
            headers=headers,
        )
        data = response.json()

        results = data.get(results_key, [])
        if not results:
            break

        yield results

        offset += len(results)

        if total_key and total_key in data:
            if offset >= data[total_key]:
                break

        if len(results) < page_size:
            break


async def paginate_cursor(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    results_key: str = "results",
    next_url_key: str = "next",
    max_pages: int = 100,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Async generator for cursor/URL-based pagination.

    Args:
        client: The httpx AsyncClient.
        url: Initial URL to fetch.
        params: Query parameters for the first request.
        headers: Additional headers.
        results_key: JSON key containing the results array.
        next_url_key: JSON key containing the next page URL.
        max_pages: Safety limit on number of pages.

    Yields:
        Lists of records from each page.
    """
    current_url: str | None = url
    is_first = True

    for _ in range(max_pages):
        if current_url is None:
            break

        response = await retry_request(
            client, "GET", current_url,
            params=params if is_first else None,
            headers=headers,
        )
        is_first = False
        data = response.json()

        results = data.get(results_key, [])
        if not results:
            break

        yield results

        current_url = data.get(next_url_key)
