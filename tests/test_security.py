"""Unit tests for security primitives: encryption and RBAC."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from fastapi import FastAPI
from starlette.testclient import TestClient

from aicbc.api.middleware.rbac import RBACMiddleware
from aicbc.core.security.encryption import (
    decrypt_value,
    encrypt_value,
    is_encrypted,
    rotate_plaintext_to_ciphertext,
)


class TestEncryption:
    """AES-256-GCM encryption helpers."""

    SECRET = "a-very-secret-32-character-key!!"

    def test_round_trip(self) -> None:
        plaintext = "sk-test-secret-key-12345"
        ciphertext = encrypt_value(plaintext, self.SECRET)
        assert ciphertext.startswith("enc:")
        assert decrypt_value(ciphertext, self.SECRET) == plaintext

    def test_plaintext_passes_through(self) -> None:
        assert decrypt_value("plain-value", self.SECRET) == "plain-value"

    def test_is_encrypted_detects_prefix(self) -> None:
        assert is_encrypted("enc:abc")
        assert not is_encrypted("plain")
        assert not is_encrypted(None)

    def test_different_plaintexts_yield_different_ciphertexts(self) -> None:
        a = encrypt_value("secret-a", self.SECRET)
        b = encrypt_value("secret-b", self.SECRET)
        assert a != b

    def test_short_secret_rejected(self) -> None:
        with pytest.raises(ValueError):
            encrypt_value("x", "short")

    def test_rotate_helper(self) -> None:
        ciphertext = rotate_plaintext_to_ciphertext("plaintext", self.SECRET)
        assert is_encrypted(ciphertext)
        assert decrypt_value(ciphertext, self.SECRET) == "plaintext"


class TestRBACMiddleware:
    """Role-based access control middleware."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()
        app.state.debug = False

        @app.get("/api/v1/studies")
        def list_studies():
            return {"ok": True}

        @app.post("/api/v1/studies")
        def create_study():
            return {"ok": True}

        @app.delete("/api/v1/studies/{study_id}")
        def delete_study(study_id: str):
            return {"deleted": study_id}

        @app.get("/api/v1/admin/settings")
        def admin_settings_get():
            return {"ok": True}

        @app.post("/api/v1/admin/settings")
        def admin_settings_post():
            return {"ok": True}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        app.add_middleware(RBACMiddleware)
        return TestClient(app)

    def test_default_role_can_read(self, client: TestClient) -> None:
        response = client.get("/api/v1/studies")
        assert response.status_code == 200

    def test_default_role_cannot_create(self, client: TestClient) -> None:
        response = client.post("/api/v1/studies")
        assert response.status_code == 403

    def test_default_role_cannot_delete(self, client: TestClient) -> None:
        response = client.delete("/api/v1/studies/s1")
        assert response.status_code == 403

    def test_researcher_can_create(self, client: TestClient) -> None:
        response = client.post("/api/v1/studies", headers={"X-User-Role": "researcher"})
        assert response.status_code == 200

    def test_researcher_cannot_delete(self, client: TestClient) -> None:
        response = client.delete("/api/v1/studies/s1", headers={"X-User-Role": "researcher"})
        assert response.status_code == 403

    def test_admin_can_delete(self, client: TestClient) -> None:
        response = client.delete("/api/v1/studies/s1", headers={"X-User-Role": "admin"})
        assert response.status_code == 200

    def test_admin_can_access_admin_endpoints(self, client: TestClient) -> None:
        response = client.post("/api/v1/admin/settings", headers={"X-User-Role": "admin"})
        assert response.status_code == 200

    def test_researcher_cannot_access_admin_endpoints(self, client: TestClient) -> None:
        response = client.post("/api/v1/admin/settings", headers={"X-User-Role": "researcher"})
        assert response.status_code == 403

    def test_public_paths_are_exempt(self, client: TestClient) -> None:
        # No role header; should still be allowed for public paths.
        response = client.get("/health")
        assert response.status_code == 200
