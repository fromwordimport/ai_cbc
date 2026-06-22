# 本地 CI/CD 门禁设计方案

> **版本**：v1.0
> **定位**：在本地跑通核心 CI/CD 门禁后再推送到 GitHub Actions，降低 Actions 额度消耗
> **负责人**：小维（DevOps/MLOps 工程师）
> **汇报对象**：小P（项目负责人）
> **依赖文档**：`docs/CI-CD流水线设计.md`、`docker/CLAUDE.md`、`scripts/CLAUDE.md`
> **配套文档**：`docs/测试/PC本地运行指南.md`
> **状态**：待实施

---

## 一、背景与目标

### 1.1 背景

当前项目处于快速开发期，每次 push/PR 都会触发 GitHub Actions 的 `ci.yml`，包含 7 个 job：

- `preflight`：分支命名、commit message、密钥扫描
- `quality`：ruff、mypy、bandit
- `security`：pip-audit、Docker build、Trivy 镜像扫描
- `fast-test`：pytest 单元/集成测试（覆盖率 ≥60%）
- `redteam-fast`：红队快速测试（防御率 ≥95%）
- `frontend`：TypeScript 检查、Vitest、构建、npm audit
- `validate-k8s`：K8s 清单校验

在快速迭代阶段，频繁提交导致 GitHub Actions 额度消耗较大。

### 1.2 目标

- **本地先跑通**：开发者在本机完成大部分 CI 门禁检查，通过后再 push
- **降低 Actions 额度**：减少因格式、lint、测试失败导致的无效 GitHub Actions 运行
- **保持与 CI 一致**：本地检查逻辑与 `.github/workflows/ci.yml` 保持一致，避免"本地过、线上挂"
- **分层触发**：commit 前轻量、push 前较全、手动跑完整

### 1.3 成功标准

| 标准 | 说明 |
|------|------|
| 本地可通过率 ≥90% | push 到 GitHub 前，本地 CI 已拦截常见失败 |
| 与 CI 行为一致 | 相同代码在本地和 GitHub Actions 上结果一致 |
| 新增 <5 分钟 overhead | pre-push 完整轻量门禁在普通开发机上 ≤5 分钟 |
| 不改变现有 CI | GitHub Actions workflow 保持运行，作为最终门禁 |

---

## 二、总体架构

### 2.1 组件图

```
┌─────────────────────────────────────────────────────────────────┐
│                      本地 CI/CD 门禁架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   触发层                                                          │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐  │
│   │ commit-msg  │   │ pre-commit  │   │ pre-push            │  │
│   │ 校验格式     │   │ 轻量 lint   │   │ local_ci.py --fast  │  │
│   └─────────────┘   └─────────────┘   └─────────────────────┘  │
│           │                │                    │              │
│           └────────────────┴────────────────────┘              │
│                            │                                    │
│                            ▼                                    │
│   编排层        ┌─────────────────────┐                         │
│                │  scripts/local_ci.py │                         │
│                │  - lint              │                         │
│                │  - test              │                         │
│                │  - security          │                         │
│                │  - frontend          │                         │
│                │  - k8s               │                         │
│                │  - all               │                         │
│                └─────────────────────┘                         │
│                            │                                    │
│           ┌────────────────┼────────────────┐                  │
│           ▼                ▼                ▼                  │
│   工具层  ruff/mypy   pytest/vitest   pip-audit/bandit        │
│           ▼                ▼                ▼                  │
│   报告层  local-ci-reports/...  （与 CI artifacts 同名）        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 路径 | 职责 |
|------|------|------|
| 本地 CI 编排器 | `scripts/local_ci.py` | 统一入口，调度各 stage，生成报告 |
| commit message 校验 | `scripts/check_commit_msg.py` | 复用 CI 的 conventional commit 校验逻辑 |
| pre-commit hooks | `.pre-commit-config.yaml` | commit-msg、pre-commit、pre-push 三层门禁 |
| 使用指南 | `docs/本地CI使用指南.md` | 安装、运行、跳过参数、故障排查 |
| 报告目录 | `local-ci-reports/` | 本地报告输出，与 GitHub Actions artifacts 同名 |

---

## 三、门禁分级

### 3.1 触发时机与范围

| 场景 | 触发方式 | 包含阶段 | 预计耗时 |
|------|---------|---------|---------|
| commit-msg | 每次 `git commit` | commit 格式校验 | <1s |
| pre-commit | 每次 `git commit` | ruff check、ruff format、bandit、通用 hooks | <30s |
| pre-push | 每次 `git push` | `local_ci.py all --fast`：lint、fast-test、frontend、pip-audit、secrets | 2-5min |
| 手动完整检查 | `uv run scripts/local_ci.py all` | 全部（含 Trivy、K8s、redteam） | 5-15min |

### 3.2 `--fast` 模式详细范围

```bash
uv run scripts/local_ci.py all --fast
```

执行以下 stage：

1. `preflight`：分支命名、commit message、TruffleHog 密钥扫描
2. `lint`：ruff check、ruff format、mypy、bandit
3. `test`：pytest fast 子集（`-m "(unit or integration) and not slow and not redteam and not performance and not smoke"`），覆盖率 ≥60%
4. `redteam`：pytest redteam 快速子集（`-m "security and not slow"`），防御率 ≥95%
5. `frontend`：npm ci、tsc、vitest with coverage、npm run build、npm audit
6. `security`：pip-audit（HIGH/CRITICAL 阻断）

不执行：

- Docker build
- Trivy 镜像扫描
- K8s 清单校验

### 3.3 `--full` 模式详细范围

```bash
uv run scripts/local_ci.py all
```

在 `--fast` 基础上增加：

1. `docker-build`：`docker build -f docker/Dockerfile -t aicbc-scan:local .`
2. `trivy`：对 `aicbc-scan:local` 执行 CRITICAL/HIGH 扫描
3. `k8s`：运行 `scripts/validate_k8s_manifests.py`（纯 Python 静态校验，无需 kubectl/kustomize）

需要本地安装 Docker（用于镜像构建和 Trivy 扫描）。

---

## 四、CLI 设计

### 4.1 命令结构

```bash
uv run scripts/local_ci.py [command] [options]
```

### 4.2 子命令

| 子命令 | 说明 |
|--------|------|
| `lint` | ruff + format + mypy + bandit |
| `test` | pytest fast 子集 |
| `redteam` | redteam 快速子集 |
| `frontend` | 前端检查 |
| `security` | pip-audit + bandit |
| `k8s` | K8s 清单校验 |
| `all` | 全部 stage（默认 `--fast`） |

### 4.3 选项

| 选项 | 说明 |
|------|------|
| `--fast` | 跳过 Docker/Trivy/K8s（pre-push 默认） |
| `--full` | 跑全部 stage |
| `--fail-fast` | 第一个失败 stage 立即退出 |
| `--verbose`, `-v` | 输出详细日志 |
| `--skip-trivy` | 跳过 Trivy |
| `--skip-tests` | 跳过 pytest |
| `--skip-frontend` | 跳过前端 |
| `--skip-k8s` | 跳过 K8s |
| `--skip-pip-audit` | 跳过 pip-audit |
| `--skip-redteam` | 跳过红队测试 |
| `--skip-secrets` | 跳过密钥扫描 |
| `--report-dir` | 报告输出目录（默认 `local-ci-reports`） |

### 4.4 使用示例

```bash
# 手动跑完整本地 CI
uv run scripts/local_ci.py all

# push 前跑轻量门禁（与 pre-push hook 行为一致）
uv run scripts/local_ci.py all --fast --fail-fast

# 仅跑 lint
uv run scripts/local_ci.py lint

# 跳过前端和镜像扫描
uv run scripts/local_ci.py all --skip-frontend --skip-trivy
```

---

## 五、pre-commit hooks 设计

### 5.1 更新后的 `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.18
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/PyCQA/bandit
    rev: 1.9.4
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml", "-r", "src/", "--severity-level", "high"]
        additional_dependencies: ["bandit[toml]"]
        pass_filenames: false

  - repo: local
    hooks:
      - id: commit-message-check
        name: Commit Message Check
        entry: uv run python scripts/check_commit_msg.py
        language: system
        stages: [commit-msg]
        pass_filenames: true

      - id: local-ci-fast
        name: Local CI Fast Gate
        entry: uv run python scripts/local_ci.py all --fast --fail-fast
        language: system
        stages: [pre-push]
        pass_filenames: false
        always_run: true
```

### 5.2 hook 行为说明

| Hook | 阶段 | 失败时 |
|------|------|--------|
| `commit-message-check` | commit-msg | 阻止 commit 创建 |
| `ruff`、`ruff-format`、`bandit`、通用 hooks | pre-commit | 阻止 commit 创建 |
| `local-ci-fast` | pre-push | 阻止 push 执行 |

---

## 六、环境检测与错误处理

### 6.1 环境检测

`local_ci.py` 启动时检测以下工具：

| 工具 | 用途 | 缺失时行为 |
|------|------|-----------|
| `uv` | Python 依赖与虚拟环境 | 报错退出，提示安装 uv |
| `npm` | 前端构建与测试 | 跳过 frontend stage，输出警告 |
| `docker` | 镜像构建与 Trivy | `--fast` 模式下不检测；`--full` 模式下跳过 docker/trivy |
| `kubectl`/`kustomize` | 高级 K8s 校验（可选） | 当前 `validate_k8s_manifests.py` 不依赖；如未来扩展则按需检测 |
| `trufflehog` | 密钥扫描 | 未安装时跳过并提示从 [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) 下载二进制 |

### 6.2 错误汇总

默认模式：收集所有 stage 结果，最后统一输出：

```
========================================
Local CI Summary
========================================
preflight   ✅  1.2s
lint        ✅  12.3s
test        ❌  45.6s  (3 failed)
frontend    ✅  28.9s
security    ✅  15.4s
----------------------------------------
Result: FAILED
code: 1
Report dir: local-ci-reports/
```

`--fail-fast` 模式：第一个失败 stage 立即退出并返回非零码。

### 6.3 跳过机制

- 通过 `--skip-*` 参数显式跳过指定 stage
- 跳过原因会记录在 summary 中
- pre-push hook 使用 `--fail-fast`，不支持默认跳过，避免滥用

---

## 七、报告输出

### 7.1 目录结构

```
local-ci-reports/
├── preflight/
│   └── trufflehog.json
├── lint/
│   ├── bandit-report.json
│   └── mypy-report.txt
├── test/
│   ├── fast.xml
│   ├── coverage.xml
│   └── htmlcov/
├── redteam/
│   └── redteam-fast.xml
├── frontend/
│   ├── npm-audit.json
│   └── coverage/
├── security/
│   └── pip-audit.json
├── docker/
│   └── build.log
├── trivy/
│   └── trivy-results.sarif
└── k8s/
    └── k8s-validation.log
```

### 7.2 与 CI artifacts 对齐

本地报告文件名尽量与 GitHub Actions 上传的 artifacts 一致，方便对比。

---

## 八、与 GitHub Actions 的对应关系

| 本地 Stage | 对应 CI Job | 对应 workflow 步骤 |
|-----------|------------|-------------------|
| `preflight` | `preflight` | branch 命名、commit message、TruffleHog |
| `lint` | `quality` | ruff check/format、mypy、bandit |
| `test` | `fast-test` | pytest fast 子集、覆盖率 |
| `redteam` | `redteam-fast` | pytest redteam 快速子集、防御率检查 |
| `frontend` | `frontend` | npm ci、tsc、vitest、build、npm audit |
| `security` | `security` | pip-audit |
| `docker-build` + `trivy` | `security` | Docker build、Trivy scan |
| `k8s` | `validate-k8s` | validate_k8s_manifests.py |

---

## 九、依赖与前置条件

### 9.1 开发环境

- Python ≥3.11
- uv ≥0.4
- Node.js ≥20
- npm ≥10
- Git

### 9.2 完整模式额外需要

- Docker Desktop 或 dockerd（用于镜像构建和 Trivy 扫描）

### 9.3 安装 pre-commit hooks

```bash
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg
```

---

## 十、测试验证

### 10.1 本地 CI 自身测试

| 测试 | 路径 | 说明 |
|------|------|------|
| 单元测试 | `tests/unit/test_local_ci.py` | 参数解析、stage 调度、跳过逻辑 |
| 集成测试 | `tests/integration/test_local_ci_integration.py` | 真实调用 ruff 并校验返回码 |
| hooks 验证 | 手动 | 安装 hooks 后验证 commit-msg 和 pre-push 拦截 |

### 10.2 不修改现有测试

根据 `CLAUDE.md` 要求，不修改 `tests/` 或 `frontend/src/__tests__/` 下的现有测试文件。仅新增本地 CI 相关测试（若实施，会单独征求用户授权）。

---

## 十一、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| pre-push 太慢 | 开发者绕过 hooks | `--fast` 模式控制在 5 分钟内；提供 `--skip-*` 参数 |
| 本地与 CI 环境不一致 | 本地过、线上挂 | 复用 CI 相同命令和阈值；报告同名便于对比 |
| 新成员不安装 hooks | 失去本地门禁意义 | 在 `docs/本地CI使用指南.md` 中强调安装步骤 |
| Docker 未安装导致 full 模式不可用 | 完整检查无法本地跑 | 默认 `--fast` 模式；指南中提供 Docker 安装链接 |
| secrets 扫描误报 | 正常提交被拦截 | TruffleHog 使用 `--only-verified`，与 CI 一致 |

---

## 十二、实施范围

### 12.1 本次实施

1. 新增 `scripts/local_ci.py`
2. 新增/更新 `scripts/check_commit_msg.py`
3. 更新 `.pre-commit-config.yaml`
4. 新增 `docs/本地CI使用指南.md`
5. 更新 `docs/文档索引与导航.md`

### 12.2 不修改

- `.github/workflows/ci.yml` 保持不变
- `.github/workflows/cd-staging.yml` 保持不变
- `.github/workflows/cd-production.yml` 保持不变
- 现有测试文件保持不变

---

## 十三、变更日志

| 日期 | 版本 | 变更内容 | 负责人 |
|------|------|---------|--------|
| 2026-06-22 | v1.0 | 初始版本，确定本地 CI/CD 门禁架构与实施方案 | 小维 |

---

*本文档由小维编制，作为 AI_CBC 项目本地 CI/CD 门禁的实施依据。*
*变更需经小P审批。*
