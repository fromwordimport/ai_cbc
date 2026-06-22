"""Lightweight Locust baseline for nightly performance smoke test.

Usage (from repo root):
    uv pip install locust
    locust -f scripts/locust_baseline.py \
        --host http://localhost:8000 \
        --run-time 2m \
        --users 10 \
        --spawn-rate 2 \
        --headless \
        --csv reports/locust
"""
from __future__ import annotations

from locust import HttpUser, between, task


class AICBCUser(HttpUser):
    """Minimal user hitting health/readiness and core read endpoints."""

    wait_time = between(1, 3)

    @task(3)
    def health(self) -> None:
        self.client.get("/health")

    @task(2)
    def ready(self) -> None:
        self.client.get("/ready")

    @task(1)
    def metrics(self) -> None:
        self.client.get("/metrics")
