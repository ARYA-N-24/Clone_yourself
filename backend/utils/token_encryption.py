"""
AES-256-GCM token encryption/decryption helpers.

The encryption key is loaded from the TOKEN_ENCRYPTION_KEY environment variable,
which must be a base64-encoded 32-byte (256-bit) key. The key is NEVER hardcoded.

Usage:
    ciphertext = encrypt_token("my-oauth-token")
    plaintext  = decrypt_token(ciphertext)
    assert plaintext == "my-oauth-token"
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# AES-256-GCM nonce size (96 bits / 12 bytes is the recommended size)
_NONCE_SIZE = 12


def _load_key() -> bytes:
    """
    Load and validate the AES-256 encryption key from the environment.

    Returns:
        The raw 32-byte key.

    Raises:
        EnvironmentError: If TOKEN_ENCRYPTION_KEY is not set.
        ValueError: If the decoded key is not exactly 32 bytes.
    """
    raw = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not raw:
        raise EnvironmentError(
            "TOKEN_ENCRYPTION_KEY environment variable is not set. "
            "Generate a key with: python -c \"import secrets, base64; "
            "print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY is not valid base64."
        ) from exc

    if len(key) != 32:
        raise ValueError(
            f"TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes for AES-256, "
            f"got {len(key)} bytes."
        )
    return key


def encrypt_token(plaintext: str) -> str:
    """
    Encrypt a plaintext string using AES-256-GCM.

    A fresh random 12-byte nonce is generated for every call, so two calls
    with the same plaintext produce different ciphertexts (non-deterministic).
    The nonce is prepended to the ciphertext before base64-encoding so that
    decrypt_token can recover it.

    Args:
        plaintext: The string to encrypt (e.g. an OAuth access or refresh token).

    Returns:
        A base64url-encoded string of the form ``nonce || ciphertext+tag``.

    Raises:
        EnvironmentError: If TOKEN_ENCRYPTION_KEY is not set.
        ValueError: If the key is invalid.
    """
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Prepend nonce so decrypt_token can extract it
    blob = nonce + ciphertext_with_tag
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string produced by encrypt_token.

    Args:
        ciphertext: A base64url-encoded string previously returned by encrypt_token.

    Returns:
        The original plaintext string.

    Raises:
        EnvironmentError: If TOKEN_ENCRYPTION_KEY is not set.
        ValueError: If the key is invalid, the ciphertext is malformed, or
                    decryption fails (wrong key, tampered data, truncated blob).
    """
    key = _load_key()
    try:
        blob = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    except Exception as exc:
        raise ValueError("Ciphertext is not valid base64url.") from exc

    if len(blob) <= _NONCE_SIZE:
        raise ValueError(
            f"Ciphertext blob is too short: expected more than {_NONCE_SIZE} bytes, "
            f"got {len(blob)}."
        )

    nonce = blob[:_NONCE_SIZE]
    ciphertext_with_tag = blob[_NONCE_SIZE:]

    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except InvalidTag as exc:
        raise ValueError(
            "Decryption failed: authentication tag mismatch. "
            "The ciphertext may have been tampered with or encrypted with a different key."
        ) from exc

    return plaintext_bytes.decode("utf-8")
