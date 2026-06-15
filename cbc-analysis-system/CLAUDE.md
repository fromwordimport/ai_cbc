# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **CBC Data Analysis subsystem** specifications: statistical modeling, reporting, and agent-assisted interpretation of simulated CBC responses.

## Navigation

- **Start here:** `01-CBC数据分析系统架构.md`
- **Data interface contract:** `02-数据接口规范.md`
- **Model implementation guide:** `03-模型实现指南.md`
- **LLM-agent interpretation:** `04-LLM-Agent设计.md`
- **Testing/validation:** `05-测试与验证规范.md`
- **API design:** `06-API接口设计.md`
- **Tool-calling protocol:** `07-ToolCalling协议设计.md`

## Document Numbering Convention

Files use two-digit prefixes (`01-` through `07-`) to indicate reading order.

## Role Owner

- **小数 (Data/Modeling Scientist)** owns this directory: statistical modeling, API design, model validation.
- **小端 (Backend Engineer)** co-owns `06-API接口设计.md` and `07-ToolCalling协议设计.md`.

## Statistical Rigor Rules

- HB models must report R-hat and ESS.
- **R-hat > 1.1 means non-convergence.**
- **ESS must be > 400** for reliable inference.
- Effects coding is the default; parameters within an attribute sum to 0.
- Price coefficients must be negative for WTP calculations.
- Auto-fallback to MNL when sample size < 50 or choice tasks < 8.

## Key Cross-References

- `../cbc-questionnaire-system/04-CBC与模拟消费者集成方案.md` — upstream input format.
- `../docs/建模管线与API设计.md` — cross-cutting modeling pipeline.
- `../docs/数据字典.md` — `AnalysisResult` schema.
- `../src/aicbc/analysis/` — implementation of these specifications.
