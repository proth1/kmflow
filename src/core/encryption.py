"""Fernet-based encryption for sensitive data at rest.

Used to encrypt integration credentials, API keys, and other
secrets stored in the database.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the configured encryption key."""
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY not configured. Set it in environment or .env file."
        )
    # Ensure key is valid Fernet format (32 url-safe base64 bytes)
    # If a plain string is provided, derive a proper key from it
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
        fernet_key = key.encode() if isinstance(key, str) else key
    except (ValueError, Exception):
        # Derive a proper Fernet key from the provided secret
        derived = hashlib.sha256(key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value and return base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext and return plaintext."""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or wrong key")
        raise


def encrypt_dict(data: dict) -> str:
    """Encrypt a dictionary as JSON string."""
    import json
    return encrypt_value(json.dumps(data))


def decrypt_dict(ciphertext: str) -> dict:
    """Decrypt a ciphertext back to a dictionary."""
    import json
    return json.loads(decrypt_value(ciphertext))
