#!/usr/bin/env python3
"""Verify that all relative Markdown links in project CLAUDE.md files resolve."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_FILES = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "consumer-simulation" / "CLAUDE.md",
    REPO_ROOT / "cbc-questionnaire-system" / "CLAUDE.md",
    REPO_ROOT / "cbc-analysis-system" / "CLAUDE.md",
    REPO_ROOT / "docs" / "CLAUDE.md",
    REPO_ROOT / "src" / "CLAUDE.md",
    REPO_ROOT / "frontend" / "CLAUDE.md",
    REPO_ROOT / "tests" / "CLAUDE.md",
    REPO_ROOT / "configs" / "CLAUDE.md",
    REPO_ROOT / "docker" / "CLAUDE.md",
    REPO_ROOT / "k8s" / "CLAUDE.md",
    REPO_ROOT / "scripts" / "CLAUDE.md",
]

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

failures: list[tuple[Path, str, Path]] = []

for md_file in CLAUDE_FILES:
    text = md_file.read_text(encoding="utf-8")
    for _, target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            continue
        resolved = (md_file.parent / target).resolve()
        if not resolved.exists():
            failures.append((md_file, target, resolved))

if failures:
    print("Broken relative links:")
    for md_file, target, resolved in failures:
        print(f"  {md_file.relative_to(REPO_ROOT)} -> {target} (resolved: {resolved.relative_to(REPO_ROOT)})")
    sys.exit(1)

print("All relative links in CLAUDE.md files resolve successfully.")
