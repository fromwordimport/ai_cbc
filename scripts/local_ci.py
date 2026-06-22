#!/usr/bin/env python3
"""Local CI/CD gate runner for AI_CBC."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR_DEFAULT = REPO_ROOT / "local-ci-reports"

STAGES = ["preflight", "lint", "test", "redteam", "frontend", "security", "k8s", "docker", "trivy"]
FAST_STAGES = ["preflight", "lint", "test", "redteam", "frontend", "security"]


@dataclass
class StageResult:
    name: str
    success: bool
    duration: float
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    report_files: list[Path] = field(default_factory=list)


class LocalCI:
    def __init__(self, report_dir: Path, verbose: bool = False):
        self.report_dir = report_dir
        self.verbose = verbose
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def require_uv(self) -> None:
        if shutil.which("uv") is None:
            raise RuntimeError("uv is required. Install from https://docs.astral.sh/uv/")

    def require_npm(self) -> None:
        if shutil.which("npm") is None:
            raise RuntimeError("npm is required for frontend stage")

    def require_docker(self) -> None:
        if shutil.which("docker") is None:
            raise RuntimeError("docker is required for docker/trivy stages")

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def run_command(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess[str]:
        self.log(f"$ {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            cwd=cwd or REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_stage(self, name: str) -> StageResult:
        method = getattr(self, f"stage_{name}", None)
        if method is None:
            return StageResult(
                name=name,
                success=False,
                duration=0.0,
                stderr=f"Unknown stage: {name}",
            )
        start = time.time()
        try:
            result = method()
        except Exception as exc:  # noqa: BLE001
            result = StageResult(
                name=name,
                success=False,
                duration=time.time() - start,
                stderr=str(exc),
            )
        return result

    def run(self, stages: list[str], fail_fast: bool = False) -> bool:
        results: list[StageResult] = []
        overall = True
        for name in stages:
            result = self.run_stage(name)
            results.append(result)
            if not result.success:
                overall = False
                if fail_fast:
                    break
        self.print_summary(results)
        return overall

    def print_summary(self, results: list[StageResult]) -> None:
        print("\n" + "=" * 40)
        print("Local CI Summary")
        print("=" * 40)
        for r in results:
            icon = "OK" if r.success else "FAIL"
            extra = f" ({r.returncode})" if not r.success else ""
            print(f"[{icon:4}] {r.name:12} {r.duration:6.1f}s{extra}")
        print("-" * 40)
        print(f"Result: {'PASSED' if all(r.success for r in results) else 'FAILED'}")
        print(f"Report dir: {self.report_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI_CBC CI gates locally")
    parser.add_argument(
        "command",
        choices=["lint", "test", "redteam", "frontend", "security", "k8s", "all"],
        help="which stage to run",
    )
    parser.add_argument("--fast", action="store_true", help="skip docker/trivy/k8s")
    parser.add_argument("--full", action="store_true", help="run all stages including docker/trivy/k8s")
    parser.add_argument("--fail-fast", action="store_true", help="stop on first failure")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose output")
    parser.add_argument("--report-dir", type=Path, default=REPORTS_DIR_DEFAULT)
    parser.add_argument("--skip-trivy", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-k8s", action="store_true")
    parser.add_argument("--skip-pip-audit", action="store_true")
    parser.add_argument("--skip-redteam", action="store_true")
    parser.add_argument("--skip-secrets", action="store_true")
    args = parser.parse_args()

    LocalCI(report_dir=args.report_dir, verbose=args.verbose).require_uv()

    if args.command == "all":
        stages = FAST_STAGES.copy()
        if args.full:
            stages.extend(["docker", "trivy", "k8s"])
    else:
        stages = [args.command]

    skip_map = {
        "trivy": args.skip_trivy,
        "test": args.skip_tests,
        "frontend": args.skip_frontend,
        "k8s": args.skip_k8s,
        "security": args.skip_pip_audit,
        "redteam": args.skip_redteam,
        "preflight": args.skip_secrets,
    }
    stages = [s for s in stages if not skip_map.get(s, False)]

    ci = LocalCI(report_dir=args.report_dir, verbose=args.verbose)
    ok = ci.run(stages, fail_fast=args.fail_fast)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
