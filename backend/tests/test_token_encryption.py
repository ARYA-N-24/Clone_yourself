"""
Unit tests for backend/utils/token_encryption.py

Covers:
- encrypt → decrypt round-trip (idempotency)
- Encrypted ciphertext differs from plaintext
- Decryption with a wrong key raises an error
- Missing TOKEN_ENCRYPTION_KEY raises EnvironmentError
- Malformed ciphertext raises ValueError
- Non-determinism: two encryptions of the same plaintext differ

Requirements: 1.3, 12.1
"""

import base64
import os
import secrets

import pytest

from backend.utils.token_encryption import decrypt_token, encrypt_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_key() -> str:
    """Return a valid base64-encoded 32-byte key."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set a fresh valid TOKEN_ENCRYPTION_KEY for every test."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _make_key())


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

def test_round_trip_simple():
    """decrypt_token(encrypt_token(x)) == x for a simple string."""
    plaintext = "my-oauth-access-token"
    assert decrypt_token(encrypt_token(plaintext)) == plaintext


def test_round_trip_empty_string():
    """Round-trip works for an empty string."""
    assert decrypt_token(encrypt_token("")) == ""


def test_round_trip_unicode():
    """Round-trip preserves unicode characters."""
    plaintext = "tëst-tökën-🔑"
    assert decrypt_token(encrypt_token(plaintext)) == plaintext


def test_round_trip_long_token():
    """Round-trip works for a long token string."""
    plaintext = "a" * 2048
    assert decrypt_token(encrypt_token(plaintext)) == plaintext


# ---------------------------------------------------------------------------
# Ciphertext differs from plaintext
# ---------------------------------------------------------------------------

def test_ciphertext_differs_from_plaintext():
    """The encrypted output must not equal the original plaintext."""
    plaintext = "super-secret-refresh-token"
    ciphertext = encrypt_token(plaintext)
    assert ciphertext != plaintext


def test_ciphertext_is_base64():
    """The encrypted output must be valid base64url."""
    ciphertext = encrypt_token("some-token")
    # Should not raise
    base64.urlsafe_b64decode(ciphertext)


# ---------------------------------------------------------------------------
# Non-determinism
# ---------------------------------------------------------------------------

def test_two_encryptions_differ():
    """Two calls with the same plaintext must produce different ciphertexts (random nonce)."""
    plaintext = "same-token"
    ct1 = encrypt_token(plaintext)
    ct2 = encrypt_token(plaintext)
    assert ct1 != ct2


# ---------------------------------------------------------------------------
# Wrong key raises ValueError
# ---------------------------------------------------------------------------

def test_wrong_key_raises(monkeypatch):
    """Decrypting with a different key must raise ValueError."""
    plaintext = "token-to-protect"
    ciphertext = encrypt_token(plaintext)

    # Switch to a different key
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _make_key())

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_token(ciphertext)


# ---------------------------------------------------------------------------
# Missing key raises EnvironmentError
# ---------------------------------------------------------------------------

def test_missing_key_encrypt_raises(monkeypatch):
    """encrypt_token must raise EnvironmentError when TOKEN_ENCRYPTION_KEY is unset."""
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="TOKEN_ENCRYPTION_KEY"):
        encrypt_token("some-token")


def test_missing_key_decrypt_raises(monkeypatch):
    """decrypt_token must raise EnvironmentError when TOKEN_ENCRYPTION_KEY is unset."""
    ciphertext = encrypt_token("some-token")
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="TOKEN_ENCRYPTION_KEY"):
        decrypt_token(ciphertext)


# ---------------------------------------------------------------------------
# Malformed / tampered ciphertext
# ---------------------------------------------------------------------------

def test_tampered_ciphertext_raises():
    """Flipping a byte in the ciphertext must cause decryption to fail."""
    ciphertext = encrypt_token("important-token")
    blob = bytearray(base64.urlsafe_b64decode(ciphertext))
    # Flip the last byte (part of the GCM authentication tag)
    blob[-1] ^= 0xFF
    tampered = base64.urlsafe_b64encode(bytes(blob)).decode()
    with pytest.raises(ValueError):
        decrypt_token(tampered)


def test_invalid_base64_raises():
    """Passing non-base64 data to decrypt_token must raise ValueError."""
    with pytest.raises(ValueError):
        decrypt_token("not-valid-base64!!!")


def test_too_short_ciphertext_raises():
    """A blob shorter than the nonce size must raise ValueError."""
    short = base64.urlsafe_b64encode(b"short").decode()
    with pytest.raises(ValueError):
        decrypt_token(short)


# ---------------------------------------------------------------------------
# Invalid key format
# ---------------------------------------------------------------------------

def test_key_wrong_length_raises(monkeypatch):
    """A key that decodes to != 32 bytes must raise ValueError."""
    # 16-byte key (AES-128, not AES-256)
    bad_key = base64.b64encode(secrets.token_bytes(16)).decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", bad_key)
    with pytest.raises(ValueError, match="32 bytes"):
        encrypt_token("token")


def test_key_not_base64_raises(monkeypatch):
    """A key that is not valid base64 must raise ValueError."""
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "!!!not-base64!!!")
    with pytest.raises(ValueError, match="base64"):
        encrypt_token("token")
