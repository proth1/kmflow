"""Fernet-based encryption for sensitive data at rest.

Used to encrypt integration credentials, API keys, and other
secrets stored in the database. Supports key rotation with
automatic fallback to the previous key for decryption.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a valid Fernet key from an arbitrary secret string."""
    try:
        Fernet(secret.encode())
        return secret.encode()
    except (ValueError, Exception):
        derived = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(derived)


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the current encryption key."""
    settings = get_settings()
    key = settings.encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not configured. Set it in environment or .env file.")
    return Fernet(_derive_fernet_key(key))


def _get_fernet_previous() -> Fernet | None:
    """Get a Fernet instance using the previous encryption key, if configured."""
    settings = get_settings()
    prev_key = settings.encryption_key_previous
    if not prev_key:
        return None
    return Fernet(_derive_fernet_key(prev_key))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value and return base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext.

    Tries the current key first, then falls back to the previous key
    if key rotation is in progress.
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Try previous key for rotation support
        prev = _get_fernet_previous()
        if prev:
            try:
                return prev.decrypt(ciphertext.encode()).decode()
            except InvalidToken:
                pass
        logger.error("Failed to decrypt value — invalid token or wrong key")
        raise


def encrypt_dict(data: dict) -> str:
    """Encrypt a dictionary as JSON string."""
    return encrypt_value(json.dumps(data))


def decrypt_dict(ciphertext: str) -> dict:
    """Decrypt a ciphertext back to a dictionary."""
    return json.loads(decrypt_value(ciphertext))


def re_encrypt_value(ciphertext: str) -> str:
    """Re-encrypt a value with the current key.

    Decrypts with current or previous key, then encrypts with current key.
    Used during key rotation to migrate encrypted data.
    """
    plaintext = decrypt_value(ciphertext)
    return encrypt_value(plaintext)
