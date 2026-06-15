# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **utility scripts** for development, verification, and batch operations.

## Scripts

| File | Purpose |
|------|---------|
| `dev_server_with_mocks.py` | Minimal FastAPI dev server with mocked LLM; recommended for Windows frontend development |
| `batch_simulate.py` | End-to-end batch simulation CLI (persona generation → bias audit → questionnaire → choice simulation → export) |
| `verify_endpoints.py` | Endpoint verification using FastAPI `TestClient` with mocked LLM |

## Conventions

- All scripts add `../src/` to `sys.path` so `aicbc` imports work when run directly.
- Use `uv run python scripts/<script>.py` to execute.

## `dev_server_with_mocks.py`

- Bypasses heavy imports (`pandas`, `prometheus_client`) that can crash on Windows.
- Mounts the personas router and provides mocked `/api/v1/health`, `/api/v1/cost-status`, `/api/v1/studies/*`, `/api/v1/admin/settings`, etc.
- Enables CORS for `http://localhost:3000` and `http://localhost:3001`.
- Seeds 5 demo personas on startup so the frontend Response Simulator has data.
- Recommended command: `uv run python scripts/dev_server_with_mocks.py`

## `batch_simulate.py`

- CLI arguments: `--n-personas`, `--study-id`, `--seed`, `--deterministic`, `--bias-audit`, `--output-dir`.
- Uses `structlog` and respects `CostFuse` budgets.

## Cross-References

- `../src/CLAUDE.md` — backend source conventions.
- `../frontend/CLAUDE.md` — frontend dev server usage.
- `../tests/CLAUDE.md` — test conventions.
