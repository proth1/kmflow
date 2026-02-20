"""Tests for WebSocket authentication in the monitoring endpoint.

Tests cover: valid token connects, missing token rejected, expired token
rejected, invalid token rejected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.routes.websocket import router
from src.core.config import Settings

# Use a stable secret for all tests
_SECRET = "test-secret-key-for-websocket-tests"
_ALGORITHM = "HS256"


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with test JWT configuration."""
    kwargs = {
        "jwt_secret_key": _SECRET,
        "jwt_algorithm": _ALGORITHM,
        "jwt_access_token_expire_minutes": 30,
        "jwt_refresh_token_expire_minutes": 10080,
        "monitoring_worker_count": 0,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _make_token(payload: dict, secret: str = _SECRET, algorithm: str = _ALGORITHM) -> str:
    """Encode a JWT token with the given payload."""
    return jwt.encode(payload, secret, algorithm=algorithm)


def _make_valid_access_token() -> str:
    """Create a valid, non-expired access token."""
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=30),
    }
    return _make_token(payload)


def _make_app(redis_client: AsyncMock | None = None) -> FastAPI:
    """Build a minimal FastAPI app with the websocket router."""
    from src.core.config import get_settings

    app = FastAPI()
    app.include_router(router)
    app.state.redis_client = redis_client or AsyncMock()

    test_settings = _make_settings()
    app.dependency_overrides[get_settings] = lambda: test_settings
    return app


# ---------------------------------------------------------------------------
# Missing token
# ---------------------------------------------------------------------------


class TestWebSocketMissingToken:
    """WebSocket endpoint rejects connections with no token."""

    def test_missing_token_closes_with_1008(self) -> None:
        """Connection without token query param should close with code 1008."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.pubsub = MagicMock()

        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            # When server closes with code 1008, Starlette raises WebSocketDisconnect
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/monitoring/eng-123") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008


# ---------------------------------------------------------------------------
# Valid token
# ---------------------------------------------------------------------------


class TestWebSocketValidToken:
    """WebSocket endpoint accepts connections with a valid token."""

    def test_valid_token_accepted(self) -> None:
        """A valid, non-expired access token should pass authentication."""
        token = _make_valid_access_token()
        redis_mock = AsyncMock()
        # Not blacklisted
        redis_mock.get = AsyncMock(return_value=None)
        pubsub_mock = AsyncMock()
        pubsub_mock.subscribe = AsyncMock()
        pubsub_mock.unsubscribe = AsyncMock()
        pubsub_mock.close = AsyncMock()
        pubsub_mock.get_message = AsyncMock(return_value=None)
        redis_mock.pubsub = MagicMock(return_value=pubsub_mock)

        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            with client.websocket_connect(f"/ws/monitoring/eng-123?token={token}") as ws:
                # Connection accepted — send a ping to verify it's live
                ws.send_text("ping")
                data = ws.receive_text()
                assert data == "pong"


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------


class TestWebSocketExpiredToken:
    """WebSocket endpoint rejects expired tokens."""

    def test_expired_token_closes_with_1008(self) -> None:
        """An expired JWT should be rejected and connection closed."""
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            # expired 1 hour ago
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        expired_token = _make_token(payload)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/monitoring/eng-123?token={expired_token}") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008


# ---------------------------------------------------------------------------
# Invalid token
# ---------------------------------------------------------------------------


class TestWebSocketInvalidToken:
    """WebSocket endpoint rejects malformed or wrongly-signed tokens."""

    def test_invalid_signature_closes_with_1008(self) -> None:
        """A token signed with the wrong secret should be rejected."""
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        }
        # Sign with a different secret
        bad_token = _make_token(payload, secret="wrong-secret")

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/monitoring/eng-123?token={bad_token}") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008

    def test_garbage_token_closes_with_1008(self) -> None:
        """A completely malformed token string should be rejected."""
        redis_mock = AsyncMock()
        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws/monitoring/eng-123?token=not.a.valid.jwt") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008

    def test_refresh_token_type_rejected(self) -> None:
        """A refresh token (type != 'access') should be rejected."""
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        }
        refresh_token = _make_token(payload)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        app = _make_app(redis_mock)

        with patch("src.api.routes.websocket.get_settings", return_value=_make_settings()):
            client = TestClient(app)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/ws/monitoring/eng-123?token={refresh_token}") as ws:
                    ws.receive_text()
            assert exc_info.value.code == 1008
