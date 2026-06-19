# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains **cross-cutting documentation** that spans all three subsystems: security, compliance, cost control, deployment, testing, data contracts, and project management.

## Navigation

- **Central index:** `文档索引与导航.md` — document registry, role-based lookup tables, dependency graph, parameter quick-reference.
- **Top-level entry:** `../AI_CBC_系统总览白皮书.md`.
- **Data contracts:** `数据字典.md` — authoritative schemas for `PersonaProfile`, `CBCRawDataset`, `AnalysisResult`.
- **Security/ethics:** `Agent安全架构纲要.md`, `伦理与偏见审计规范.md`, `安全架构与红队测试规范.md`, `偏见审计清单.md`, `隐私合规检查表.md`.
- **Cost control:** `成本管控方案.md`.
- **Acceptance criteria:** `项目成功标准书.md`, `业务验收标准与KPI框架.md`.
- **Experimental design:** `洗碗机CBC实验设计方案.md`.
- **Integration:** `全链路集成架构设计.md`, `端到端数据流与集成规范.md`.
- **CI/CD:** `CI-CD流水线设计.md`.
- **Compliance:** `compliance/privacy_policy.md`, `compliance/data_processing_agreement.md`.
- **Production readiness:** `生产就绪评估/2026-06-14-生产就绪评估报告.md`, `生产就绪评估/2026-06-14-生产就绪整改计划.md`.
- **Operations runbooks:** `运维/Consumer-simulation生产环境故障预案.md`.
- **Working reports:** `../reports/README.md` — progress, audit, validation, and performance reports.

## Subdirectories

| Directory | Contents |
|-----------|----------|
| `compliance/` | Privacy policy and data processing agreement |
| `superpowers/` | Review reports and audit summaries |
| `training/` | Training materials and quick-reference cards |
| `测试/` | Testing guides, runbooks, browser checklists, test data |
| `生产就绪评估/` | Production-readiness assessment reports and remediation plans |
| `运维/` | Operations runbooks and incident-response playbooks |
| `验收/` | UAT plans, test cases, defect reports, sign-off documents |

## Editing Conventions

遵循根目录 `../CLAUDE.md` 中的全局编辑规范。本目录特有的补充：

- **Update `docs/文档索引与导航.md`** when adding new documents.
- Parameter tables are authoritative — changing a threshold (e.g., `rhat_max < 1.1`) requires同步 updates in all referencing documents.

## Role Ownership

参见根目录 `../CLAUDE.md` 中的团队角色表。本目录文档主要由 小P、小联、小数、小端、小伦、小测、小验、小维、小控、小前、小培、小安 负责。
