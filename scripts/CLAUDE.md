# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **utility scripts** for development, verification, and batch operations.

## Scripts

| File | Purpose |
|------|---------|
| `batch_simulate.py` | End-to-end batch simulation CLI (persona generation → bias audit → questionnaire → choice simulation → export) |
| `verify_endpoints.py` | Endpoint verification using FastAPI `TestClient` with mocked LLM |
| `setup-azure-vm.sh` | Initialize an Azure B2ats v2 VM: install Docker, certbot, ufw, git; configure swap and firewall |
| `deploy-to-azure-b2ats.sh` | Pull latest images and restart the AI_CBC stack on Azure B2ats v2 |
| `backup-mongodb-to-azure.sh` | Dump MongoDB and upload to Azure Blob; falls back to local storage if no Blob config |
| `restore-mongodb.sh` | Restore MongoDB from a local `mongodump` tar.gz archive |
| `generate_password_hash.py` | Generate bcrypt hashes for frontend login passwords |

## Conventions

- All scripts add `../src/` to `sys.path` so `aicbc` imports work when run directly.
- Use `uv run python scripts/<script>.py` to execute.

## `batch_simulate.py`

- CLI arguments: `--n-personas`, `--study-id`, `--seed`, `--deterministic`, `--bias-audit`, `--output-dir`.
- Uses `structlog` and respects `CostFuse` budgets.

## Cross-References

- `../src/CLAUDE.md` — backend source conventions.
- `../frontend/CLAUDE.md` — frontend dev server usage.
- `../tests/CLAUDE.md` — test conventions.
- `../CLAUDE.md` — global repository guidance and team roles.
