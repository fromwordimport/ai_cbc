"""Tests for password hashing helpers."""

from __future__ import annotations

import pytest

from aicbc.core.security.password import (
    PasswordError,
    hash_password,
    verify_password,
)


def test_hash_and_verify_round_trip() -> None:
    password = "secret-password-123"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_against_empty_hash() -> None:
    assert verify_password("any-password", "") is False


def test_empty_password_raises() -> None:
    with pytest.raises(PasswordError):
        hash_password("")


def test_verify_invalid_hash_format() -> None:
    assert verify_password("password", "not-a-valid-hash") is False
