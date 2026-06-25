"""Compare benchmark result against baseline and fail on regression."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    current_path = Path(sys.argv[1])
    baseline_path = Path(sys.argv[2])
    qps_threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.15
    p95_threshold = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30

    current = json.loads(current_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    baseline_by_endpoint = {b["endpoint"]: b for b in baseline}
    failed = False
    for c in current:
        name = c["endpoint"]
        b = baseline_by_endpoint.get(name)
        if b is None:
            continue
        if b.get("rps", 0) > 0:
            qps_drop = (b["rps"] - c["rps"]) / b["rps"]
            if qps_drop > qps_threshold:
                print(f"FAIL {name}: QPS dropped {qps_drop:.1%} (threshold {qps_threshold:.1%})")
                failed = True
        if c.get("p95_ms", 0) > 0 and b.get("p95_ms", 0) > 0:
            p95_increase = (c["p95_ms"] - b["p95_ms"]) / b["p95_ms"]
            if p95_increase > p95_threshold:
                print(f"FAIL {name}: P95 increased {p95_increase:.1%} (threshold {p95_threshold:.1%})")
                failed = True

    if failed:
        sys.exit(1)
    print("Baseline comparison passed")


if __name__ == "__main__":
    main()
