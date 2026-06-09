# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Nature

This is a **documentation and specification repository** for the AI_CBC virtual consumer research platform. There is no source code, build system, or test suite here — all files are design documents, architecture specifications, and process definitions written in Markdown.

## Python Environment

When Python code is introduced to this repository, **all environment and package management must use [`uv`](https://hellowac.github.io/uv-zh-cn/getting-started/)**. Do not use `pip`, `conda`, `poetry`, or `venv` directly. Use `uv venv` for virtual environments and `uv pip install` / `uv add` for dependency management.

## System Architecture

AI_CBC is a three-subsystem platform that uses LLM-generated "virtual consumers" to conduct Choice-Based Conjoint (CBC) market research:

```
Consumer Simulation → CBC Questionnaire → Data Analysis
     (生成)              (收集)              (分析)
```

| Subsystem | Directory | Core Function |
|-----------|-----------|---------------|
| Consumer Simulation | `consumer-simulation/` | Generate virtual consumer personas and simulate their behavior |
| CBC Questionnaire | `cbc-questionnaire-system/` | Design choice experiments and generate questionnaires |
| Data Analysis | `cbc-analysis-system/` | Statistical modeling (HB/MNL), market simulation, reporting |

A fourth **Security & Compliance Layer (安全与合规层)** spans all three subsystems, covering ethics auditing, bias detection, red-team testing, cost fuses, input sanitization, and log auditing. Specifications for this layer live in `docs/Agent安全架构纲要.md` and related security documents.

The subsystems exchange data through standardized formats defined in `docs/数据字典.md`.

## Document Navigation

**Start here for any work:** `AI_CBC_系统总览白皮书.md` — the system-wide white paper with architecture diagrams, phase definitions, and team roles.

**For navigation by task:** `docs/文档索引与导航.md` — central index with role-based lookup tables, document dependency graph, and parameter quick-reference.

**Key document clusters:**

| Task | Entry Document |
|------|---------------|
| Understand the overall system | `AI_CBC_系统总览白皮书.md` |
| Generate consumer personas | `consumer-simulation/05-Prompt模板库.md` (Template 1) |
| Design a CBC experiment | `docs/洗碗机CBC实验设计方案.md` |
| Integrate subsystems | `docs/全链路集成架构设计.md` |
| Define data contracts | `docs/数据字典.md` |
| Security/ethics review | `docs/Agent安全架构纲要.md` → `docs/伦理与偏见审计规范.md` |
| Business acceptance criteria | `docs/项目成功标准书.md` |

### Document Numbering Convention

All three subsystems use `NN-` prefix numbering (e.g., `01-`, `02-`) to indicate reading order. Within `consumer-simulation/`, `README.md` contains a full document dependency graph showing how the 17 numbered files relate to each other and to the root `消费者画像.md` tag-system source file.

## Core Design Principles

When editing or extending documents, preserve these architectural principles:

1. **张力优先 (Tension First)**: Virtual consumers must have internally contradictory traits (e.g., high income + extreme frugality), not "average" personalities. Every contradiction requires a psychological narrative explanation.

2. **Four-Layer Persona Model**: Consumer personas are structured as:
   - Layer 1: Demographics (`layer1_demographics`)
   - Layer 2: Behavioral patterns (`layer2_behavior`)
   - Layer 3: Psychological motivations (`layer3_psychology`)
   - Layer 4: Situational narratives (`layer4_scenarios`)
   Upper layers must explain anomalies in lower layers.

3. **Statistical Rigor**: HB models must report R-hat and ESS; R-hat > 1.1 means non-convergence. Effects coding is the default (parameters sum to 0). Price coefficients must be negative for WTP calculations.

4. **Bias Zero-Tolerance**: Virtual consumer preferences must not systematically correlate with protected attributes (gender, race, etc.). All persona batches undergo automated bias auditing.

## Standard Data Exchange Formats

Three key interfaces between subsystems (full schemas in `docs/数据字典.md`):

| Flow | Format | Producer → Consumer | Key Fields |
|------|--------|---------------------|------------|
| Persona output | `PersonaProfile` JSON | consumer-simulation → questionnaire & analysis | `persona_id`, four layers, `authenticity_score` |
| Raw responses | `CBCRawDataset` JSON/CSV | questionnaire → analysis | `metadata`, `choice_records` with `chosen` flag |
| Analysis result | `AnalysisResult` JSON | analysis → dashboard/report | `individual_utilities`, `importance`, `wtp`, `convergence` |

### Effects Coding Naming Convention

Categorical attributes use `{attribute_id}_{level_index}` where `level_index` ranges `0` to `n_levels-2`. The last level is recovered as the negative sum of others. Example: `capacity_0`, `capacity_1` → 3rd level = `-(capacity_0 + capacity_1)`.

## Team Roles & Document Ownership

Documents are owned by named roles (not individuals). Understanding these helps locate the right specification:

| Role | Code | Domain | Key Documents |
|------|------|--------|---------------|
| 小联 | Conjoint Expert | Experimental design, model interpretation | `cbc-questionnaire-system/`, `docs/洗碗机CBC实验设计方案.md` |
| 小数 | Data/Modeling Scientist | Statistical modeling, APIs | `cbc-analysis-system/`, `docs/建模管线与API设计.md` |
| 小应 | LLM Application Engineer | Agent framework, prompts | `consumer-simulation/07-Harness架构设计方案.md`, `docs/Agent原型Prompt设计.md` |
| 小示 | Behavior Engineer | Consumer psychology, persona design | `consumer-simulation/02-阶段一-画像生成.md`, `docs/目标人群角色卡设计.md` |
| 小端 | Backend Engineer | Integration, data pipelines | `docs/全链路集成架构设计.md`, `docs/数据字典.md` |
| 小伦 | Ethics/Bias Auditor | Fairness, compliance | `docs/伦理与偏见审计规范.md`, `docs/虚拟消费者公平性规范.md` |
| 小测 | QA Engineer | Testing, validation | `consumer-simulation/14-测试规范.md`, `docs/测试验证方案.md` |
| 小验 | Business Acceptance | KPIs, UAT | `docs/项目成功标准书.md`, `docs/业务验收标准与KPI框架.md` |

## Editing Conventions

- All documents use Markdown with Chinese as the primary language
- Frontmatter format: Chinese blockquote style (`> **版本**：v1.0`) — not YAML frontmatter. Typical fields: version, positioning, maintainer, related documents
- Cross-references use relative paths with `[]()` links
- The central index (`docs/文档索引与导航.md`) must be updated when adding new documents
- Parameter tables are authoritative — changing a threshold (e.g., `rhat_max < 1.1`) requires同步 updates in all referencing documents
