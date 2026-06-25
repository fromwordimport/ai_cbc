"""Celery worker benchmark for analysis tasks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import httpx


def poll_task_status(base_url: str, analysis_id: str, timeout: int = 600) -> dict:
    start = time.perf_counter()
    with httpx.Client() as client:
        while time.perf_counter() - start < timeout:
            response = client.get(f"{base_url}/api/v1/analysis/{analysis_id}/status", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            if data.get("status") in ("COMPLETED", "FAILED", "TIMED_OUT"):
                return {"final": data, "elapsed": time.perf_counter() - start}
            time.sleep(2.0)
    raise TimeoutError(f"Task {analysis_id} did not complete within {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Celery analysis worker")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--study-id", default="benchmark-worker-study")
    parser.add_argument("--output", default="reports/performance/benchmark_worker.json")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    report: dict = {
        "started_at": datetime.now(UTC).isoformat(),
        "study_id": args.study_id,
    }

    with httpx.Client() as client:
        # 1. Create study
        client.post(
            f"{base}/api/v1/studies",
            json={
                "study_id": args.study_id,
                "product_category": "dishwasher",
                "research_goal": "benchmark",
            },
            timeout=10.0,
        )

        # 2. Upload a minimal dataset (150 respondents x 12 choice sets x 3 alts)
        n_respondents = 150
        n_choice_sets = 12
        n_alternatives = 3
        choice_records = []
        for r in range(n_respondents):
            for cs in range(n_choice_sets):
                choice_records.append(
                    {
                        "respondent_id": f"resp-{r:03d}",
                        "choice_set_id": cs,
                        "selected_alternative": r % n_alternatives,
                        "available_alternatives": list(range(n_alternatives)),
                    }
                )

        dataset_payload = {
            "study_id": args.study_id,
            "n_respondents": n_respondents,
            "n_choice_sets": n_choice_sets,
            "n_alternatives": n_alternatives,
            "choice_records": choice_records,
        }
        client.post(f"{base}/api/v1/studies/{args.study_id}/dataset", json=dataset_payload, timeout=30.0)

        # 3. Trigger HB analysis
        analysis_id = f"{args.study_id}-hb"
        response = client.post(
            f"{base}/api/v1/analysis",
            json={
                "study_id": args.study_id,
                "analysis_id": analysis_id,
                "model_type": "hb",
                "config": {"n_draws": 500, "n_tune": 500, "n_chains": 2, "n_cores": 1},
            },
            timeout=10.0,
        )
        response.raise_for_status()
        queued_at = time.perf_counter()

        # 4. Poll to completion
        result = poll_task_status(base, analysis_id)
        report["queued_at"] = queued_at
        report["total_elapsed_seconds"] = result["elapsed"]
        report["status"] = result["final"].get("status")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
