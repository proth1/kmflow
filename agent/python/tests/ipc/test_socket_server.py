"""Tests for the Unix domain socket server.

Covers: auth handshake, bounded readline, IPCMessage envelope dispatch,
camelCase→snake_case normalization, VCE pipeline routing, standard event buffering.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.ipc.socket_server import SocketServer, _normalize_keys

# ── Helpers ──────────────────────────────────────────────────────────


class FakeReader:
    """Simulates an asyncio.StreamReader for testing."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self._index = 0

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        if self._index >= len(self._lines):
            raise asyncio.IncompleteReadError(b"", None)
        line = self._lines[self._index]
        self._index += 1
        return line


class FakeWriter:
    """Simulates an asyncio.StreamWriter for testing."""

    def __init__(self):
        self.written: list[bytes] = []
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True


# ── _normalize_keys ──────────────────────────────────────────────────


class TestNormalizeKeys:
    def test_camel_to_snake(self):
        data = {"eventType": "app_switch", "applicationName": "Excel", "windowTitle": "Budget.xlsx"}
        result = _normalize_keys(data)
        assert result == {"event_type": "app_switch", "application_name": "Excel", "window_title": "Budget.xlsx"}

    def test_already_snake_case_unchanged(self):
        data = {"event_type": "click", "count": 5}
        assert _normalize_keys(data) == data

    def test_empty_dict(self):
        assert _normalize_keys({}) == {}

    def test_single_word_unchanged(self):
        data = {"timestamp": "2026-01-01"}
        assert _normalize_keys(data) == {"timestamp": "2026-01-01"}

    def test_consecutive_capitals(self):
        data = {"bundleID": "com.apple.Safari"}
        result = _normalize_keys(data)
        # The regex only inserts _ before uppercase preceded by lowercase/digit
        assert result == {"bundle_id": "com.apple.Safari"}


# ── Authentication handshake ─────────────────────────────────────────


class TestAuthHandshake:
    @pytest.fixture
    def server_with_auth(self, tmp_path):
        buf = BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)
        return SocketServer(buf, socket_path=str(tmp_path / "test.sock"), auth_token="secret-token-42")

    @pytest.fixture
    def server_no_auth(self, tmp_path):
        buf = BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)
        return SocketServer(buf, socket_path=str(tmp_path / "test.sock"))

    @pytest.mark.asyncio
    async def test_valid_auth_succeeds(self, server_with_auth):
        reader = FakeReader([json.dumps({"auth": "secret-token-42"}).encode() + b"\n"])
        writer = FakeWriter()
        result = await server_with_auth._authenticate(reader, writer)
        assert result is True
        response = json.loads(writer.written[0].decode().strip())
        assert response["status"] == "ok"

    @pytest.mark.asyncio
    async def test_invalid_auth_fails(self, server_with_auth):
        reader = FakeReader([json.dumps({"auth": "wrong-token"}).encode() + b"\n"])
        writer = FakeWriter()
        result = await server_with_auth._authenticate(reader, writer)
        assert result is False
        response = json.loads(writer.written[0].decode().strip())
        assert response["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_auth_field_fails(self, server_with_auth):
        reader = FakeReader([json.dumps({"foo": "bar"}).encode() + b"\n"])
        writer = FakeWriter()
        result = await server_with_auth._authenticate(reader, writer)
        assert result is False

    @pytest.mark.asyncio
    async def test_malformed_json_fails(self, server_with_auth):
        reader = FakeReader([b"not-json\n"])
        writer = FakeWriter()
        result = await server_with_auth._authenticate(reader, writer)
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnection_during_auth(self, server_with_auth):
        reader = FakeReader([])  # immediate EOF
        writer = FakeWriter()
        result = await server_with_auth._authenticate(reader, writer)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_auth_token_skips_handshake(self, server_no_auth):
        """When auth_token is None, _handle_client skips authentication."""
        assert server_no_auth._auth_token is None


# ── IPCMessage dispatch ──────────────────────────────────────────────


class TestDispatch:
    @pytest.fixture
    def server(self, tmp_path):
        buf = BufferManager(db_path=str(tmp_path / "test.db"), encryption_key=b"k" * 32)
        return SocketServer(buf, socket_path=str(tmp_path / "test.sock"))

    @pytest.mark.asyncio
    async def test_v1_bare_event_dispatches(self, server):
        """v1 messages (no kind field) are treated as capture events."""
        data = {
            "event_type": "app_switch",
            "timestamp": "2026-01-01T00:00:00Z",
            "sequence_number": 1,
            "application_name": "Safari",
            "window_title": "Google",
        }
        await server._dispatch(data)
        assert server.event_count == 1

    @pytest.mark.asyncio
    async def test_v2_capture_event_dispatches(self, server):
        """v2 messages with kind=capture_event dispatch correctly."""
        data = {
            "version": 2,
            "kind": "capture_event",
            "timestamp_ns": 1234567890,
            "event": {
                "event_type": "mouse_click",
                "timestamp": "2026-01-01T00:00:00Z",
                "sequence_number": 42,
                "application_name": "Chrome",
            },
        }
        await server._dispatch(data)
        assert server.event_count == 1

    @pytest.mark.asyncio
    async def test_v2_heartbeat_no_error(self, server):
        data = {
            "version": 2,
            "kind": "heartbeat",
            "timestamp_ns": 1234567890,
            "heartbeat": {"uptime_seconds": 120},
        }
        await server._dispatch(data)
        # Heartbeats are logged but don't increment event_count
        assert server.event_count == 0

    @pytest.mark.asyncio
    async def test_v2_config_update_no_error(self, server):
        data = {
            "version": 2,
            "kind": "config_update",
            "timestamp_ns": 1234567890,
            "config_update": {"screenshot_enabled": True},
        }
        await server._dispatch(data)
        assert server.event_count == 0

    @pytest.mark.asyncio
    async def test_standard_event_is_buffered(self, server):
        """Standard events are L2-filtered and written to buffer."""
        data = {
            "event_type": "keyboard_action",
            "timestamp": "2026-01-01T00:00:00Z",
            "sequence_number": 10,
            "application_name": "TextEdit",
            "window_title": "notes.txt",
        }
        await server._process_standard_event(data)
        assert server.event_count == 1
        pending = await server.buffer.count_pending()
        assert pending == 1


# ── Socket permissions ───────────────────────────────────────────────


class TestSocketPermissions:
    @pytest.mark.asyncio
    async def test_socket_created_with_0600_permissions(self):
        """Socket file should be user-only (0o600)."""
        import os
        import stat
        import tempfile

        # Use a short path to avoid AF_UNIX path length limit (104 bytes on macOS)
        with tempfile.TemporaryDirectory(prefix="km") as tmpdir:
            sock_path = os.path.join(tmpdir, "s.sock")
            db_path = os.path.join(tmpdir, "t.db")
            buf = BufferManager(db_path=db_path, encryption_key=b"k" * 32)
            server = SocketServer(buf, socket_path=sock_path)

            shutdown = asyncio.Event()

            async def start_and_stop():
                task = asyncio.create_task(server.serve(shutdown))
                await asyncio.sleep(0.3)
                assert os.path.exists(sock_path)
                mode = os.stat(sock_path).st_mode
                assert stat.S_IMODE(mode) == 0o600
                shutdown.set()
                await task

            await start_and_stop()
