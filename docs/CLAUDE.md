# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **cross-cutting documentation** that spans all three subsystems: security, compliance, cost control, deployment, testing, data contracts, and project management.

## Navigation

- **Central index:** `文档索引与导航.md` — document registry, role-based lookup tables, dependency graph, parameter quick-reference.
- **Top-level entry:** `../AI_CBC_系统总览白皮书.md`.
- **Data contracts:** `数据字典.md` — authoritative schemas for `PersonaProfile`, `CBCRawDataset`, `AnalysisResult`.
- **Security/ethics:** `Agent安全架构纲要.md`, `伦理与偏见审计规范.md`, `安全架构与红队测试规范.md`.
- **Cost control:** `成本管控方案.md`.
- **Acceptance criteria:** `项目成功标准书.md`, `业务验收标准与KPI框架.md`.
- **Experimental design:** `洗碗机CBC实验设计方案.md`.
- **Integration:** `全链路集成架构设计.md`, `端到端数据流与集成规范.md`.
- **CI/CD:** `CI-CD流水线设计.md`.
- **Compliance:** `compliance/privacy_policy.md`, `compliance/data_processing_agreement.md`.
- **Production readiness:** `生产就绪评估/2026-06-14-生产就绪评估报告.md`, `生产就绪评估/2026-06-13-生产就绪整改计划.md`.
- **Working reports:** `../reports/README.md` — progress, audit, validation, and performance reports.

## Subdirectories

| Directory | Contents |
|-----------|----------|
| `compliance/` | Privacy policy and data processing agreement |
| `superpowers/` | Review reports and audit summaries |
| `training/` | Training materials and quick-reference cards |
| `测试/` | Testing guides, runbooks, browser checklists, test data |
| `生产就绪评估/` | Production-readiness assessment reports and remediation plans |
| `验收/` | UAT plans, test cases, defect reports, sign-off documents |

## Editing Conventions

- Documents use Markdown with **Chinese as the primary language**.
- Frontmatter uses Chinese blockquote style (`> **版本**：v1.0`), not YAML.
- Cross-references use relative paths with `[]()` links.
- **Update `docs/文档索引与导航.md`** when adding new documents.
- Parameter tables are authoritative — changing a threshold (e.g., `rhat_max < 1.1`) requires同步 updates in all referencing documents.

## Role Ownership

| Role | Key Documents |
|------|---------------|
| 小P (PM) | `文档索引与导航.md`, `项目进度计划与里程碑.md`, `风险管理登记册.md` |
| 小端 (Backend Engineer) | `数据字典.md`, `全链路集成架构设计.md`, `端到端数据流与集成规范.md` |
| 小数 (Data/Modeling Scientist) | `建模管线与API设计.md` (with 小端) |
| 小伦 (Ethics/Bias Auditor) | `伦理与偏见审计规范.md`, `虚拟消费者公平性规范.md` |
| 小安 (Security Engineer) | `Agent安全架构纲要.md`, `安全架构与红队测试规范.md` |
| 小控 (Cost Engineer) | `成本管控方案.md` |
| 小验 (Business Acceptance) | `项目成功标准书.md`, `业务验收标准与KPI框架.md` |
| 小维 (DevOps) | `CI-CD流水线设计.md` |
