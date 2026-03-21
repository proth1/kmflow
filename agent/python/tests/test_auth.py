"""Tests for agent JWT authentication and HTTP client factory.

Covers: token retrieval (env, Keychain, legacy file), JWT expiry detection,
AuthManager lifecycle, create_http_client (headers, HTTPS enforcement, TLS).
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest
from kmflow_agent.auth import (
    AuthManager,
    _is_token_expired,
    create_http_client,
    get_auth_token,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_jwt(payload: dict, header: dict | None = None) -> str:
    """Build a minimal unsigned JWT (header.payload.signature) for testing."""
    hdr = header or {"alg": "HS256", "typ": "JWT"}
    h = base64.urlsafe_b64encode(json.dumps(hdr).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h}.{p}.test_signature"


# ── get_auth_token ───────────────────────────────────────────────────


class TestGetAuthToken:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("KMFLOW_AGENT_TOKEN", "env-token-123")
        assert get_auth_token() == "env-token-123"

    @patch("kmflow_agent.auth._read_keychain", return_value="keychain-tok")
    def test_keychain_when_no_env(self, mock_kc, monkeypatch):
        monkeypatch.delenv("KMFLOW_AGENT_TOKEN", raising=False)
        assert get_auth_token() == "keychain-tok"
        mock_kc.assert_called_once_with("agent_token")

    @patch("kmflow_agent.auth._write_keychain", return_value=True)
    @patch("kmflow_agent.auth._read_keychain", return_value=None)
    def test_legacy_file_migration(self, mock_kc_read, mock_kc_write, monkeypatch, tmp_path):
        monkeypatch.delenv("KMFLOW_AGENT_TOKEN", raising=False)

        token_dir = tmp_path / "KMFlowAgent"
        token_dir.mkdir()
        token_file = token_dir / ".agent_token"
        token_file.write_text("legacy-token-456\n")

        # Patch the legacy token path
        with patch("kmflow_agent.auth.Path") as mock_path_cls:
            # First call to Path() for the token_path construction
            mock_path_instance = MagicMock()
            mock_path_instance.read_text.return_value = "legacy-token-456\n"
            mock_path_cls.return_value = mock_path_instance

            token = get_auth_token()
            assert token == "legacy-token-456"
            mock_kc_write.assert_called_once_with("agent_token", "legacy-token-456")

    @patch("kmflow_agent.auth._read_keychain", return_value=None)
    def test_all_sources_empty_returns_none(self, mock_kc, monkeypatch):
        monkeypatch.delenv("KMFLOW_AGENT_TOKEN", raising=False)
        # Legacy file doesn't exist → OSError → returns None
        assert get_auth_token() is None


# ── _is_token_expired ────────────────────────────────────────────────


class TestIsTokenExpired:
    def test_valid_token_not_expired(self):
        exp = int(time.time()) + 3600  # 1 hour from now
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        assert _is_token_expired(token) is False

    def test_expired_token(self):
        exp = int(time.time()) - 100  # 100 seconds ago
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        assert _is_token_expired(token) is True

    def test_token_expiring_within_buffer(self):
        exp = int(time.time()) + 200  # 200 seconds — within 300s buffer
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        assert _is_token_expired(token, buffer_seconds=300) is True

    def test_custom_buffer_seconds(self):
        exp = int(time.time()) + 200
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        # With 100s buffer, 200s remaining is fine
        assert _is_token_expired(token, buffer_seconds=100) is False

    def test_no_exp_claim_treated_as_non_expiring(self):
        token = _make_jwt({"sub": "agent-1"})
        assert _is_token_expired(token) is False

    def test_malformed_token_treated_as_expired(self):
        assert _is_token_expired("not-a-jwt") is True

    def test_invalid_base64_treated_as_expired(self):
        assert _is_token_expired("a.!!!invalid!!!.c") is True

    def test_empty_payload_treated_as_expired(self):
        assert _is_token_expired("a..c") is True


# ── AuthManager ──────────────────────────────────────────────────────


class TestAuthManager:
    def test_initial_state_needs_refresh(self):
        mgr = AuthManager()
        assert mgr.token is None
        assert mgr.needs_refresh is True

    def test_set_valid_token(self):
        mgr = AuthManager()
        exp = int(time.time()) + 3600
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        mgr.set_token(token)
        assert mgr.token == token
        assert mgr.needs_refresh is False

    def test_expired_token_returns_none(self):
        mgr = AuthManager()
        exp = int(time.time()) - 100
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        mgr.set_token(token)
        assert mgr.token is None
        assert mgr.needs_refresh is True

    def test_custom_buffer(self):
        mgr = AuthManager(buffer_seconds=60)
        exp = int(time.time()) + 120  # 2 min out, 1 min buffer
        token = _make_jwt({"sub": "agent-1", "exp": exp})
        mgr.set_token(token)
        assert mgr.token == token


# ── create_http_client ───────────────────────────────────────────────


class TestCreateHttpClient:
    def test_no_args_creates_client(self):
        client = create_http_client()
        assert client is not None
        assert "Authorization" not in client.headers

    def test_token_sets_bearer_header(self):
        client = create_http_client(token="my-token")
        assert client.headers["authorization"] == "Bearer my-token"

    def test_https_enforcement_rejects_http(self):
        with pytest.raises(ValueError, match="HTTP is not allowed"):
            create_http_client(base_url="http://external-server.com")

    def test_localhost_http_allowed(self):
        client = create_http_client(base_url="http://localhost:8000")
        assert client is not None

    def test_127_0_0_1_http_allowed(self):
        client = create_http_client(base_url="http://127.0.0.1:8000")
        assert client is not None

    def test_ipv6_loopback_http_allowed(self):
        client = create_http_client(base_url="http://[::1]:8000")
        assert client is not None

    def test_https_external_allowed(self):
        client = create_http_client(base_url="https://api.kmflow.io")
        assert client is not None

    @patch("kmflow_agent.auth._get_ca_bundle_path", return_value=None)
    @patch("kmflow_agent.auth._get_client_cert", return_value=None)
    def test_no_ca_bundle_uses_default_verify(self, mock_cert, mock_ca):
        client = create_http_client()
        assert client is not None

    def test_timeout_is_30_seconds(self):
        client = create_http_client()
        assert client.timeout.connect == 30.0
