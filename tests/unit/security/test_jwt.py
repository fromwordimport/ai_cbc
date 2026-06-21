"""Tests for JWT helper functions."""

from __future__ import annotations

import pytest

from aicbc.config.settings import Settings
from aicbc.core.security.jwt import JWTError, create_access_token, decode_access_token


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        debug=True,
        secret_key="a-very-secret-32-character-key!!",
        access_token_expire_minutes=60,
    )


def test_create_and_decode_token(test_settings: Settings) -> None:
    token = create_access_token("user-1", "researcher", settings=test_settings)
    payload = decode_access_token(token, settings=test_settings)
    assert payload.sub == "user-1"
    assert payload.role == "researcher"


def test_decode_invalid_token(test_settings: Settings) -> None:
    with pytest.raises(JWTError):
        decode_access_token("not-a-token", settings=test_settings)


def test_decode_tampered_token(test_settings: Settings) -> None:
    token = create_access_token("user-1", "researcher", settings=test_settings)
    with pytest.raises(JWTError):
        decode_access_token(token + "x", settings=test_settings)
