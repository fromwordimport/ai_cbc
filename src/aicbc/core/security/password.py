"""Password hashing helpers for frontend login."""

from __future__ import annotations

import bcrypt


class PasswordError(ValueError):
    """Raised for password-related errors."""


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    if not password:
        raise PasswordError("Password cannot be empty")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
