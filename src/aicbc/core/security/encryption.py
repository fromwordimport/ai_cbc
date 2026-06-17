"""API key / secret encryption helpers using AES-256-GCM.

Design:
  - The encryption key is derived from ``SECRET_KEY`` via SHA-256, so a
    32+ character production secret is required.
  - Ciphertext format (base64):
        {12-byte nonce}{16-byte GCM tag}{ciphertext}
  - Encrypted values are prefixed with ``enc:`` so settings can detect them.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENCRYPTION_PREFIX = "enc:"
_NONCE_SIZE = 12
_TAG_SIZE = 16


def _derive_key(secret_key: str) -> bytes:
    """Derive a 32-byte AES key from the application secret key."""
    return hashlib.sha256(secret_key.encode("utf-8")).digest()


def encrypt_value(plaintext: str, secret_key: str) -> str:
    """Encrypt a plaintext value and return a base64 ``enc:...`` string."""
    if not secret_key or len(secret_key) < 32:
        raise ValueError("secret_key must be at least 32 characters for AES-256-GCM")

    key = _derive_key(secret_key)
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # ciphertext includes the 16-byte GCM tag at the end
    combined = nonce + ciphertext
    return f"{_ENCRYPTION_PREFIX}{base64.urlsafe_b64encode(combined).decode('utf-8')}"


def decrypt_value(value: str, secret_key: str) -> str:
    """Decrypt an ``enc:...`` value. Plaintext values are returned unchanged."""
    if not value.startswith(_ENCRYPTION_PREFIX):
        return value

    if not secret_key or len(secret_key) < 32:
        raise ValueError("secret_key must be at least 32 characters for AES-256-GCM")

    combined = base64.urlsafe_b64decode(value[len(_ENCRYPTION_PREFIX) :].encode("utf-8"))
    if len(combined) < _NONCE_SIZE + _TAG_SIZE:
        raise ValueError("invalid encrypted value: too short")

    nonce = combined[:_NONCE_SIZE]
    ciphertext = combined[_NONCE_SIZE:]
    key = _derive_key(secret_key)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def is_encrypted(value: str | None) -> bool:
    """Return True if the value appears to be an ``enc:...`` ciphertext."""
    return isinstance(value, str) and value.startswith(_ENCRYPTION_PREFIX)


def rotate_plaintext_to_ciphertext(plaintext: str, secret_key: str) -> str:
    """Helper to convert a plaintext secret into its encrypted form."""
    return encrypt_value(plaintext, secret_key)
