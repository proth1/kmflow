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


_LEGACY_FIXED_SALT = b"kmflow-fernet-key-derivation-v1"


def _derive_fernet_key(secret: str, *, legacy_salt: bool = False) -> bytes:
    """Derive a valid Fernet key from an arbitrary secret string.

    Args:
        secret: The raw encryption key string.
        legacy_salt: If True, use the old fixed salt for backward compatibility
            when decrypting data encrypted before the per-deployment salt migration.
    """
    try:
        Fernet(secret.encode())
        return secret.encode()
    except (ValueError, Exception):
        salt = _LEGACY_FIXED_SALT if legacy_salt else hashlib.sha256(secret.encode()).digest()[:16]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            salt,
            iterations=600_000,
        )
        return base64.urlsafe_b64encode(derived)


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the current encryption key."""
    settings = get_settings()
    key = settings.encryption_key.get_secret_value()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY not configured. Set it in environment or .env file.")
    return Fernet(_derive_fernet_key(key))


def _get_fernet_previous() -> Fernet | None:
    """Get a Fernet instance using the previous encryption key, if configured."""
    settings = get_settings()
    prev_key = settings.encryption_key_previous
    if not prev_key:
        return None
    # encryption_key_previous is a plain str (rotation key supplied at runtime)
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
        pass

    # Try legacy fixed salt (data encrypted before per-deployment salt migration)
    settings = get_settings()
    key = settings.encryption_key.get_secret_value()
    try:
        legacy_f = Fernet(_derive_fernet_key(key, legacy_salt=True))
        plaintext = legacy_f.decrypt(ciphertext.encode()).decode()
        logger.info("Decrypted value using legacy salt — consider re-encrypting")
        return plaintext
    except InvalidToken:
        pass

    # Try previous key for rotation support
    prev = _get_fernet_previous()
    if prev:
        try:
            return prev.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            pass
    logger.error("Failed to decrypt value — invalid token or wrong key")
    raise InvalidToken


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
