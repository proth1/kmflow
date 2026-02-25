"""AES-256-GCM envelope encryption for buffer payloads.

Each event is encrypted with a random nonce. The encryption key
is derived from the macOS Keychain in production, or from an
environment variable during development.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12  # 96 bits for AES-GCM


def encrypt_payload(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt a payload using AES-256-GCM.

    Returns: nonce (12 bytes) || ciphertext
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key[:32])
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_payload(data: bytes, key: bytes) -> bytes:
    """Decrypt a payload encrypted with encrypt_payload.

    Expects: nonce (12 bytes) || ciphertext
    """
    nonce = data[:NONCE_SIZE]
    ciphertext = data[NONCE_SIZE:]
    aesgcm = AESGCM(key[:32])
    return aesgcm.decrypt(nonce, ciphertext, None)
