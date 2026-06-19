# 已开发完成分支合并到 master 设计方案

> **版本**：v1.0
> **日期**：2026-06-19
> **作者**：Claude Code
> **状态**：已批准，待执行

## 目标

将 `feature/test-architecture-governance` 剩余未合入 master 的提交合并到 master，并同步本地 master 与远程 `origin/master`，清理仓库中已无用的本地分支。

## 背景

- 本地 `master` 停留在 `9c3fe04`，落后于远程 `origin/master`（`6e6c95e`）。
- `feature/test-architecture-governance` 分支尚有 1 个提交未进入 master：
  - `3bde20c ci: limit push triggers to master, release and hotfix branches`
- 本地分支 `cleanup/legacy-debt` 与 `worktree-uat-2-prep` 相对 master 无新增提交，可清理。

## 合并策略

采用**保守同步法**：先同步本地 master 到远程最新，再合并特性分支，验证后推送并清理。

## 执行步骤

1. **切换并同步 master**
   ```bash
   git checkout master
   git pull origin master
   ```

2. **合并特性分支**
   ```bash
   git merge --no-ff feature/test-architecture-governance
   ```

3. **验证合并结果**
   ```bash
   git log --oneline --graph -5
   ```
   如条件允许，运行测试套件进一步验证。

4. **推送**
   ```bash
   git push origin master
   ```

5. **清理分支**
   ```bash
   git branch -d cleanup/legacy-debt
   git branch -d worktree-uat-2-prep
   ```

## 回滚策略

若推送后发现异常，使用以下命令撤销合并提交：

```bash
git revert -m 1 <merge-commit-hash>
```

## 风险与注意事项

- 第 1 步拉取远程 master 时若工作区不干净可能失败，已确认当前工作区为空。
- `feature/test-architecture-governance` 的变更仅涉及 CI 触发器，业务代码无影响。
- 清理分支前已确认无未合入提交，避免误删工作。
