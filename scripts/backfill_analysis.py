#!/usr/bin/env python3
"""Backfill missing analysis jobs for studies that already have responses.

Uses only the standard library so it can run in the GitHub Actions runner
without installing extra packages.

Usage:
    python scripts/backfill_analysis.py \
        --host http://localhost:8000 \
        --api-key dev-key-change-in-prod \
        --model-type hb
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


def _request_json(base_url: str, path: str, api_key: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
    url = urljoin(base_url, path)
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
    }
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _list_all_studies(host: str, api_key: str) -> list[dict[str, Any]]:
    """Fetch all studies across pages (API caps page_size at 100)."""
    all_studies: list[dict[str, Any]] = []
    page = 1
    page_size = 100
    while True:
        resp = _request_json(host, f"/api/v1/studies?page={page}&page_size={page_size}", api_key)
        if not isinstance(resp, dict):
            break
        studies = resp.get("studies", [])
        all_studies.extend(studies)
        total = resp.get("total", len(all_studies))
        if len(all_studies) >= total or not studies:
            break
        page += 1
    return all_studies


def backfill(host: str, api_key: str, model_type: str = "hb") -> int:
    studies = _list_all_studies(host, api_key)

    enqueued: list[dict[str, str]] = []

    for study in studies:
        study_id = study.get("study_id")
        if not study_id:
            continue

        # 检查是否已有 response dataset
        try:
            _request_json(host, f"/api/v1/studies/{study_id}/responses/export", api_key)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            print(f"WARN: could not check responses for {study_id}: {exc.code}", file=sys.stderr)
            continue

        # 检查是否已有 completed analysis
        try:
            analyses = _request_json(host, f"/api/v1/studies/{study_id}/analysis", api_key)
        except urllib.error.HTTPError as exc:
            print(f"WARN: could not list analyses for {study_id}: {exc.code}", file=sys.stderr)
            continue

        if any(a.get("status") == "COMPLETED" for a in analyses):
            continue

        # 触发分析
        try:
            resp = _request_json(
                host,
                f"/api/v1/studies/{study_id}/analyze",
                api_key,
                method="POST",
                data={"model_type": model_type},
            )
            enqueued.append({"study_id": study_id, "analysis_id": resp.get("analysis_id", "")})
            print(f"Enqueued {model_type} for {study_id}")
        except urllib.error.HTTPError as exc:
            print(f"WARN: failed to enqueue {study_id}: {exc.code}", file=sys.stderr)

    report = {
        "backfilled_at": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "model_type": model_type,
        "n_enqueued": len(enqueued),
        "jobs": enqueued,
    }
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    report_file = reports_dir / f"backfill-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {report_file}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill AI_CBC analyses")
    parser.add_argument("--host", default=os.environ.get("API_HOST", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    parser.add_argument(
        "--model-type",
        default=os.environ.get("MODEL_TYPE", "hb"),
        choices=["hb", "mnl", "latent_class"],
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: --api-key or API_KEY env required", file=sys.stderr)
        return 1

    return backfill(args.host, args.api_key, args.model_type)


if __name__ == "__main__":
    sys.exit(main())
