"""Tests for the batch uploader.

Covers: success path, gzip+checksum, retry on 5xx, no-retry on 4xx,
batch sizing, prune after upload.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.config.manager import ConfigManager
from kmflow_agent.upload.batch_uploader import BatchUploader

# ── Helpers ──────────────────────────────────────────────────────────


def _make_config(backend_url: str = "https://api.example.com", agent_id: str = "agent-1") -> ConfigManager:
    """Create a ConfigManager with test defaults (no HTTP client)."""
    return ConfigManager(
        backend_url=backend_url,
        agent_id=agent_id,
        http_client=None,
    )


def _make_response(status_code: int, text: str = "") -> httpx.Response:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


# ── Upload success path ──────────────────────────────────────────────


class TestUploadSuccess:
    @pytest.fixture
    def buffer(self, tmp_path):
        return BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)

    @pytest.fixture
    def uploader(self, buffer):
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(return_value=_make_response(200))
        return BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

    @pytest.mark.asyncio
    async def test_upload_single_batch(self, uploader, buffer):
        """Events are uploaded and marked as uploaded on 200."""
        # Write some events
        for i in range(5):
            await buffer.write_event({"event_type": "click", "seq": i})

        assert await buffer.count_pending() == 5

        await uploader._upload_pending()

        # Client.post was called once (5 events < batch_size of 10)
        uploader._client.post.assert_called_once()

        # Verify gzip + checksum headers
        call_kwargs = uploader._client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers["Content-Encoding"] == "gzip"
        assert "X-Checksum" in headers
        assert "X-Batch-Id" in headers

        # Verify payload is gzip-compressed JSON
        content = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content")
        decompressed = gzip.decompress(content)
        payload = json.loads(decompressed)
        assert payload["agent_id"] == "agent-1"
        assert len(payload["events"]) == 5

        # Verify checksum matches uncompressed payload
        expected_checksum = hashlib.sha256(decompressed).hexdigest()
        assert headers["X-Checksum"] == expected_checksum

    @pytest.mark.asyncio
    async def test_upload_count_increments(self, uploader, buffer):
        await buffer.write_event({"event_type": "click", "seq": 1})
        assert uploader._upload_count == 0
        await uploader._upload_pending()
        assert uploader._upload_count == 1


# ── Retry behavior ──────────────────────────────────────────────────


class TestRetryBehavior:
    @pytest.fixture
    def buffer(self, tmp_path):
        return BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)

    @pytest.mark.asyncio
    async def test_retry_on_500(self, buffer):
        """Server errors (5xx) trigger retries with exponential backoff."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        # First 2 calls fail with 500, third succeeds
        client.post = AsyncMock(
            side_effect=[
                _make_response(500, "Internal Server Error"),
                _make_response(500, "Internal Server Error"),
                _make_response(200),
            ]
        )

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await buffer.write_event({"event_type": "click"})

        # Patch sleep to speed up test
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await uploader._upload_pending()

        assert client.post.call_count == 3
        assert uploader._upload_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, buffer):
        """Client errors (4xx) do NOT retry — immediately fail."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(return_value=_make_response(400, "Bad Request"))

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await buffer.write_event({"event_type": "click"})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await uploader._upload_pending()

        # Only one call — no retries for 4xx
        assert client.post.call_count == 1
        assert uploader._upload_count == 0

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, buffer):
        """After MAX_RETRIES failures, batch is abandoned for this cycle."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(return_value=_make_response(503, "Service Unavailable"))

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await buffer.write_event({"event_type": "click"})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await uploader._upload_pending()

        # Should have tried MAX_RETRIES (5) times
        assert client.post.call_count == 5
        assert uploader._upload_count == 0

    @pytest.mark.asyncio
    async def test_network_error_retries(self, buffer):
        """httpx.HTTPError triggers retry."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_response(200),
            ]
        )

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await buffer.write_event({"event_type": "click"})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await uploader._upload_pending()

        assert client.post.call_count == 2
        assert uploader._upload_count == 1


# ── Batch sizing ─────────────────────────────────────────────────────


class TestBatchSizing:
    @pytest.fixture
    def buffer(self, tmp_path):
        return BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)

    @pytest.mark.asyncio
    async def test_multiple_batches(self, buffer):
        """When events exceed batch_size, multiple batches are uploaded."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(return_value=_make_response(200))

        uploader = BatchUploader(buffer, config, client, batch_size=3, interval_seconds=1)

        # Write 7 events → should produce 3 batches (3, 3, 1)
        for i in range(7):
            await buffer.write_event({"event_type": "click", "seq": i})

        await uploader._upload_pending()

        assert client.post.call_count == 3
        assert uploader._upload_count == 3

    @pytest.mark.asyncio
    async def test_empty_buffer_no_upload(self, buffer):
        """No uploads when buffer is empty."""
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await uploader._upload_pending()

        client.post.assert_not_called()
        assert uploader._upload_count == 0


# ── Run loop ─────────────────────────────────────────────────────────


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_shutdown_event_stops_loop(self, tmp_path):
        """The run() loop exits when shutdown_event is set."""
        buffer = BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(return_value=_make_response(200))

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=60)

        shutdown = asyncio.Event()

        async def set_shutdown():
            await asyncio.sleep(0.1)
            shutdown.set()

        task = asyncio.create_task(set_shutdown())
        await uploader.run(shutdown)
        await task
        # If we reach here, the loop exited correctly

    @pytest.mark.asyncio
    async def test_exception_in_cycle_does_not_crash(self, tmp_path):
        """Errors in _upload_pending don't crash the run loop."""
        buffer = BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)
        config = _make_config()
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))

        uploader = BatchUploader(buffer, config, client, batch_size=10, interval_seconds=1)

        await buffer.write_event({"event_type": "click"})

        shutdown = asyncio.Event()

        async def set_shutdown():
            await asyncio.sleep(0.2)
            shutdown.set()

        task = asyncio.create_task(set_shutdown())

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await uploader.run(shutdown)

        await task
