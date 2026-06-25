"""API benchmark script for AI_CBC."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class BenchmarkResult:
    endpoint: str
    status_codes: list[int] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.latencies) + len(self.errors)

    @property
    def rps(self) -> float:
        if not self.latencies:
            return 0.0
        duration = max(self.latencies) - min(self.latencies) if len(self.latencies) > 1 else self.latencies[0]
        return len(self.latencies) / max(duration, 0.001)

    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        k = (len(sorted_lat) - 1) * p / 100
        f = int(k)
        c = min(f + 1, len(sorted_lat) - 1)
        return sorted_lat[f] + (k - f) * (sorted_lat[c] - sorted_lat[f])


async def _worker(
    client: httpx.AsyncClient,
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    requests: int,
    results: BenchmarkResult,
) -> None:
    for _ in range(requests):
        start = time.perf_counter()
        try:
            if method == "GET":
                response = await client.get(f"{base_url}{path}", timeout=30.0)
            else:
                response = await client.post(f"{base_url}{path}", json=body, timeout=30.0)
            results.status_codes.append(response.status_code)
            results.latencies.append(time.perf_counter() - start)
        except Exception as exc:
            results.errors.append(str(exc))


async def run_benchmark(
    base_url: str,
    endpoint: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    concurrency: int,
    requests_per_worker: int,
) -> BenchmarkResult:
    results = BenchmarkResult(endpoint=endpoint)
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=concurrency * 2)) as client:
        await asyncio.gather(
            *[
                _worker(client, base_url, method, path, body, requests_per_worker, results)
                for _ in range(concurrency)
            ]
        )
    return results


def print_report(results: list[BenchmarkResult]) -> None:
    print(f"{'Endpoint':<30} {'Total':>8} {'OK':>8} {'Err':>8} {'RPS':>10} {'P50(ms)':>10} {'P95(ms)':>10} {'P99(ms)':>10}")
    for r in results:
        ok = sum(1 for c in r.status_codes if 200 <= c < 300)
        print(
            f"{r.endpoint:<30} {r.total:>8} {ok:>8} {len(r.errors):>8} "
            f"{r.rps:>10.2f} {r.percentile(50) * 1000:>10.1f} {r.percentile(95) * 1000:>10.1f} {r.percentile(99) * 1000:>10.1f}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark AI_CBC API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--duration", type=int, default=60, help="Duration per scenario in seconds")
    parser.add_argument("--output", default="reports/performance/benchmark_api.json", help="Output JSON path")
    args = parser.parse_args()

    scenarios = [
        ("health", "GET", "/health", None, 50),
        ("ready", "GET", "/ready", None, 20),
        ("dashboard_summary", "GET", "/dashboard/summary", None, 50),
        ("studies", "GET", "/api/v1/studies", None, 20),
        ("personas", "GET", "/api/v1/personas", None, 20),
    ]

    results: list[BenchmarkResult] = []
    for name, method, path, body, concurrency in scenarios:
        requests_per_worker = max(1, args.duration * concurrency // 10)
        print(f"Running {name}: concurrency={concurrency}, total_requests={requests_per_worker * concurrency}")
        result = await run_benchmark(args.base_url, name, method, path, body, concurrency, requests_per_worker)
        results.append(result)

    print_report(results)

    import json
    from pathlib import Path

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            [
                {
                    "endpoint": r.endpoint,
                    "total": r.total,
                    "errors": len(r.errors),
                    "rps": r.rps,
                    "p50_ms": r.percentile(50) * 1000,
                    "p95_ms": r.percentile(95) * 1000,
                    "p99_ms": r.percentile(99) * 1000,
                }
                for r in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
