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
    """Derive a valid Fernet key from an arbitrary secret string.

    The salt is derived from the secret itself using a single SHA-256 pass so
    that each deployment's key material produces a unique salt without
    requiring a separately-stored value.  This eliminates the previous fixed
    application-level salt (b"kmflow-fernet-key-derivation-v1") which was
    identical across all deployments and offered no protection if the PBKDF2
    output for the default dev key was ever pre-computed.
    """
    try:
        Fernet(secret.encode())
        return secret.encode()
    except (ValueError, Exception):
        # Derive a per-deployment salt from the secret itself: SHA-256(secret)
        # truncated to 16 bytes.  This ensures the salt differs across deployments
        # without needing external storage.
        per_deployment_salt = hashlib.sha256(secret.encode()).digest()[:16]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            per_deployment_salt,
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
