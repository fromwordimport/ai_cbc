# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **Python test suite** for AI_CBC, using `pytest`.

## Structure

```
tests/
├── unit/              # Pure unit tests, no external dependencies
├── integration/       # Tests requiring DB/Redis/Celery/API
├── e2e/               # End-to-end full pipeline tests
├── redteam/           # Security/adversarial tests
├── performance/       # Load and regression tests
├── manual/            # Manual acceptance scripts
└── support/           # Shared factories, datasets, mocks
```

## Running Tests

```bash
# Default fast feedback (CI equivalent)
uv run pytest -m "(unit or integration) and not slow and not redteam and not performance"

# Unit tests only
uv run pytest -m unit

# Include slow tests
uv run pytest -m "not performance"

# Full suite
uv run pytest

# Red team fast
uv run pytest tests/redteam/ -m "security and not slow"

# Red team full
uv run pytest tests/redteam/

# Performance regression
uv run pytest tests/performance/
```

## Key Conventions

- `conftest.py` provides an **autouse per-function fixture** (`_clean_global_state`) that resets module-level singletons to prevent cross-test leakage:
  - `api.dependencies.reset_dependencies()`
  - `core.store.reset_stores()`
  - `analysis.store.reset_analysis_store()`
  - `cost.tracker.reset_cost_tracker()`
  - FastAPI `app.dependency_overrides.clear()`
  - rate-limit state reset
  - deletes `./data/cost_state.json`
- Heavy imports (`aicbc.main`, `aicbc.analysis.store`) are lazy-loaded once and cached in `conftest.py`.
- Use `app.dependency_overrides` to inject mocks for FastAPI `TestClient` tests.
- The `@pytest.mark.slow` marker excludes expensive tests (e.g., full MCMC sampling) from the default run.

## Useful Fixtures

| Fixture | Purpose |
|---------|---------|
| `mock_llm_client` | `MagicMock` LLM client returning canned four-layer persona responses |
| `sample_persona` | Fully valid `PersonaProfile` instance for API testing |
| `clean_store` | Fresh empty `PersonaStore` |
| `test_settings` | Settings configured for `environment="test"`, `debug=True` |

## Frontend Tests

Frontend tests live in `../frontend/src/__tests__/` and run via Vitest, not pytest.

## Cross-References

- `../src/CLAUDE.md` — backend source conventions.
- `../src/aicbc/api/dependencies.py` — dependency singletons and `reset_dependencies()`.
- `../src/aicbc/main.py` — FastAPI app used in integration tests.
