# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **CBC Questionnaire subsystem** specifications: how to design Choice-Based Conjoint experiments and generate valid choice sets.

## Navigation

- **Start here:** `01-CBC系统架构与解决方案.md`
- **Experimental design algorithms:** `03-CBC实验设计算法说明.md`
- **Attribute/level design:** `05-属性水平与实验设计.md`
- **Input contract:** `02-CBC问卷生成输入规范.md`
- **Integration with consumer simulation:** `04-CBC与模拟消费者集成方案.md`

## Document Numbering Convention

Files use two-digit prefixes (`01-` through `05-`) to indicate reading order.

## Role Owner

- **小联 (Conjoint Expert)** owns this directory: experimental design, attribute/level definitions, model interpretation.

## Design Conventions

- Each attribute must have at least 2 levels.
- Attribute IDs must match `^[a-zA-Z0-9_\-]+$`.
- D-efficiency target is 0.85; minimum acceptable is 0.80.
- Supported algorithms: balanced/orthogonal and D-optimal.
- Prohibited attribute-level pairs must be explicitly declared and validated.
- Effects coding is the default: `{attribute_id}_{level_index}` where `level_index` ranges `0` to `n_levels-2`; the last level is the negative sum of the others.

## Key Cross-References

- `../docs/洗碗机CBC实验设计方案.md` — concrete dishwasher-scenario design.
- `../docs/数据字典.md` — data contracts for `CBCQuestionnaire`, `CBCRawDataset`.
- `../cbc-analysis-system/02-数据接口规范.md` — downstream analysis input format.
- `../src/aicbc/questionnaire/` — implementation of these specifications.
