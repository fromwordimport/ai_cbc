#!/usr/bin/env python3
"""Export all study data for external warehouse / backup.

Uses only the standard library so it can run in the GitHub Actions runner
without installing extra packages.

Usage:
    python scripts/export_responses.py \
        --host http://localhost:8000 \
        --api-key dev-key-change-in-prod \
        --dest-file reports/export.json

Post to a warehouse:
    python scripts/export_responses.py \
        --host http://localhost:8000 \
        --api-key ... \
        --warehouse-url https://warehouse.example.com/ingest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


def _request_json(base_url: str, path: str, api_key: str) -> Any:
    url = urljoin(base_url, path)
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _in_date_range(study: dict[str, Any], start: datetime | None, end: datetime | None) -> bool:
    created_raw = study.get("created_at") or study.get("study", {}).get("created_at")
    if not created_raw:
        return True
    try:
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if start is not None and created < start:
        return False
    if end is not None:
        # end_date is inclusive
        end_inclusive = end.replace(hour=23, minute=59, second=59, microsecond=999999)
        if created > end_inclusive:
            return False
    return True


def export_all(
    host: str,
    api_key: str,
    dest_file: Path | None,
    warehouse_url: str | None,
    start_date: str | None,
    end_date: str | None,
) -> int:
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)

    studies_resp = _request_json(host, "/api/v1/studies?page=1&page_size=1000", api_key)
    studies = studies_resp.get("studies", []) if isinstance(studies_resp, dict) else []

    exported: list[dict[str, Any]] = []
    skipped = 0

    for study in studies:
        study_id = study.get("study_id")
        if not study_id:
            continue
        if not _in_date_range(study, start_dt, end_dt):
            skipped += 1
            continue
        try:
            data = _request_json(host, f"/api/v1/studies/{study_id}/export", api_key)
            exported.append(data)
        except urllib.error.HTTPError as exc:
            print(f"WARN: failed to export {study_id}: {exc.code}", file=sys.stderr)

    summary = {
        "exported_at": datetime.now(UTC).isoformat(),
        "host": host,
        "date_range": {"start": start_date, "end": end_date},
        "n_studies_total": len(studies),
        "n_studies_skipped": skipped,
        "n_exported": len(exported),
        "studies": exported,
    }

    if dest_file:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {dest_file}")

    if warehouse_url:
        payload = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            warehouse_url,
            data=payload,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"Posted to warehouse: {resp.status}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AI_CBC study data")
    parser.add_argument("--host", default=os.environ.get("API_HOST", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    parser.add_argument("--dest-file", type=Path, default=os.environ.get("EXPORT_DEST_FILE"))
    parser.add_argument("--warehouse-url", default=os.environ.get("DATA_WAREHOUSE_URL", ""))
    parser.add_argument("--start-date", default=os.environ.get("START_DATE", ""))
    parser.add_argument("--end-date", default=os.environ.get("END_DATE", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: --api-key or API_KEY env required", file=sys.stderr)
        return 1

    warehouse_url = args.warehouse_url or None
    dest_file = args.dest_file or None
    if not dest_file and not warehouse_url:
        dest_file = Path("reports/export.json")

    return export_all(
        args.host,
        args.api_key,
        dest_file,
        warehouse_url,
        args.start_date or None,
        args.end_date or None,
    )


if __name__ == "__main__":
    sys.exit(main())
