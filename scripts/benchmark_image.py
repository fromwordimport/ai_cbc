"""Measure Docker image size and cold-start time to /health."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Docker image size and startup")
    parser.add_argument("--tag", default="aicbc:benchmark")
    parser.add_argument("--output", default="reports/performance/benchmark_image.json")
    args = parser.parse_args()

    # Build image
    print(f"Building {args.tag} ...")
    start = time.perf_counter()
    run(["docker", "build", "-f", "docker/Dockerfile", "-t", args.tag, "."])
    build_time = time.perf_counter() - start

    # Inspect image size (bytes)
    inspect = run(["docker", "inspect", "-f", "{{.Size}}", args.tag]).strip()
    image_size_bytes = int(inspect)

    # Cold-start test: run container and time to /health
    print("Measuring cold-start time ...")
    container = subprocess.run(
        ["docker", "run", "-d", "-p", "8000:8000", "--name", "aicbc-benchmark", args.tag],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    health_url = "http://localhost:8000/health"
    start = time.perf_counter()
    while time.perf_counter() - start < 120:
        probe = subprocess.run(
            ["curl", "-sf", health_url],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            break
        time.sleep(0.5)
    cold_start = time.perf_counter() - start

    subprocess.run(["docker", "stop", "aicbc-benchmark"], check=False)
    subprocess.run(["docker", "rm", "aicbc-benchmark"], check=False)

    report = {
        "image_tag": args.tag,
        "image_size_bytes": image_size_bytes,
        "image_size_mb": round(image_size_bytes / 1024 / 1024, 2),
        "build_time_seconds": round(build_time, 2),
        "cold_start_seconds": round(cold_start, 2),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
