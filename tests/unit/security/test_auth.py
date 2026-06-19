"""Tests for frontend authentication and combined auth/RBAC behavior."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from aicbc.api.middleware.rbac import RBACMiddleware
from aicbc.api.routes import auth
from aicbc.config.settings import Settings
from aicbc.core.security.jwt import JWTError, create_access_token, decode_access_token
from aicbc.core.security.password import hash_password


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        DEBUG=False,
        SECRET_KEY="a-very-secret-32-character-key!!",
        FRONTEND_RESEARCHER_PASSWORD_HASH=hash_password("researcher-pass"),
        FRONTEND_ADMIN_PASSWORD_HASH=hash_password("admin-pass"),
        ACCESS_TOKEN_EXPIRE_MINUTES=60,
    )


@pytest.fixture
def client(auth_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("aicbc.api.routes.auth.get_settings", lambda: auth_settings)
    monkeypatch.setattr("aicbc.core.security.jwt.get_settings", lambda: auth_settings)

    app = FastAPI()
    app.state.debug = False
    app.include_router(auth.router, prefix="/api/v1")

    @app.get("/api/v1/studies")
    def list_studies():
        return {"ok": True}

    @app.post("/api/v1/studies")
    def create_study():
        return {"ok": True}

    @app.delete("/api/v1/studies/{study_id}")
    def delete_study(study_id: str):
        return {"deleted": study_id}

    class TestAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = decode_access_token(auth_header[7:], settings=auth_settings)
                    request.state.role = payload.role
                except JWTError:
                    return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            return await call_next(request)

    app.add_middleware(TestAuthMiddleware)
    app.add_middleware(RBACMiddleware)
    return TestClient(app)


def test_login_with_researcher_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "researcher", "password": "researcher-pass"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "researcher"
    assert data["token_type"] == "bearer"
    assert "access_token" in data


def test_login_with_admin_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-pass"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_login_with_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "researcher", "password": "wrong"},
    )
    assert response.status_code == 401


def test_jwt_researcher_can_read_and_create(client: TestClient) -> None:
    token = create_access_token("researcher", "researcher", settings=client.app.state.settings if hasattr(client.app.state, "settings") else None)
    # Use auth_settings from fixture indirectly via decode above; for create we can pass settings manually
    # Simpler: create token without settings override using default get_settings monkeypatched to auth_settings.
    token = create_access_token("researcher", "researcher")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/studies", headers=headers).status_code == 200
    assert client.post("/api/v1/studies", headers=headers).status_code == 200


def test_jwt_researcher_cannot_delete(client: TestClient) -> None:
    token = create_access_token("researcher", "researcher")
    response = client.delete("/api/v1/studies/s1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_jwt_admin_can_delete(client: TestClient) -> None:
    token = create_access_token("admin", "admin")
    response = client.delete("/api/v1/studies/s1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
