# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **Python backend source code** for AI_CBC: a FastAPI application that orchestrates virtual-consumer generation, CBC questionnaire design, response simulation, and statistical analysis.

## Entry Points

- `aicbc/main.py` — FastAPI app initialization, middleware registration, router inclusion, MongoDB/Beanie startup.
- `aicbc/config/settings.py` — Pydantic-settings configuration loaded from `.env`.

## Package Layout

| Package | Responsibility |
|---------|----------------|
| `agents/` | Base agent framework (`BaseAgent`), `ConsumerGeneratorAgent`, `AnalysisAgent`, evaluation chain, tool protocol |
| `api/` | FastAPI routes, dependency injection (`dependencies.py`), request/response schemas, middleware |
| `analysis/` | HB/MNL engines, preprocessing, importance/WTP, market simulation, report builder, Celery tasks |
| `config/` | Pydantic settings, pricing lookups |
| `core/` | Domain models, storage (memory + MongoDB), validators, authenticity scorer, bias auditor, security, audit logging |
| `cost/` | `CostTracker` singleton and `CostFuse` budget enforcement |
| `generators/` | `SeedGenerator` and `ProfileGenerator` for layered persona generation |
| `llm/` | Unified Anthropic/OpenAI client with retry, caching, cost estimation, model router |
| `monitoring/` | Prometheus metrics, health/readiness endpoints, middleware |
| `questionnaire/` | CBC study models, D-optimal/orthogonal design generators, effects coding, validators |

## Common Commands

All Python commands use `uv`.

```bash
# Install dependencies
uv venv
uv pip install -e ".[dev,analysis]"

# Run server (all platforms)
uv run uvicorn src.aicbc.main:app --reload --host 0.0.0.0 --port 8000

# Tests
uv run pytest tests/ -v
uv run pytest tests/test_profile_generator.py -v
uv run pytest tests/test_profile_generator.py::test_name -v
uv run pytest tests/ -m "not slow"          # default
uv run pytest tests/ -m slow                # include slow tests
uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

# Code quality
uv run ruff check src/
uv run ruff format --check src/
uv run ruff format src/
uv run mypy src/ --strict --ignore-missing-imports
uv run bandit -r src/
```

## Key Conventions

- **Pydantic v2** for all domain models, API schemas, and settings.
- **Structlog** for logging: `structlog.get_logger("aicbc.<module>")`.
- **Lazy singletons** in `api/dependencies.py` — reset them in tests via `reset_dependencies()`.
- **Pluggable storage** — `core/store*.py` defaults to in-memory in dev/test unless `USE_MEMORY_STORE=false` or `MONGODB_URL` is non-default.
- **Cost fuse** — every LLM call flows through `CostFuse`; budgets are configured via `COST_FUSE_*_CNY` env vars.
- **Agent prompt architecture** — `SystemInstruction` → `RuleInjection` → `DynamicExample` in `agents/base.py`.
- **Tension-first design** — every `PersonaProfile` requires a `TensionCombination` with `narrative_explanation` ≥ 50 chars.
- **Security** — input sanitization, prompt-injection detection, RBAC, rate limiting, API-key middleware.
- **Async analysis** — CPU-intensive HB sampling runs in Celery workers (`analysis/tasks.py`); API returns `202 Accepted` with polling.
- **Effects coding** — categorical attributes use `{attribute_id}_{level_index}` with indices `0` to `n_levels-2`.

## Configuration

- Copy `.env.example` to `.env` and set LLM keys.
- `SECRET_KEY` must be ≥ 32 chars in production.
- `API_KEY` defaults to `dev-key-change-in-prod`; production must override it.
- Dev API key is hard-coded in `frontend/src/services/api.ts`.

## Cross-References

- `../consumer-simulation/` — generation subsystem specs.
- `../cbc-questionnaire-system/` — questionnaire subsystem specs.
- `../cbc-analysis-system/` — analysis subsystem specs.
- `../docs/数据字典.md` — data schemas.
- `../configs/` — prompt template and tag config assets.
- `../tests/` — test suite conventions.
- `../scripts/` — dev server and batch simulation scripts.
- `../CLAUDE.md` — global repository guidance and team roles.
