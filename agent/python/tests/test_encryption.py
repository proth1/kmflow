"""Tests for AES-256-GCM encryption."""

from __future__ import annotations

import pytest

from kmflow_agent.buffer.encryption import decrypt_payload, encrypt_payload


def test_encrypt_decrypt_roundtrip():
    key = b"test-key-32-bytes-long-for-aes!!"
    plaintext = b"Hello, World! This is secret."

    encrypted = encrypt_payload(plaintext, key)
    assert encrypted != plaintext
    assert len(encrypted) > len(plaintext)  # nonce + ciphertext + tag

    decrypted = decrypt_payload(encrypted, key)
    assert decrypted == plaintext


def test_different_nonces():
    key = b"test-key-32-bytes-long-for-aes!!"
    plaintext = b"Same message"

    enc1 = encrypt_payload(plaintext, key)
    enc2 = encrypt_payload(plaintext, key)

    # Same plaintext should produce different ciphertext (random nonce)
    assert enc1 != enc2

    # Both should decrypt to the same plaintext
    assert decrypt_payload(enc1, key) == plaintext
    assert decrypt_payload(enc2, key) == plaintext


def test_wrong_key_fails():
    key1 = b"test-key-32-bytes-long-for-aes!!"
    key2 = b"wrong-key-32-bytes-long-for-aes!"
    plaintext = b"Secret data"

    encrypted = encrypt_payload(plaintext, key1)

    with pytest.raises(Exception):
        decrypt_payload(encrypted, key2)


def test_empty_plaintext():
    key = b"test-key-32-bytes-long-for-aes!!"
    plaintext = b""

    encrypted = encrypt_payload(plaintext, key)
    decrypted = decrypt_payload(encrypted, key)
    assert decrypted == plaintext


def test_large_payload():
    key = b"test-key-32-bytes-long-for-aes!!"
    plaintext = b"x" * 100_000

    encrypted = encrypt_payload(plaintext, key)
    decrypted = decrypt_payload(encrypted, key)
    assert decrypted == plaintext
