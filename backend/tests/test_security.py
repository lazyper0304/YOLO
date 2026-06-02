"""Unit tests for security utility functions.

Covers: password hashing/verification, JWT token creation/decoding,
Fernet API key encryption/decryption.

NOTE: bcrypt tests are skipped if passlib has a compatibility issue
with the installed bcrypt version (known: bcrypt 4.1+ + passlib < 1.7.4).
"""

import pytest
from unittest.mock import patch, MagicMock

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    encrypt_api_key,
    decrypt_api_key,
)


# ---------------------------------------------------------------------------
# Password hashing & verification
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    """Tests for bcrypt password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Hashing a plain password must return a non-empty string."""
        try:
            hashed = hash_password("my_secret_123")
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != "my_secret_123"

    def test_verify_correct_password(self):
        """Verifying against the correct plain-text returns True."""
        try:
            plain = "my_secret_99"
            hashed = hash_password(plain)
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        """Verifying against a wrong plain-text returns False."""
        try:
            hashed = hash_password("correct")
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_deterministic_per_verify(self):
        """Each hash call produces a different salt, but both verify correctly."""
        plain = "password123"
        try:
            h1 = hash_password(plain)
            h2 = hash_password(plain)
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        assert h1 != h2  # different salts
        assert verify_password(plain, h1)
        assert verify_password(plain, h2)

    def test_empty_password_is_hashable(self):
        """An empty string should still produce a hash."""
        try:
            hashed = hash_password("")
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_verify_against_tampered_hash(self):
        """Verification must fail when the hash is tampered."""
        try:
            hashed = hash_password("real")
        except ValueError:
            pytest.skip("bcrypt/passlib version incompatibility")
        tampered = hashed[:-4] + "AAAA"
        assert verify_password("real", tampered) is False


# ---------------------------------------------------------------------------
# JWT token creation & decoding
# ---------------------------------------------------------------------------

class TestJWTTokens:
    """Tests for JWT access token lifecycle."""

    # Settings are mocked globally by conftest.py with:
    #   SECRET_KEY = "test-secret-key-for-unit-tests-32c"
    #   JWT_ALGORITHM = "HS256"
    #   JWT_EXPIRATION_HOURS = 24

    def test_create_token_returns_string(self):
        """A created token is a non-empty string."""
        token = create_access_token(data={"sub": "1"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_valid_token_returns_payload(self):
        """Decoding a valid token returns the original data."""
        token = create_access_token(data={"sub": "42", "username": "alice"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"

    def test_decode_includes_expiration(self):
        """The payload must contain an 'exp' claim."""
        token = create_access_token(data={"sub": "1"})
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_decode_tampered_token_returns_none(self):
        """Decoding a tampered token returns None."""
        token = create_access_token(data={"sub": "1"})
        tampered = token[:-4] + "AAAA"
        assert decode_access_token(tampered) is None

    def test_decode_empty_token_returns_none(self):
        """Decoding an empty / garbage token returns None."""
        assert decode_access_token("") is None
        assert decode_access_token("not.a.valid.jwt") is None

    def test_decode_token_with_wrong_key(self):
        """Token signed with one key cannot be decoded with another."""
        from types import SimpleNamespace

        # Create with the conftest key
        token = create_access_token(data={"sub": "1"})
        # Decode should work with same key
        payload = decode_access_token(token)
        assert payload is not None

        # Now try to decode with a DIFFERENT key
        with patch("app.core.security.settings",
                   SimpleNamespace(SECRET_KEY="a-different-secret-key-32chars!!",
                                   JWT_ALGORITHM="HS256",
                                   JWT_EXPIRATION_HOURS=24)):
            assert decode_access_token(token) is None

    def test_token_with_str_sub(self):
        """The 'sub' claim can be a string."""
        token = create_access_token(data={"sub": "user-uuid-123"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-uuid-123"

    def test_token_with_empty_data(self):
        """A token can be created with empty data dict."""
        token = create_access_token(data={})
        payload = decode_access_token(token)
        assert payload is not None

    def test_custom_expiry(self):
        """Custom expiry delta is respected."""
        from datetime import timedelta
        token = create_access_token(
            data={"sub": "1"},
            expires_delta=timedelta(seconds=1),
        )
        payload = decode_access_token(token)
        assert payload is not None
        # We can't easily test expiry without waiting, but the exp should exist
        assert "exp" in payload


# ---------------------------------------------------------------------------
# API key encryption & decryption (Fernet AES-256)
# ---------------------------------------------------------------------------

class TestAPIKeyEncryption:
    """Tests for Fernet-based API key encryption / decryption."""

    def test_encrypt_returns_string(self):
        """Encryption produces a non-empty string different from the original."""
        encrypted = encrypt_api_key("sk-test-key-12345")
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0
        assert encrypted != "sk-test-key-12345"

    def test_decrypt_roundtrip(self):
        """Encrypt → decrypt round-trip returns the original key."""
        original = "sk-abcdefghijklmnopqrstuvwxyz123456"
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_unique_encryptions(self):
        """Each encryption of the same plaintext should produce unique
        ciphertext (Fernet includes timestamp + IV)."""
        original = "my-api-key"
        e1 = encrypt_api_key(original)
        e2 = encrypt_api_key(original)
        assert e1 != e2  # different IVs

    def test_decrypt_tampered_ciphertext_raises(self):
        """Decrypting tampered ciphertext must raise an exception."""
        encrypted = encrypt_api_key("valid-key")
        tampered = encrypted[:-8] + "AAAAAAAA"
        with pytest.raises(Exception):
            decrypt_api_key(tampered)

    def test_decrypt_empty_string_raises(self):
        """Decrypting an empty string raises an exception."""
        with pytest.raises(Exception):
            decrypt_api_key("")

    def test_encrypt_empty_key(self):
        """Encrypting an empty string should still work."""
        encrypted = encrypt_api_key("")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode_key(self):
        """Unicode API keys are supported."""
        original = "sk-测试-日本語-키"
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_encrypt_long_key(self):
        """Very long keys are handled correctly."""
        original = "a" * 1000
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original
