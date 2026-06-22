#!/usr/bin/env python3
"""Local CI/CD gate runner for AI_CBC."""

from __future__ import annotations

import argparse
import re
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

    def stage_dir(self, name: str) -> Path:
        d = self.report_dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_report(self, stage: str, filename: str, content: str) -> Path:
        d = self.stage_dir(stage)
        p = d / filename
        p.write_text(content, encoding="utf-8")
        return p

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

    def stage_preflight(self) -> StageResult:
        start = time.time()
        errors: list[str] = []
        report_files: list[Path] = []

        # branch naming
        branch_res = self.run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch_res.stdout.strip()
        if not re.match(r"^(master|release/.*|hotfix/.*|feature/.*|worktree/.*|worktree-.*)$", branch):
            errors.append(f"branch naming violation: {branch}")

        # commit message
        commit_res = self.run_command(["git", "log", "--format=%s", "-n", "1", "HEAD"])
        message = commit_res.stdout.strip()
        cm_res = self.run_command(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_commit_msg.py"), "--from-git"]
        )
        if cm_res.returncode != 0:
            errors.append("commit message format violation")

        # secrets scan
        if shutil.which("trufflehog"):
            out_path = self.write_report("preflight", "trufflehog.json", "")
            res = self.run_command(
                ["trufflehog", "git", "file://.", "--only-verified", "--json"],
                timeout=120,
            )
            out_path.write_text(res.stdout, encoding="utf-8")
            report_files.append(out_path)
            if res.returncode != 0:
                errors.append("TruffleHog found verified secrets")
        else:
            errors.append("trufflehog not installed; skipping secrets scan")

        duration = time.time() - start
        return StageResult(
            name="preflight",
            success=len(errors) == 0,
            duration=duration,
            stdout=f"branch: {branch}\nmessage: {message}",
            stderr="\n".join(errors),
            report_files=report_files,
        )

    def stage_lint(self) -> StageResult:
        start = time.time()
        errors: list[str] = []
        report_files: list[Path] = []
        stage_dir = self.stage_dir("lint")

        res = self.run_command(["uv", "run", "ruff", "check", "src/", "--output-format=github"])
        if res.returncode != 0:
            errors.append("ruff check failed")

        res = self.run_command(["uv", "run", "ruff", "format", "--check", "src/"])
        if res.returncode != 0:
            errors.append("ruff format check failed")

        res = self.run_command(["uv", "run", "mypy", "src/", "--ignore-missing-imports"])
        mypy_path = stage_dir / "mypy-report.txt"
        mypy_path.write_text(res.stdout + res.stderr, encoding="utf-8")
        report_files.append(mypy_path)
        if res.returncode != 0:
            errors.append("mypy found issues (non-blocking in CI, but reported locally)")

        bandit_path = stage_dir / "bandit-report.json"
        res = self.run_command(
            ["uv", "run", "bandit", "-r", "src/", "-f", "json", "-o", str(bandit_path), "--severity-level", "high"]
        )
        report_files.append(bandit_path)
        if res.returncode != 0:
            errors.append("bandit found HIGH severity issues")

        duration = time.time() - start
        return StageResult(
            name="lint",
            success=len(errors) == 0,
            duration=duration,
            stdout="",
            stderr="\n".join(errors),
            report_files=report_files,
        )

    def stage_test(self) -> StageResult:
        start = time.time()
        stage_dir = self.stage_dir("test")
        junit_path = stage_dir / "fast.xml"
        coverage_xml = stage_dir / "coverage.xml"

        cmd = [
            "uv", "run", "pytest", "tests/",
            "-m", "(unit or integration) and not slow and not redteam and not performance and not smoke",
            "--timeout=120",
            "--cov=src",
            "--cov-report=xml:" + str(coverage_xml),
            "--cov-report=html:" + str(stage_dir / "htmlcov"),
            "--cov-fail-under=60",
            f"--junitxml={junit_path}",
        ]
        res = self.run_command(cmd, timeout=600)

        return StageResult(
            name="test",
            success=res.returncode == 0,
            duration=time.time() - start,
            stdout=res.stdout[-2000:] if len(res.stdout) > 2000 else res.stdout,
            stderr=res.stderr[-2000:] if len(res.stderr) > 2000 else res.stderr,
            report_files=[junit_path, coverage_xml],
        )

    def stage_redteam(self) -> StageResult:
        start = time.time()
        stage_dir = self.stage_dir("redteam")
        junit_path = stage_dir / "redteam-fast.xml"

        cmd = [
            "uv", "run", "pytest", "tests/redteam/",
            "-v",
            "-m", "security and not slow",
            "--timeout=120",
            f"--junitxml={junit_path}",
        ]
        res = self.run_command(cmd, timeout=600)

        if res.returncode == 0:
            defense = self.run_command(
                [sys.executable, str(REPO_ROOT / "scripts" / "check_defense_rate.py"), str(junit_path), "--threshold", "0.95"]
            )
            success = defense.returncode == 0
        else:
            success = False

        return StageResult(
            name="redteam",
            success=success,
            duration=time.time() - start,
            stdout=res.stdout[-2000:] if len(res.stdout) > 2000 else res.stdout,
            stderr=res.stderr[-2000:] if len(res.stderr) > 2000 else res.stderr,
            report_files=[junit_path],
        )

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
