# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory holds **runtime configuration assets** consumed by the backend and the consumer-simulation subsystem.

## Contents

| Path | Purpose |
|------|---------|
| `prompts/persona_generation.txt` | Prompt template for layered persona generation |
| `tags/demographics.json` | Structured demographic tag definitions |
| `tags/behaviors.json` | Structured behavior tag definitions |
| `tags/psychologies.json` | Structured psychology tag definitions |
| `tags/scenarios.json` | Structured scenario tag definitions |

## Role Ownership

- **小示 (Behavior Engineer)** owns the `tags/*.json` files.
- **小应 (LLM Application Engineer)** owns `prompts/persona_generation.txt`.

## Conventions

- Tag JSON files are the machine-readable counterparts to `../消费者画像.md` and the specifications in `../consumer-simulation/`.
- The prompt template is read by `../src/aicbc/generators/profile_generator.py`.
- Keep tag definitions aligned with the four-layer persona model and the 12-dimension tag system in `../消费者画像.md`.
- Changes here may require corresponding updates in `consumer-simulation/02-阶段一-画像生成.md` and `docs/目标人群角色卡设计.md`.

## Cross-References

- `../消费者画像.md` — source-of-truth tag system.
- `../consumer-simulation/` — generation subsystem specs.
- `../src/aicbc/generators/profile_generator.py` — consumer of `prompts/persona_generation.txt`.
- `../CLAUDE.md` — global repository guidance and team roles.
