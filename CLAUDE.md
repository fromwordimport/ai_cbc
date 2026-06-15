# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Repository Nature

AI_CBC is a virtual-consumer Choice-Based Conjoint (CBC) research platform. This repo contains **both design specifications and a working application**:

- Markdown specifications and architecture documents under `consumer-simulation/`, `cbc-questionnaire-system/`, `cbc-analysis-system/`, and `docs/`.
- Python/FastAPI backend under `src/`.
- React + Vite frontend under `frontend/`.
- Test suites under `tests/` and `frontend/src/__tests__/`.
- Deployment artifacts under `docker/` and `k8s/`.
- Runtime assets under `configs/` and utility scripts under `scripts/`.

## System Architecture

```
Consumer Simulation → CBC Questionnaire → Data Analysis
     (生成)              (收集)              (分析)
```

A **Security & Compliance Layer** spans all three subsystems.

## Directory Guidance

For detailed conventions and commands, see the CLAUDE.md in each directory:

| Directory | Focus |
|-----------|-------|
| [`consumer-simulation/CLAUDE.md`](consumer-simulation/CLAUDE.md) | Virtual-consumer generation specs, four-layer persona model, prompt templates |
| [`cbc-questionnaire-system/CLAUDE.md`](cbc-questionnaire-system/CLAUDE.md) | CBC experimental design specs, attribute/level conventions |
| [`cbc-analysis-system/CLAUDE.md`](cbc-analysis-system/CLAUDE.md) | Statistical modeling specs, HB/MNL, convergence rules |
| [`docs/CLAUDE.md`](docs/CLAUDE.md) | Cross-cutting docs index, editing conventions, role owners |
| [`src/CLAUDE.md`](src/CLAUDE.md) | Python backend architecture, dev commands, testing, linting |
| [`frontend/CLAUDE.md`](frontend/CLAUDE.md) | React/Vite frontend, dev/test commands, API client |
| [`tests/CLAUDE.md`](tests/CLAUDE.md) | pytest conventions, fixtures, global-state cleanup, red-team tests |
| [`configs/CLAUDE.md`](configs/CLAUDE.md) | Prompt templates and tag JSON assets |
| [`docker/CLAUDE.md`](docker/CLAUDE.md) | Container build and local observability stack |
| [`k8s/CLAUDE.md`](k8s/CLAUDE.md) | Kubernetes deployment manifests |
| [`scripts/CLAUDE.md`](scripts/CLAUDE.md) | Dev server with mocks, batch simulation, endpoint verification |

## Quick Start

```bash
# Backend (use mocked dev server on Windows; see src/CLAUDE.md for details)
uv venv
uv pip install -e ".[dev,analysis]"
uv run python scripts/dev_server_with_mocks.py

# Frontend
cd frontend
npm install
npm run dev    # http://localhost:3000, proxies /api to localhost:8000
```

## Data Exchange Formats

Standard interfaces (full schemas in [`docs/数据字典.md`](docs/数据字典.md)):

| Flow | Format | Producer → Consumer |
|------|--------|---------------------|
| Persona output | `PersonaProfile` JSON | consumer-simulation → questionnaire & analysis |
| Raw responses | `CBCRawDataset` JSON/CSV | questionnaire → analysis |
| Analysis result | `AnalysisResult` JSON | analysis → dashboard/report |

## Core Design Principles

1. **张力优先 (Tension First)**: Virtual consumers must have internally contradictory traits, not average personalities. Every contradiction requires a psychological narrative explanation.
2. **Four-Layer Persona Model**: Demographics → Behavior → Psychology → Scenarios. Upper layers explain anomalies in lower layers.
3. **Statistical Rigor**: HB models must report R-hat and ESS; R-hat > 1.1 means non-convergence. Effects coding is the default. Price coefficients must be negative for WTP calculations.
4. **Bias Zero-Tolerance**: Virtual consumer preferences must not systematically correlate with protected attributes. All persona batches undergo automated bias auditing.

## Editing Conventions

- Specification documents use Markdown with Chinese as the primary language.
- Frontmatter uses Chinese blockquote style (`> **版本**：v1.0`), not YAML.
- Cross-references use relative paths with `[]()` links.
- Update `docs/文档索引与导航.md` when adding new documents.
- Parameter tables are authoritative — changing a threshold requires同步 updates in all referencing documents.

## Environment & CI/CD

- Python environment and package management must use `uv`.
- Node.js 20+ for the frontend.
- Copy `.env.example` to `.env` and set LLM keys.
- CI/CD enforces conventional commits (`feat(scope): ...`), branch naming, ruff/mypy/bandit, pytest coverage ≥ 60%, and frontend build/test. See `.github/workflows/ci-cd.yml`.

## Team Roles

| Role | Domain | Key Areas |
|------|--------|-----------|
| 小P | PM | `docs/文档索引与导航.md`, schedule, risks |
| 小联 | Conjoint Expert | `cbc-questionnaire-system/`, `docs/洗碗机CBC实验设计方案.md` |
| 小数 | Data/Modeling Scientist | `cbc-analysis-system/`, `src/aicbc/analysis/`, `docs/建模管线与API设计.md` |
| 小应 | LLM Application Engineer | `consumer-simulation/07-Harness架构设计方案.md`, `src/aicbc/agents/`, prompts |
| 小示 | Behavior Engineer | `consumer-simulation/02-阶段一-画像生成.md`, `configs/tags/`, `docs/目标人群角色卡设计.md` |
| 小端 | Backend Engineer | `docs/数据字典.md`, `src/aicbc/api/`, `src/aicbc/core/store*.py` |
| 小伦 | Ethics/Bias Auditor | `docs/伦理与偏见审计规范.md`, `tests/redteam/` |
| 小测 | QA Engineer | `consumer-simulation/14-测试规范.md`, `tests/` |
| 小验 | Business Acceptance | `docs/项目成功标准书.md`, `docs/业务验收标准与KPI框架.md` |
| 小维 | DevOps/MLOps | `.github/workflows/`, `docker/`, `k8s/`, `docker-compose.yml` |
| 小控 | Cost Engineer | `src/aicbc/cost/`, cost env vars |
| 小前 | Frontend Engineer | `frontend/` |
| 小速 | Performance Engineer | Performance gates and optimizations |
| 小培 | Training | Training materials and onboarding |
| 小安 | Security Engineer | `docs/Agent安全架构纲要.md`, security reviews |
