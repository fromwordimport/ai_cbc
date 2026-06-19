"""CLI helper to generate bcrypt password hashes for frontend accounts.

Usage:
    uv run python scripts/generate_password_hash.py
"""

from __future__ import annotations

import getpass

from aicbc.core.security.password import hash_password


def main() -> None:
    """Prompt for a password and print its bcrypt hash."""
    password = getpass.getpass("Enter password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    print(hash_password(password))


if __name__ == "__main__":
    main()
