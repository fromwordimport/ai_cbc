# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **utility scripts** for development, verification, and batch operations.

## Scripts

| File | Purpose |
|------|---------|
| `batch_simulate.py` | End-to-end batch simulation CLI (persona generation → bias audit → questionnaire → choice simulation → export) |
| `verify_endpoints.py` | Endpoint verification using FastAPI `TestClient` with mocked LLM |

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
