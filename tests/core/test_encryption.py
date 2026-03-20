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

    def test_decrypt_legacy_salt_ciphertext(self) -> None:
        """Verify decrypt_value handles data encrypted with the legacy fixed salt."""
        from src.core.encryption import _derive_fernet_key, decrypt_value

        # Use a non-Fernet passphrase so _derive_fernet_key uses PBKDF2
        # (a valid Fernet key bypasses derivation, making legacy_salt irrelevant)
        passphrase = "my-passphrase-not-a-fernet-key"

        from unittest.mock import patch as _patch

        from src.core.config import Settings

        mock_settings = Settings(encryption_key=passphrase)
        with _patch("src.core.encryption.get_settings", return_value=mock_settings):
            legacy_fernet = Fernet(_derive_fernet_key(passphrase, legacy_salt=True))
            plaintext = "legacy-encrypted-secret"
            legacy_ciphertext = legacy_fernet.encrypt(plaintext.encode()).decode()

            assert decrypt_value(legacy_ciphertext) == plaintext

    def test_re_encrypt_with_same_key(self) -> None:
        """Re-encrypting with the same key produces valid ciphertext."""
        from src.core.encryption import decrypt_value, encrypt_value, re_encrypt_value

        original = "rotate-me"
        ct1 = encrypt_value(original)
        ct2 = re_encrypt_value(ct1)
        assert ct2 != ct1  # Different ciphertext (Fernet uses random IV)
        assert decrypt_value(ct2) == original

    def test_re_encrypt_with_rotated_key(self) -> None:
        """Re-encrypting after key rotation migrates to new key."""
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()

        # Encrypt with old key
        old_fernet = Fernet(old_key.encode())
        original = "secret-data"
        old_ct = old_fernet.encrypt(original.encode()).decode()

        # Re-encrypt: new key as primary, old key as previous
        mock_settings = Settings(encryption_key=new_key, encryption_key_previous=old_key)
        with patch("src.core.encryption.get_settings", return_value=mock_settings):
            from src.core.encryption import re_encrypt_value

            new_ct = re_encrypt_value(old_ct)
            # Verify new ciphertext decrypts with new key alone
            new_fernet = Fernet(new_key.encode())
            assert new_fernet.decrypt(new_ct.encode()).decode() == original

    def test_re_encrypt_invalid_ciphertext_raises(self) -> None:
        """re_encrypt_value raises on invalid ciphertext."""
        from cryptography.fernet import InvalidToken

        from src.core.encryption import re_encrypt_value

        with pytest.raises(InvalidToken):
            re_encrypt_value("not-valid-ciphertext")
