# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **Consumer Simulation subsystem** specifications: how to generate and simulate LLM-based virtual consumers for Choice-Based Conjoint research.

## Navigation

- **Start here:** `README.md` — central navigation, document dependency graph, quick-start guide.
- **Quick practical entry:** `05-Prompt模板库.md` — copy-paste prompt templates.
- **Core generation flow:** `02-阶段一-画像生成.md`.
- **Agent framework:** `07-Harness架构设计方案.md`.
- **Multi-agent protocol:** `11-多Agent协作协议.md`.
- **Asset management:** `12-画像资产化管理规范.md`.
- **Testing:** `14-测试规范.md`.
- **API surface:** `16-API文档.md`.

## Document Numbering Convention

Files use two-digit prefixes (`01-` through `17-`) to indicate reading order. Do not rename them without updating `README.md` and `docs/文档索引与导航.md`.

## Core Design Principles

When editing any document here, preserve:

1. **张力优先 (Tension First)**: Virtual consumers must have internally contradictory traits, not average personalities. Every contradiction requires a psychological narrative explanation.
2. **Four-Layer Persona Model**:
   - Layer 1: Demographics (`layer1_demographics`)
   - Layer 2: Behavioral patterns (`layer2_behavior`)
   - Layer 3: Psychological motivations (`layer3_psychology`)
   - Layer 4: Situational narratives (`layer4_scenarios`)
   Upper layers must explain anomalies in lower layers.
3. **Bias Zero-Tolerance**: Generated personas must not systematically correlate preferences with protected attributes (gender, race, region, age, occupation, income, marital status).

## Role Ownership

| Role | Documents |
|------|-----------|
| 小示 (Behavior Engineer) | `02-阶段一-画像生成.md`, persona psychology and tag-system docs |
| 小应 (LLM Application Engineer) | `07-Harness架构设计方案.md`, `11-多Agent协作协议.md`, `05-Prompt模板库.md` |
| 小测 (QA Engineer) | `14-测试规范.md` |

## Key Cross-References

- `../消费者画像.md` — source-of-truth for the 12-dimension tag system.
- `../configs/tags/*.json` — machine-readable tag definitions consumed by generators.
- `../docs/目标人群角色卡设计.md` — target-audience role cards.
- `../cbc-questionnaire-system/04-CBC与模拟消费者集成方案.md` — downstream integration contract.
