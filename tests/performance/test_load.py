"""Locust load tests for AI_CBC API.

Run headless against a local server:

    cd tests/performance
    uv run locust -f test_load.py --host http://localhost:8000 --headless \
        -u 100 -r 10 --run-time 5m --csv aicbc_load

Environment variables:
    AICBC_API_KEY   API key for non-debug deployments (default: dev-key-change-in-prod)
    AICBC_USERNAME  Optional user id header value
    AICBC_ROLE      Optional role header value (default: admin)
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from locust import HttpUser, between, events, task


@events.init.add_listener
def on_locust_init(environment, **_kwargs: Any) -> None:
    """Print configuration summary at startup."""
    api_key = os.environ.get("AICBC_API_KEY", "dev-key-change-in-prod")
    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    print(f"AI_CBC load test configured: host={environment.host}, api_key={masked}")


class AICBCUser(HttpUser):
    """Base user with shared helpers and headers."""

    wait_time = between(1, 3)
    abstract = True

    def on_start(self) -> None:
        """Set common headers for all requests."""
        self.api_key = os.environ.get("AICBC_API_KEY", "dev-key-change-in-prod")
        self.role = os.environ.get("AICBC_ROLE", "admin")
        self.user_id = os.environ.get("AICBC_USERNAME", f"load-tester-{uuid.uuid4().hex[:8]}")
        self.client.headers.update(
            {
                "X-API-Key": self.api_key,
                "X-User-Role": self.role,
                "X-User-Id": self.user_id,
                "Content-Type": "application/json",
            }
        )

    def _unique_study_id(self) -> str:
        """Return a unique study id for this user."""
        return f"load-{self.user_id}-{uuid.uuid4().hex[:8]}"


class StudyManagementUser(AICBCUser):
    """Lightweight read/write operations on studies and questionnaires."""

    weight = 3

    @task(4)
    def list_studies(self) -> None:
        """GET /api/v1/studies"""
        self.client.get("/api/v1/studies", name="GET /studies")

    @task(2)
    def create_and_get_study(self) -> None:
        """Create a study and immediately retrieve it."""
        study_id = self._unique_study_id()
        payload = {
            "study_id": study_id,
            "product_category": "洗碗机",
            "research_goal": "Load test benchmark",
        }
        with self.client.post(
            "/api/v1/studies",
            json=payload,
            name="POST /studies",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 409:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

        self.client.get(f"/api/v1/studies/{study_id}", name="GET /studies/{id}")

    @task(2)
    def generate_questionnaire(self) -> None:
        """Create a study and generate its CBC questionnaire."""
        study_id = self._unique_study_id()
        self.client.post(
            "/api/v1/studies",
            json={
                "study_id": study_id,
                "product_category": "洗碗机",
                "research_goal": "Load test benchmark",
            },
            name="POST /studies (for questionnaire)",
        )
        with self.client.post(
            f"/api/v1/studies/{study_id}/generate",
            name="POST /studies/{id}/generate",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 409:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


class FullPipelineUser(AICBCUser):
    """End-to-end pipeline: study -> questionnaire -> personas -> responses -> analysis."""

    weight = 1
    wait_time = between(5, 10)

    @task
    def run_full_pipeline(self) -> None:
        """Execute the complete research pipeline."""
        study_id = self._unique_study_id()

        # 1. Create study
        self.client.post(
            "/api/v1/studies",
            json={
                "study_id": study_id,
                "product_category": "洗碗机",
                "research_goal": "Load test full pipeline",
            },
            name="POST /studies (pipeline)",
        )

        # 2. Generate questionnaire
        self.client.post(
            f"/api/v1/studies/{study_id}/generate",
            name="POST /studies/{id}/generate (pipeline)",
        )

        # 3. Generate personas (small batch to keep latency reasonable)
        self.client.post(
            "/api/v1/personas/generate",
            json={"study_id": study_id, "count": 3},
            name="POST /personas/generate",
        )

        # 4. Simulate responses with fast rule-based simulator
        self.client.post(
            f"/api/v1/studies/{study_id}/simulate-responses",
            json={
                "persona_ids": [
                    f"persona-{study_id}-001",
                    f"persona-{study_id}-002",
                    f"persona-{study_id}-003",
                ],
                "mode": "rule",
            },
            name="POST /studies/{id}/simulate-responses",
        )

        # 5. Trigger analysis
        with self.client.post(
            f"/api/v1/studies/{study_id}/analyze",
            json={"model_type": "hb", "n_draws": 500, "n_tune": 250},
            name="POST /studies/{id}/analyze",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 201, 202):
                response.success()
            else:
                response.failure(f"Analyze failed: {response.status_code}")

        # 6. Read back results
        self.client.get(
            f"/api/v1/studies/{study_id}/responses",
            name="GET /studies/{id}/responses",
        )


class HealthCheckUser(AICBCUser):
    """Low-cost health and readiness probes."""

    weight = 5
    wait_time = between(1, 2)

    @task(3)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(2)
    def ready(self) -> None:
        self.client.get("/ready", name="GET /ready")

    @task(1)
    def metrics(self) -> None:
        self.client.get("/metrics", name="GET /metrics")
