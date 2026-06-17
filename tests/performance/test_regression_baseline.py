"""Performance regression test baseline for AI_CBC API.

Extends the Locust load tests with assertion-based performance gating.
Run with pytest after a Locust run to validate against KPI thresholds.

Usage:
    # 1. Run Locust headless to generate CSV stats
    cd tests/performance
    uv run locust -f test_load.py --host http://localhost:8000 --headless \
        -u 100 -r 10 --run-time 5m --csv aicbc_load

    # 2. Run regression assertions against the CSV output
    uv run pytest tests/performance/test_regression_baseline.py -v
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# KPI Thresholds (performance gates)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceGate:
    """A single performance gate with P50/P95/P99 thresholds."""

    endpoint: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_error_rate: float = 0.001  # 0.1%
    min_rps: float | None = None


# Baseline thresholds derived from staging target requirements.
# Adjust after PERF-1 production-stack benchmarking.
PERFORMANCE_GATES: list[PerformanceGate] = [
    PerformanceGate(
        endpoint="GET /health",
        p50_ms=200.0,
        p95_ms=500.0,
        p99_ms=1000.0,
        min_rps=50.0,
    ),
    PerformanceGate(
        endpoint="GET /ready",
        p50_ms=200.0,
        p95_ms=500.0,
        p99_ms=1000.0,
        min_rps=50.0,
    ),
    PerformanceGate(
        endpoint="GET /studies",
        p50_ms=500.0,
        p95_ms=2000.0,
        p99_ms=5000.0,
        min_rps=20.0,
    ),
    PerformanceGate(
        endpoint="POST /studies",
        p50_ms=500.0,
        p95_ms=2000.0,
        p99_ms=5000.0,
        min_rps=10.0,
    ),
    PerformanceGate(
        endpoint="POST /studies/{id}/generate",
        p50_ms=1000.0,
        p95_ms=5000.0,
        p99_ms=10000.0,
        min_rps=5.0,
    ),
    PerformanceGate(
        endpoint="POST /personas/generate",
        p50_ms=2000.0,
        p95_ms=10000.0,
        p99_ms=30000.0,
        min_rps=2.0,
    ),
    PerformanceGate(
        endpoint="POST /studies/{id}/simulate-responses",
        p50_ms=1000.0,
        p95_ms=5000.0,
        p99_ms=10000.0,
        min_rps=5.0,
    ),
    PerformanceGate(
        endpoint="POST /studies/{id}/analyze",
        p50_ms=2000.0,
        p95_ms=30000.0,
        p99_ms=60000.0,
        min_rps=1.0,
    ),
]

# Concurrency tiers for load test scenarios
LOAD_SCENARIOS: dict[str, dict[str, Any]] = {
    "light": {"users": 10, "spawn_rate": 2, "run_time": "3m"},
    "medium": {"users": 100, "spawn_rate": 10, "run_time": "5m"},
    "heavy": {"users": 500, "spawn_rate": 50, "run_time": "10m"},
    "stress": {"users": 1000, "spawn_rate": 100, "run_time": "15m"},
}

# Resource degradation thresholds (for Prometheus-based assertions)
RESOURCE_GATES: dict[str, dict[str, float]] = {
    "cpu": {"p50_percent": 50.0, "p95_percent": 80.0, "p99_percent": 95.0},
    "memory": {"p50_percent": 60.0, "p95_percent": 80.0, "p99_percent": 90.0},
}


# ---------------------------------------------------------------------------
# CSV parser helpers
# ---------------------------------------------------------------------------


def _find_stats_csv() -> Path | None:
    """Locate the most recent Locust stats CSV in the performance directory."""
    perf_dir = Path(__file__).parent
    candidates = list(perf_dir.glob("*_stats.csv"))
    if not candidates:
        return None
    # Most recently modified
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _load_stats(csv_path: Path) -> dict[str, dict[str, Any]]:
    """Parse Locust stats CSV into a dict keyed by endpoint name."""
    stats: dict[str, dict[str, Any]] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", row.get("name", "")).strip()
            if not name or name == "Aggregated":
                continue
            stats[name] = {
                "requests": int(row.get("# Requests", row.get("request_count", 0))),
                "failures": int(row.get("# Fails", row.get("failure_count", 0))),
                "p50_ms": float(row.get("50%", row.get("median_response_time", 0))),
                "p95_ms": float(row.get("95%", row.get("ninety_fifth_percentile", 0))),
                "p99_ms": float(row.get("99%", row.get("ninety_ninth_percentile", 0))),
                "avg_ms": float(row.get("Average (ms)", row.get("average_response_time", 0))),
                "rps": float(row.get("Requests/s", row.get("current_rps", 0))),
            }
    return stats


def _load_distribution_csv() -> dict[str, dict[str, float]] | None:
    """Load Locust distribution CSV if available (for percentile verification)."""
    perf_dir = Path(__file__).parent
    candidates = list(perf_dir.glob("*_distribution.csv"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    dist: dict[str, dict[str, float]] = {}
    with candidates[0].open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            if not name or name == "Aggregated":
                continue
            dist[name] = {
                k: float(v) for k, v in row.items() if k not in ("Name", "# Requests") and v
            }
    return dist


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def locust_stats() -> dict[str, dict[str, Any]]:
    """Load the most recent Locust stats CSV, or skip if none found."""
    csv_path = _find_stats_csv()
    if csv_path is None:
        pytest.skip(
            "No Locust stats CSV found. Run locust first: "
            "uv run locust -f test_load.py --host http://localhost:8000 "
            "--headless -u 100 -r 10 --run-time 5m --csv aicbc_load"
        )
    return _load_stats(csv_path)


@pytest.fixture(scope="session")
def locust_distribution() -> dict[str, dict[str, float]] | None:
    """Load distribution CSV if available."""
    return _load_distribution_csv()


@pytest.fixture(scope="session")
def load_tier() -> str:
    """Determine which load tier was run from environment or default to medium."""
    return os.environ.get("PERF_LOAD_TIER", "medium")


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


class TestPerformanceRegression:
    """Assert that API response times and error rates stay within baseline gates."""

    @pytest.mark.parametrize("gate", PERFORMANCE_GATES, ids=lambda g: g.endpoint)
    def test_response_time_percentiles(
        self,
        locust_stats: dict[str, dict[str, Any]],
        gate: PerformanceGate,
    ) -> None:
        """P50, P95, and P99 must be below the defined thresholds."""
        stats = locust_stats.get(gate.endpoint)
        if stats is None:
            pytest.skip(f"No data for endpoint '{gate.endpoint}' in stats CSV")

        assert stats["p50_ms"] <= gate.p50_ms, (
            f"{gate.endpoint} P50 {stats['p50_ms']:.1f}ms exceeds threshold {gate.p50_ms}ms"
        )
        assert stats["p95_ms"] <= gate.p95_ms, (
            f"{gate.endpoint} P95 {stats['p95_ms']:.1f}ms exceeds threshold {gate.p95_ms}ms"
        )
        assert stats["p99_ms"] <= gate.p99_ms, (
            f"{gate.endpoint} P99 {stats['p99_ms']:.1f}ms exceeds threshold {gate.p99_ms}ms"
        )

    @pytest.mark.parametrize("gate", PERFORMANCE_GATES, ids=lambda g: g.endpoint)
    def test_error_rate(
        self,
        locust_stats: dict[str, dict[str, Any]],
        gate: PerformanceGate,
    ) -> None:
        """Error rate must be below the defined threshold (default 0.1%)."""
        stats = locust_stats.get(gate.endpoint)
        if stats is None:
            pytest.skip(f"No data for endpoint '{gate.endpoint}' in stats CSV")

        total = stats["requests"] + stats["failures"]
        if total == 0:
            pytest.skip("No requests recorded")

        error_rate = stats["failures"] / total
        assert error_rate <= gate.max_error_rate, (
            f"{gate.endpoint} error rate {error_rate:.4f} exceeds threshold {gate.max_error_rate}"
        )

    @pytest.mark.parametrize(
        "gate",
        [g for g in PERFORMANCE_GATES if g.min_rps is not None],
        ids=lambda g: g.endpoint,
    )
    def test_throughput(
        self,
        locust_stats: dict[str, dict[str, Any]],
        gate: PerformanceGate,
    ) -> None:
        """RPS must meet the minimum throughput gate."""
        stats = locust_stats.get(gate.endpoint)
        if stats is None:
            pytest.skip(f"No data for endpoint '{gate.endpoint}' in stats CSV")

        assert stats["rps"] >= gate.min_rps, (
            f"{gate.endpoint} RPS {stats['rps']:.2f} below minimum {gate.min_rps}"
        )

    def test_overall_error_rate(self, locust_stats: dict[str, dict[str, Any]]) -> None:
        """Aggregated error rate across all endpoints must be < 0.1%."""
        total_requests = sum(s["requests"] for s in locust_stats.values())
        total_failures = sum(s["failures"] for s in locust_stats.values())
        if total_requests == 0:
            pytest.skip("No requests recorded")

        overall_error_rate = total_failures / total_requests
        assert overall_error_rate <= 0.001, (
            f"Overall error rate {overall_error_rate:.4f} exceeds 0.1%"
        )

    def test_no_unexpected_endpoints(self, locust_stats: dict[str, dict[str, Any]]) -> None:
        """Warn if endpoints appear in stats that are not covered by gates."""
        gated = {g.endpoint for g in PERFORMANCE_GATES}
        unexpected = set(locust_stats.keys()) - gated
        if unexpected:
            pytest.warns(
                UserWarning,
                f"Endpoints without performance gates: {unexpected}. "
                "Consider adding gates or excluding from load test.",
            )


class TestLoadScenarioAdherence:
    """Verify that the load test was run with expected concurrency parameters."""

    def test_minimum_request_volume(
        self, locust_stats: dict[str, dict[str, Any]], load_tier: str
    ) -> None:
        """Ensure enough total requests were made for statistically meaningful results."""
        min_requests = {
            "light": 500,
            "medium": 5000,
            "heavy": 25000,
            "stress": 50000,
        }.get(load_tier, 5000)

        total_requests = sum(s["requests"] for s in locust_stats.values())
        assert total_requests >= min_requests, (
            f"Total requests {total_requests} below minimum {min_requests} for tier '{load_tier}'"
        )

    def test_all_gated_endpoints_present(self, locust_stats: dict[str, dict[str, Any]]) -> None:
        """Every gate should have at least some data (may be skipped if endpoint not hit)."""
        missing = [g.endpoint for g in PERFORMANCE_GATES if g.endpoint not in locust_stats]
        if missing:
            pytest.warns(
                UserWarning,
                f"Gated endpoints with no data: {missing}. "
                "Load test may not have exercised all critical paths.",
            )
