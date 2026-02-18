"""Tests for Fernet encryption (src/core/encryption.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from src.core.config import Settings


class TestEncryption:
    """Test encrypt/decrypt roundtrip with a known Fernet key."""

    @pytest.fixture(autouse=True)
    def _mock_settings(self):
        key = Fernet.generate_key().decode()
        mock_settings = Settings(encryption_key=key)
        with patch("src.core.encryption.get_settings", return_value=mock_settings):
            yield

    def test_encrypt_decrypt_roundtrip(self) -> None:
        from src.core.encryption import decrypt_value, encrypt_value

        plaintext = "sensitive-credential-value"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext
        assert decrypt_value(ciphertext) == plaintext

    def test_encrypt_dict_roundtrip(self) -> None:
        from src.core.encryption import decrypt_dict, encrypt_dict

        data = {"host": "db.example.com", "port": 5432, "password": "secret"}
        ciphertext = encrypt_dict(data)
        assert isinstance(ciphertext, str)
        result = decrypt_dict(ciphertext)
        assert result == data

    def test_different_plaintexts_produce_different_ciphertexts(self) -> None:
        from src.core.encryption import encrypt_value

        ct1 = encrypt_value("value_a")
        ct2 = encrypt_value("value_b")
        assert ct1 != ct2

    def test_decrypt_invalid_ciphertext_raises(self) -> None:
        from cryptography.fernet import InvalidToken

        from src.core.encryption import decrypt_value

        with pytest.raises(InvalidToken):
            decrypt_value("not-valid-ciphertext")

    def test_encrypt_empty_string(self) -> None:
        from src.core.encryption import decrypt_value, encrypt_value

        ct = encrypt_value("")
        assert decrypt_value(ct) == ""
