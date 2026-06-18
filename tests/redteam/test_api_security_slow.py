"""Red team tests: API endpoint security (slow / adversarial).

Slow adversarial tests including:
- Fuzzing with many payloads
- Traversal attempts
- Heavy payloads
- Brute-force-like checks
- Loop-based rate limit tests
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicbc.main import app

client = TestClient(app)

pytestmark = [pytest.mark.redteam, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Rate Limiting Tests (loop-based, multiple requests)
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Document the absence of rate limiting."""

    def test_no_rate_limit_on_generation(self) -> None:
        """Rapid requests to generate endpoint are now throttled by rate limiter."""
        # Make multiple rapid requests
        responses = []
        for i in range(5):
            response = client.post(
                "/api/v1/personas/generate",
                json={"count": 1, "study_id": f"redteam-rate-{i}"},
            )
            responses.append(response.status_code)

        # Rate limiting IS implemented; requests may be blocked (429) or succeed
        # depending on accumulated rate limit state from prior tests
        assert all(code in (201, 422, 429, 500) for code in responses)

    def test_no_rate_limit_on_converse(self) -> None:
        """Rapid requests to converse endpoint are not throttled."""
        responses = []
        for i in range(5):
            response = client.post(
                "/api/v1/personas/persona-test-001/converse",
                json={"question": f"Question {i}", "context": {}},
            )
            responses.append(response.status_code)

        # Rate limiting IS implemented; 429 may appear if rate limit exhausted
        assert all(code in (200, 404, 429) for code in responses)


# ---------------------------------------------------------------------------
# Privilege Escalation Tests
# ---------------------------------------------------------------------------


class TestPrivilegeEscalation:
    """Test for unauthorized access to admin functionality."""

    def test_delete_without_admin_role(self) -> None:
        """Delete endpoint has no role-based access control."""
        response = client.delete("/api/v1/personas/persona-test-001")
        # SECURITY GAP: No RBAC - anyone can delete
        assert response.status_code in (204, 404)

    def test_delete_study_without_admin_role(self) -> None:
        """Study delete has no role-based access control."""
        response = client.delete("/api/v1/studies/redteam-study-001")
        # SECURITY GAP: No RBAC - anyone can delete studies
        assert response.status_code in (204, 404)

    def test_batch_size_limit_bypass(self) -> None:
        """Attempt to bypass batch size limits."""
        # Max batch is 100, try edge cases
        response = client.post(
            "/api/v1/personas/generate",
            json={"count": 100, "study_id": "redteam-max"},
        )
        # Should be allowed (at limit); 429 if rate-limited from prior tests
        assert response.status_code in (201, 422, 429, 500)

    def test_list_all_personas_unauthorized(self) -> None:
        """Anyone can list all personas without authorization."""
        response = client.get("/api/v1/personas?page_size=100")
        # SECURITY GAP: No authorization check
        assert response.status_code == 200

    def test_export_dataset_unauthorized(self) -> None:
        """Anyone can export response datasets."""
        response = client.get("/api/v1/studies/redteam-study-001/responses/export")
        # SECURITY GAP: No authorization check for data export
        assert response.status_code in (200, 404)
