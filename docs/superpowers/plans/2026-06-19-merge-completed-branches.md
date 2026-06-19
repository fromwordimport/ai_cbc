# 已开发完成分支合并到 master 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `feature/test-architecture-governance` 合并到 `master`，同步本地与远程 `master`，并清理无用的本地分支。

**Architecture:** 采用保守同步法，先拉取远程 `master` 确保本地基准最新，再通过 `--no-ff` 合并保留分支历史，验证后推送并清理分支。

**Tech Stack:** Git

---

## 文件结构

本计划不涉及代码文件的创建或修改，仅操作 Git 分支和提交历史：

- 目标分支：`master`
- 待合并分支：`feature/test-architecture-governance`
- 待清理本地分支：`cleanup/legacy-debt`、`worktree-uat-2-prep`
- 设计文档：`docs/superpowers/specs/2026-06-19-merge-completed-branches-design.md`
- 本计划文档：`docs/superpowers/plans/2026-06-19-merge-completed-branches.md`

---

### Task 1: 验证工作区状态

- [ ] **Step 1: 检查当前分支与工作区**

  Run:
  ```bash
  git status --short
  git branch --show-current
  ```

  Expected:
  - `git status --short` 输出为空
  - `git branch --show-current` 输出 `master`

- [ ] **Step 2: 确认待合并分支存在且包含未合入提交**

  Run:
  ```bash
  git log --oneline master..feature/test-architecture-governance
  ```

  Expected:
  ```
  3bde20c ci: limit push triggers to master, release and hotfix branches
  ```

- [ ] **Step 3: 确认待清理分支无未合入提交**

  Run:
  ```bash
  git log --oneline master..cleanup/legacy-debt
  git log --oneline master..worktree-uat-2-prep
  ```

  Expected:
  两条命令均无输出

---

### Task 2: 同步本地 master 与远程

- [ ] **Step 1: 切换到 master 并拉取远程更新**

  Run:
  ```bash
  git checkout master
  git pull origin master
  ```

  Expected:
  - `git pull` 成功，显示 `Updating 9c3fe04..6e6c95e` 或类似信息
  - 无冲突提示

- [ ] **Step 2: 验证本地 master 已与远程同步**

  Run:
  ```bash
  git log --oneline --decorate -1
  ```

  Expected:
  - 输出包含 `(HEAD -> master, origin/master, origin/HEAD)`
  - commit hash 为 `6e6c95e` 或远程最新

---

### Task 3: 合并 feature/test-architecture-governance

- [ ] **Step 1: 执行非快进合并**

  Run:
  ```bash
  git merge --no-ff feature/test-architecture-governance
  ```

  Expected:
  - 编辑器弹出合并提交信息，内容为默认的 `Merge branch 'feature/test-architecture-governance'`
  - 保存并关闭编辑器后显示合并成功

- [ ] **Step 2: 验证合并历史**

  Run:
  ```bash
  git log --oneline --graph -5
  ```

  Expected:
  ```
  *   <new-hash> Merge branch 'feature/test-architecture-governance'
  |\
  | * 3bde20c ci: limit push triggers to master, release and hotfix branches
  |/
  * 6e6c95e feat: 技术栈优化（Render 单容器、Celery 调优、CI 修复）
  ```

---

### Task 4: 验证合并结果

- [ ] **Step 1: 检查合并提交包含的预期变更**

  Run:
  ```bash
  git show --stat HEAD
  ```

  Expected:
  - 变更涉及 `.github/workflows/` 中的 CI 文件
  - 无业务代码变更

- [ ] **Step 2: 可选运行测试验证**

  Run:
  ```bash
  uv run pytest tests/ -q --tb=short
  ```

  Expected:
  - 测试通过或至少无由本次合并引入的失败

---

### Task 5: 推送 master

- [ ] **Step 1: 推送到远程**

  Run:
  ```bash
  git push origin master
  ```

  Expected:
  - 推送成功，显示计数增加

- [ ] **Step 2: 验证远程 master 已更新**

  Run:
  ```bash
  git log --oneline --decorate -1 origin/master
  ```

  Expected:
  - `origin/master` 指向新的合并提交

---

### Task 6: 清理无用本地分支

- [ ] **Step 1: 删除无新提交的分支**

  Run:
  ```bash
  git branch -d cleanup/legacy-debt
  git branch -d worktree-uat-2-prep
  ```

  Expected:
  - 两条命令均显示 `Deleted branch ...`

- [ ] **Step 2: 验证本地分支列表**

  Run:
  ```bash
  git branch
  ```

  Expected:
  - 仅保留 `master` 和 `feature/test-architecture-governance`

---

### Task 7: 清理远程 feature 分支（可选）

- [ ] **Step 1: 确认远程 feature 分支不再需要后删除**

  Run:
  ```bash
  git push origin --delete feature/test-architecture-governance
  ```

  Expected:
  - 删除成功提示

- [ ] **Step 2: 清理本地对该远程分支的追踪引用**

  Run:
  ```bash
  git fetch --prune origin
  ```

  Expected:
  - 显示 `[deleted]         origin/feature/test-architecture-governance`

---

## 回滚策略

若推送后发现合并异常，执行：

```bash
git revert -m 1 <merge-commit-hash>
git push origin master
```

其中 `<merge-commit-hash>` 为合并提交（`Merge branch 'feature/test-architecture-governance'`）的 hash。

---

## 自审

- **Spec coverage:** 设计文档中的同步 master、合并分支、验证、推送、清理步骤均已对应任务。
- **Placeholder scan:** 无 TBD/TODO，所有命令和预期输出均已给出。
- **Type consistency:** 不涉及类型定义。
- **Risk:** Task 7 为可选步骤，需用户确认后再执行。
