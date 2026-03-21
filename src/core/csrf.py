"""CSRF token generation (shared between core.auth and api.middleware.csrf)."""

from __future__ import annotations

import hashlib
import hmac

from src.core.config import get_settings


def generate_csrf_token(access_cookie_value: str) -> str:
    """Generate CSRF token cryptographically bound to the current session."""
    settings = get_settings()
    secret = settings.jwt_secret_key.get_secret_value()
    return hmac.new(
        secret.encode(),
        access_cookie_value.encode(),
        hashlib.sha256,
    ).hexdigest()
