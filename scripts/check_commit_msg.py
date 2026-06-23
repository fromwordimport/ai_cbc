#!/usr/bin/env python3
"""Validate AI_CBC conventional commit messages.

Usage:
    python scripts/check_commit_msg.py <commit-msg-file>
    python scripts/check_commit_msg.py --from-git
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

VALID_TYPES = r"feat|fix|docs|test|refactor|perf|security|cost|chore|ci"
PATTERN = rf"^({VALID_TYPES})\(.+\):\s+\S.+"


def get_message_from_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read commit message file: {exc}") from exc
    return text.splitlines()[0] if text else ""


def get_message_from_git() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%s", "-n", "1", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git log failed: {exc}") from exc
    return result.stdout.strip()


WHITELIST_PREFIXES = ("Merge ", "Revert \"", "Squash ")


def validate(message: str) -> tuple[bool, str]:
    if not message:
        return False, "commit message is empty"
    if message.startswith(WHITELIST_PREFIXES):
        return True, ""
    if not re.match(PATTERN, message):
        return (
            False,
            "commit message must match: type(scope): description, "
            f"where type is one of {VALID_TYPES}",
        )
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", help="path to commit message file")
    parser.add_argument("--from-git", action="store_true", help="read last commit from git")
    args = parser.parse_args()

    try:
        if args.path:
            message = get_message_from_file(Path(args.path))
        elif args.from_git:
            message = get_message_from_git()
        else:
            parser.print_help()
            return 2
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    ok, error = validate(message)
    if not ok:
        print(f"FAIL: {error}")
        print(f"Message: {message!r}")
        return 1

    print(f"OK: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
