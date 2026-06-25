"""Profile a single endpoint with py-spy and output a flamegraph."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile an endpoint with py-spy")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--endpoint", default="/dashboard/summary")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--output", default="reports/performance/flamegraph.svg")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Find uvicorn process
    proc = subprocess.run(
        ["pgrep", "-f", "uvicorn src.aicbc.main:app"],
        capture_output=True,
        text=True,
        check=False,
    )
    pid = proc.stdout.strip().splitlines()[0] if proc.returncode == 0 else None
    if not pid:
        print("Could not find uvicorn process; is the server running?", file=sys.stderr)
        sys.exit(1)

    # Start py-spy record
    spy_cmd = [
        "py-spy",
        "record",
        "-p",
        pid,
        "-o",
        str(output_path),
        "-d",
        str(args.duration),
        "--rate",
        "100",
    ]
    spy_proc = subprocess.Popen(spy_cmd)

    # Generate load concurrently
    start = time.perf_counter()
    with httpx.Client() as client:
        while time.perf_counter() - start < args.duration:
            try:
                client.get(f"{args.base_url}{args.endpoint}", timeout=10.0)
            except Exception:
                pass
            time.sleep(0.1)

    spy_proc.wait()
    print(f"Flamegraph saved to {output_path}")


if __name__ == "__main__":
    main()
