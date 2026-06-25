> **版本**：v1.0
> **日期**：2026-06-25
> **主题**：远程 feature 分支合并与 CI/CD 门禁流程
> **执行策略**：方案 A — 逐分支合并 + 单分支 CI 门禁

# 远程 feature 分支合并与 CI/CD 门禁设计

## 1. 目标

安全地将 4 个远程 `feature/*` 分支处理完毕：

- 对已合并到 `origin/master` 的分支进行验证并删除远程分支。
- 对未合并的分支通过 Pull Request + CI/CD 门禁逐个合并到 `master`。
- 整个过程中若出现冲突或 CI 失败，必须先汇报并获得授权后再修改。

## 2. 分支清单

| 分支名 | 与 `origin/master` 关系 | 处理方式 |
|--------|------------------------|----------|
| `origin/feature/ci-merge-commit-check` | 已合并 | 验证后删除远程分支 |
| `origin/feature/security-scan-ignore-unfixed` | 已合并 | 验证后删除远程分支 |
| `origin/feature/cicd-pipeline-flag-scripts` | 未合并 | 走 PR + CI 合并 |
| `origin/feature/optimize-slow-tests` | 未合并 | 走 PR + CI 合并 |

## 3. 前置准备

当前本地 `master` 工作区存在未提交改动，合并前必须先清理：

1. 列出所有未提交改动（修改、删除、未跟踪文件）。
2. 由用户确认处置方式：
   - `git stash` 暂存；
   - 提交为临时 commit；
   - 还原到干净状态。
3. 执行 `git fetch origin` 拉取最新远程状态。
4. 本地 `master` 更新到 `origin/master`。

## 4. 已合并分支清理流程

对每个已合并分支执行以下步骤：

1. 使用 `git branch -r --merged origin/master` 二次确认该分支确实已合并。
2. 删除远程分支：`git push origin --delete feature/xxx`。
3. 记录删除操作到本设计文档的「执行日志」附录。

> **授权要求**：删除远程分支为不可恢复操作，执行前必须获得用户明确授权。

## 5. 未合并分支合并流程

### 5.1 合并顺序

合并前先检查两个未合并分支的改动范围，决定顺序：

- 若 `cicd-pipeline-flag-scripts` 修改了 CI 工作流，优先合并它，确保 `optimize-slow-tests` 在最新 CI 配置下运行。
- 若存在代码冲突，先合入不依赖对方的基础分支。
- 若改动无交集，默认按字母顺序合并。

### 5.2 单分支合并步骤

以 `feature/xxx` 为例：

1. **创建本地跟踪分支**
   ```bash
   git checkout -b feature/xxx origin/feature/xxx
   ```

2. **本地预检合并**
   ```bash
   git merge --no-ff --no-commit origin/master
   ```
   - 若存在冲突：立即停止，生成冲突文件清单与 diff，汇报后等待授权解决。

3. **创建 Pull Request**
   ```bash
   gh pr create --base master --head feature/xxx --title "..." --body "..."
   ```

4. **触发 CI/CD**
   - PR 创建后自动触发 `.github/workflows/ci.yml`。
   - 监控 PR checks 状态直到完成。

5. **处理 CI 结果**
   - **通过**：继续下一步。
   - **失败**：停止，提取失败 job 日志，定位根因，向用户汇报，获得授权后再修复。

6. **合并 PR**
   - 使用 merge commit 方式合并，保留分支历史。
   ```bash
   gh pr merge --merge
   ```

7. **更新本地 master**
   ```bash
   git checkout master
   git pull origin master
   ```

8. **清理远程功能分支**
   - 在用户授权后，删除已合并的远程功能分支。

## 6. 错误处理与汇报机制

| 场景 | 处理方式 |
|------|----------|
| 工作区未提交改动 | 先请示处置方式，不擅自清理 |
| 分支冲突 | 生成冲突文件清单与 diff，汇报后按授权解决 |
| CI 失败 | 截取失败 job 日志，定位到具体文件/测试，汇报根因 |
| 测试失败 | 按项目规范，不擅自修改测试文件，先汇报并请求授权 |
| 合并后异常 | 可回滚到合并前 `origin/master` 的 SHA，汇报情况 |

## 7. 成功标准

- `master` 包含 `cicd-pipeline-flag-scripts` 和 `optimize-slow-tests` 的最新改动。
- 所有相关 CI 检查通过。
- `ci-merge-commit-check` 和 `security-scan-ignore-unfixed` 的远程分支被安全删除。
- 未发生未经授权的文件修改。

## 8. 执行日志

执行过程中按下列格式补充记录：

| 时间 | 操作 | 分支 | 结果 | 备注 |
|------|------|------|------|------|
| 2026-06-25 | 删除远程分支 | feature/ci-merge-commit-check | 成功 | 已合并到 master |
| 2026-06-25 | 删除远程分支 | feature/security-scan-ignore-unfixed | 成功 | 已合并到 master |
| 2026-06-25 | 合并 PR | feature/optimize-slow-tests | 成功 | PR #17，CI 全部通过 |
| 2026-06-25 | 删除远程分支 | feature/optimize-slow-tests | 成功 | PR #17 合并后清理 |
| 2026-06-25 | 解决冲突并合并 PR | feature/cicd-pipeline-flag-scripts | 成功 | PR #18，3 个 add/add 冲突已解决，CI 全部通过 |
| 2026-06-25 | 删除远程分支 | feature/cicd-pipeline-flag-scripts | 成功 | PR #18 合并后清理 |

---

*本设计经用户确认后执行。*
