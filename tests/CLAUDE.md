# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **Python test suite** for AI_CBC, using `pytest`.

## Structure

```
tests/
├── conftest.py              # Global fixtures and autouse cleanup
├── test_*.py                # Backend unit/integration tests
├── analysis/                # Analysis subsystem tests
│   ├── test_analysis_agent.py
│   ├── test_hb_engine.py
│   ├── test_mnl_engine.py
│   ├── test_market_simulator.py
│   ├── test_preprocessing.py
│   └── test_synthetic_recovery.py
└── redteam/                 # Adversarial/security tests
    └── test_agent_security.py
```

## Running Tests

```bash
# Default (excludes slow tests)
uv run pytest tests/ -v

# Single file / single test
uv run pytest tests/test_profile_generator.py -v
uv run pytest tests/test_profile_generator.py::test_name -v

# Include slow tests
uv run pytest tests/ -m slow

# Coverage (CI-style)
uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

# Red-team tests only
uv run pytest tests/redteam/ -v
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
