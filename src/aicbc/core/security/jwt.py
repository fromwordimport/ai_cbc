"""JWT helpers for frontend session tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import PyJWTError

from aicbc.config.settings import Settings, get_settings

ALGORITHM = "HS256"


class JWTError(ValueError):
    """Raised when a JWT cannot be decoded or is invalid."""


class TokenPayload:
    """Validated JWT payload for a frontend session."""

    def __init__(self, sub: str, role: str, exp: datetime) -> None:
        self.sub = sub
        self.role = role
        self.exp = exp


def create_access_token(
    subject: str,
    role: str,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token for the frontend."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and validate a JWT access token."""
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except PyJWTError as exc:
        raise JWTError("Invalid or expired token") from exc

    sub = payload.get("sub")
    role = payload.get("role")
    exp_timestamp = payload.get("exp")

    if (
        not isinstance(sub, str)
        or not isinstance(role, str)
        or not isinstance(exp_timestamp, (int, float))
    ):
        raise JWTError("Malformed token payload")

    exp = datetime.fromtimestamp(exp_timestamp, tz=UTC)
    return TokenPayload(sub=sub, role=role, exp=exp)
