"""Authentication routes for frontend users."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from aicbc.config.settings import get_settings
from aicbc.core.security.jwt import create_access_token
from aicbc.core.security.password import verify_password

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    """Frontend login payload."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Successful login response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: Literal["researcher", "admin"]
    expires_in_minutes: int


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate a frontend user and return a JWT access token."""
    settings = get_settings()

    credentials: list[tuple[str, str, str]] = [
        ("admin", settings.frontend_admin_password_hash, "admin"),
        ("researcher", settings.frontend_researcher_password_hash, "researcher"),
    ]

    for expected_username, password_hash, role in credentials:
        if request.username == expected_username and verify_password(
            request.password, password_hash
        ):
            token = create_access_token(subject=request.username, role=role)
            return LoginResponse(
                access_token=token,
                role=role,  # type: ignore[assignment]
                expires_in_minutes=settings.access_token_expire_minutes,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
    )
