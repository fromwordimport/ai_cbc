# CLAUDE.md 文件整理与测试文件修改规则设计

> **版本**：v1.0  
> **日期**：2026-06-19  
> **状态**：已完成

## 背景与目标

AI_CBC 项目在根目录及 11 个子目录中维护了 12 个 `CLAUDE.md` 文件，用于向 Claude Code 提供目录级指导。随着项目演进，这些文件出现以下问题：

- 各文件章节结构不一致，部分文件缺少"常用命令"或"相关文档"等基础章节。
- 根目录"目录指引表"与子目录文件之间的相对链接可能存在失效或指向过时内容。
- 团队角色、全局编辑规范、数据交换格式等通用内容在根目录和子目录之间存在重复。
- 缺少对 Claude Code 修改测试文件的明确约束，容易导致未经授权改动测试代码。

本次设计的目标是在不改变文档核心语义的前提下，对上述问题进行结构化整理，并在根目录 `Core Design Principles` 中新增测试文件修改规则。

## 范围

**涉及文件（共 12 个）**：

1. 根目录 `CLAUDE.md`
2. `consumer-simulation/CLAUDE.md`
3. `cbc-questionnaire-system/CLAUDE.md`
4. `cbc-analysis-system/CLAUDE.md`
5. `docs/CLAUDE.md`
6. `src/CLAUDE.md`
7. `frontend/CLAUDE.md`
8. `tests/CLAUDE.md`
9. `configs/CLAUDE.md`
10. `docker/CLAUDE.md`
11. `k8s/CLAUDE.md`
12. `scripts/CLAUDE.md`

**不涉及文件**：

- `.venv/`、`.venv-test/` 中第三方包自带的 `CLAUDE.md`。
- `.claude/worktrees/` 下各工作树副本（这些副本会在工作树同步后自然跟随主仓库更新）。

## 方案选择

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A 最小改动 | 只在根目录新增规则，其他文件仅修复明显失效链接。 | 风险低、改动小。 | 整理不彻底，重复和格式问题仍然存在。 |
| **B 结构化整理（推荐）** | 统一格式模板、修复交叉引用、合并重复内容、新增核心原则。 | 可维护性提升明显，改动量可控。 | 需要逐篇核对。 |
| C 重构为分层治理 | 根目录只保留全局总览，子目录严格只写本目录内容，大量内容迁移。 | 长期维护最清晰。 | 工作量大，易引发大范围文档重组。 |

本设计采用 **方案 B**。

## 具体改动

### 1. 统一章节模板

每个子目录 `CLAUDE.md` 至少包含以下章节（已有完整结构的保持不动，缺失的补充）：

- **目的/范围**：说明该文件面向的角色和覆盖范围。
- **关键约定**：该目录下的编码、命名、数据等核心约定。
- **常用命令**：进入该目录后常用的开发、测试、构建命令。
- **相关文档链接**：指向根目录 `CLAUDE.md`、其他子目录 `CLAUDE.md` 或 `docs/` 中相关规范文件的相对链接。

### 2. 修复交叉引用

- 检查根目录 `CLAUDE.md` 中"目录指引表"的相对链接是否指向正确的子目录文件。
- 检查各子目录 `CLAUDE.md` 中引用的其他 `CLAUDE.md` 或 `docs/` 文件是否存在。
- 修正失效链接，删除指向已移除文档的引用或替换为最新位置。

### 3. 合并重复内容

- **团队角色表**：仅在根目录 `CLAUDE.md` 中维护。子目录中如需引用，使用相对链接指向根目录，不再复制完整表格。
- **全局编辑规范**：如"Always reply to the user in Chinese"、"Frontmatter uses Chinese blockquote style"等，仅在根目录说明。子目录中只保留与本目录强相关的特殊编辑约定。
- **全局数据交换格式**：`PersonaProfile`、`CBCRawDataset`、`AnalysisResult` 的概述保留在根目录。子目录中只说明本目录涉及的具体字段或处理逻辑。

### 4. 新增核心原则

在根目录 `CLAUDE.md` 的 `Core Design Principles` 章节中追加第 5 条：

```markdown
5. **Test File Integrity**: 不得在用户未明确授权的情况下修改测试文件（包括 `tests/`、`frontend/src/__tests__/` 目录及任何 `*test*.py`、`*spec*` 等测试相关文件）。若确需改动，必须先获得用户明确授权。
```

## 不做的内容

- 不改变现有文档的核心语义和技术决策。
- 不将通用内容大规模迁移到 `docs/` 或其他新文件。
- 不重写团队角色表、系统架构图或数据字典。
- 不修改 `.claude/worktrees/` 或 `.venv*` 中的副本。

## 验收标准

- [x] 12 个项目级 `CLAUDE.md` 文件均具备统一的章节结构。
- [x] 根目录"目录指引表"中所有相对链接均可正常跳转。
- [x] 子目录 `CLAUDE.md` 中不再重复出现团队角色表、全局编辑规范、全局数据格式等完整内容。
- [x] 根目录 `Core Design Principles` 中已新增"Test File Integrity"规则。
- [x] 所有改动通过 `markdownlint`（如项目已配置）或至少通过人工检查无格式错误。
- [x] 设计文档提交到 `docs/superpowers/specs/` 并通过用户审查。

## 实施记录

- 实施计划：`docs/superpowers/plans/2026-06-19-CLAUDE-md-整理.md`
- 链接验证脚本：`scripts/verify_claude_md_links.py`
