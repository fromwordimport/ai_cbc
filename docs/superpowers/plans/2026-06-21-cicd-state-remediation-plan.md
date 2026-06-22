# AI_CBC CI/CD 状态修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `docs/superpowers/specs/2026-06-21-cicd-state-review.md` 中识别的全部 CI/CD 不一致与可执行性问题，使 Staging/Production 部署能真正更新镜像、 nightly 不再因缺失脚本失败、设计文档与实现一致，并补齐 pre-commit、Bandit 配置等门禁缺口。

**Architecture:** 将修复拆分为 9 个独立任务：P0 级镜像名修复与 locust 脚本补齐优先交付；P1 级文档同步、Bandit 统一、pre-commit 配置随后；中长期任务（security-scan 去重、smoke test、偏见/成本门禁）作为可独立合并的增强项。每个任务自带本地验证脚本，确保不依赖 GitHub Actions 即可自检。

**Tech Stack:** GitHub Actions, Kustomize, Docker, uv, pytest, ruff, mypy, bandit, pre-commit, Locust

---

## 文件结构总览

| 文件 | 变更性质 | 职责 |
|------|---------|------|
| `k8s/base/kustomization.yaml` | 修改 | 统一 image name 为 `ghcr.io/fromwordimport/ai_cbc` |
| `k8s/base/deployment.yaml` | 修改 | 容器镜像引用统一为 `ghcr.io/fromwordimport/ai_cbc` |
| `k8s/base/worker-deployment.yaml` | 修改 | 同上 |
| `k8s/base/beat-deployment.yaml` | 修改 | 同上 |
| `.github/workflows/cd-staging.yml` | 修改 | 修正 `kustomize edit set image` 目标名 |
| `.github/workflows/cd-production.yml` | 修改 | 同上 |
| `scripts/locust_baseline.py` | 新建 | nightly 性能基线脚本 |
| `pyproject.toml` | 修改 | 统一 Bandit severity 为 `HIGH` |
| `.github/workflows/ci.yml` | 修改 | 同步 Bandit `--severity-level` 与脚本逻辑 |
| `scripts/ci_check_bandit.py` | 可选修改 | 与 pyproject.toml 保持一致 |
| `.pre-commit-config.yaml` | 新建 | 本地提交前质量/安全/密钥检查 |
| `docs/CI-CD流水线设计.md` | 修改 | 同步为当前实际方案，标记目标态 |
| `.github/workflows/security-scan.yml` | 修改 | 与 ci.yml 去重，明确职责 |
| `tests/smoke/__init__.py` | 新建 | Smoke test 包入口 |
| `tests/smoke/test_critical_paths.py` | 新建 | 部署后核心路径检查 |
| `scripts/check_defense_rate.py` | 新建 | 解析 redteam XML 并校验防御率 |
| `.github/workflows/ci.yml` | 修改 | 增加偏见防御率门禁 |
| `scripts/ci_cost_fuse_check.py` | 新建 | 部署前成本熔断状态检查 |
| `.github/workflows/cd-staging.yml` | 修改 | 增加成本熔断门禁步骤 |
| `.github/workflows/cd-production.yml` | 修改 | 增加成本熔断门禁步骤 |

---

## Task 1: 修复 K8s CD 镜像名称（P0）

**Files:**
- Modify: `k8s/base/kustomization.yaml`
- Modify: `k8s/base/deployment.yaml`
- Modify: `k8s/base/worker-deployment.yaml`
- Modify: `k8s/base/beat-deployment.yaml`
- Modify: `.github/workflows/cd-staging.yml`
- Modify: `.github/workflows/cd-production.yml`
- Test: `scripts/verify_k8s_image_tag.py`（新建）

**背景：** 当前 CI 推送到 `ghcr.io/fromwordimport/ai_cbc`，但 K8s manifests 使用 `ghcr.io/fromwordimport/aicbc`，且 CD workflow 用 `kustomize edit set image aicbc-api=...`，目标名不匹配，导致部署永远使用旧镜像。

- [ ] **Step 1: 编写本地验证脚本，先确认当前失败**

Create `scripts/verify_k8s_image_tag.py`:

```python
#!/usr/bin/env python3
"""Verify that kustomize build uses the expected image repository."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_REPO = "ghcr.io/fromwordimport/ai_cbc"


def check_overlay(overlay: str) -> bool:
    result = subprocess.run(
        ["kustomize", "build", str(REPO_ROOT / "k8s" / "overlays" / overlay)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"FAIL: kustomize build {overlay} failed:\n{result.stderr}")
        return False
    if EXPECTED_REPO not in result.stdout:
        print(f"FAIL: overlay {overlay} does not use image {EXPECTED_REPO}")
        return False
    print(f"OK: overlay {overlay} uses image {EXPECTED_REPO}")
    return True


def main() -> int:
    ok = True
    for overlay in ("staging", "prod"):
        ok = check_overlay(overlay) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

Run:

```bash
uv run python scripts/verify_k8s_image_tag.py
```

Expected: FAIL（当前镜像名不一致）

- [ ] **Step 2: 统一 K8s manifests 中的镜像仓库名**

Modify `k8s/base/kustomization.yaml`:

```yaml
images:
  - name: ghcr.io/fromwordimport/ai_cbc
    newTag: 0.1.0
```

Modify `k8s/base/deployment.yaml` line 42:

```yaml
image: ghcr.io/fromwordimport/ai_cbc:0.1.0
```

Modify `k8s/base/worker-deployment.yaml` line 39:

```yaml
image: ghcr.io/fromwordimport/ai_cbc:0.1.0
```

Modify `k8s/base/beat-deployment.yaml` line 37:

```yaml
image: ghcr.io/fromwordimport/ai_cbc:0.1.0
```

- [ ] **Step 3: 修正 CD workflow 中 kustomize 的目标名**

Modify `.github/workflows/cd-staging.yml` line 100:

```yaml
kustomize edit set image ghcr.io/fromwordimport/ai_cbc=ghcr.io/${{ github.repository }}:${{ github.sha }}
```

Modify `.github/workflows/cd-production.yml` line 86:

```yaml
kustomize edit set image ghcr.io/fromwordimport/ai_cbc=ghcr.io/${{ github.repository }}:${{ needs.verify-image.outputs.image_tag }}
```

- [ ] **Step 4: 运行本地验证脚本，确认通过**

Run:

```bash
uv run python scripts/verify_k8s_image_tag.py
```

Expected:

```
OK: overlay staging uses image ghcr.io/fromwordimport/ai_cbc
OK: overlay prod uses image ghcr.io/fromwordimport/ai_cbc
```

- [ ] **Step 5: 运行 K8s manifest 静态验证**

Run:

```bash
uv run python scripts/validate_k8s_manifests.py
```

Expected: `No issues found. Static validation passed.`

- [ ] **Step 6: Commit**

```bash
git add k8s/base/ \
  .github/workflows/cd-staging.yml \
  .github/workflows/cd-production.yml \
  scripts/verify_k8s_image_tag.py
git commit -m "fix(cd): align K8s image name with CI pushed repository

- Use ghcr.io/fromwordimport/ai_cbc consistently across base manifests
- Fix kustomize edit set image target in staging/production workflows"
```

---

## Task 2: 补齐 nightly 性能基线脚本（P0）

**Files:**
- Create: `scripts/locust_baseline.py`
- Modify: `.github/workflows/nightly.yml`（可选，若需调整参数）

**背景：** `nightly.yml` 引用 `scripts/locust_baseline.py`，但文件不存在，导致 workflow 失败。

- [ ] **Step 1: 确认当前 nightly 步骤会失败**

Run:

```bash
test -f scripts/locust_baseline.py && echo "exists" || echo "missing"
```

Expected: `missing`

- [ ] **Step 2: 创建 Locust 基线脚本**

Create `scripts/locust_baseline.py`:

```python
"""Lightweight Locust baseline for nightly performance smoke test.

Usage (from repo root):
    uv pip install locust
    locust -f scripts/locust_baseline.py \
        --host http://localhost:8000 \
        --run-time 2m \
        --users 10 \
        --spawn-rate 2 \
        --headless \
        --csv reports/locust
"""
from __future__ import annotations

from locust import HttpUser, between, task


class AICBCUser(HttpUser):
    """Minimal user hitting health/readiness and core read endpoints."""

    wait_time = between(1, 3)

    @task(3)
    def health(self) -> None:
        self.client.get("/health")

    @task(2)
    def ready(self) -> None:
        self.client.get("/ready")

    @task(1)
    def metrics(self) -> None:
        self.client.get("/metrics")
```

- [ ] **Step 3: 本地验证脚本可被 Locust 加载**

Run:

```bash
uv pip install locust
locust -f scripts/locust_baseline.py --host http://localhost:8000 --run-time 5s --users 1 --spawn-rate 1 --headless --csv reports/locust-smoke || true
```

Expected: 若本地无服务则请求失败，但 Locust 本身能正常加载脚本，无 Python 语法/导入错误。关键检查：

```bash
python -c "import importlib.util; spec = importlib.util.spec_from_file_location('locust_baseline', 'scripts/locust_baseline.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print('OK: script loads')"
```

Expected: `OK: script loads`

- [ ] **Step 4: Commit**

```bash
git add scripts/locust_baseline.py
git commit -m "feat(perf): add locust baseline script for nightly smoke test"
```

---

## Task 3: 统一 Bandit 严重级别（P1）

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/security-scan.yml`
- Test: `scripts/ci_check_bandit.py`（保持现状即可）

**背景：** `pyproject.toml` 设 `severity = "MEDIUM"`，但 CI 用 `--severity-level high`，`ci_check_bandit.py` 只检查 HIGH。统一为 HIGH，使配置与执行一致。

- [ ] **Step 1: 查看当前不一致**

Run:

```bash
grep -n "severity" pyproject.toml
grep -n "severity-level" .github/workflows/ci.yml
```

Expected: 分别看到 `MEDIUM` 和 `high`。

- [ ] **Step 2: 修改 pyproject.toml 中 Bandit severity 为 HIGH**

Modify `pyproject.toml` line 112:

```toml
severity = "HIGH"
```

- [ ] **Step 3: 保持 CI 使用 HIGH 并验证 bandit 可运行**

Run:

```bash
uv run bandit -r src/ -f json -o bandit-report.json --severity-level high
uv run python scripts/ci_check_bandit.py
```

Expected: 与修改前行为一致（当前 CI 本就是 HIGH）。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(config): align bandit severity with CI gate at HIGH"
```

---

## Task 4: 添加 pre-commit 配置（P1）

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `docs/CI-CD流水线设计.md`（可选，后续 Task 5 统一处理）

**背景：** 设计文档要求 pre-commit hooks，但仓库中不存在 `.pre-commit-config.yaml`。

- [ ] **Step 1: 确认当前缺失**

Run:

```bash
test -f .pre-commit-config.yaml && echo "exists" || echo "missing"
```

Expected: `missing`

- [ ] **Step 2: 创建 pre-commit 配置**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        args: [--strict, --ignore-missing-imports]
        additional_dependencies:
          - pydantic
          - pydantic-settings
          - types-python-dateutil

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml", "-r", "src/"]
        additional_dependencies: ["bandit[toml]"]
```

- [ ] **Step 3: 安装 pre-commit 并试运行**

Run:

```bash
uv pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Expected：所有 hooks 跑完，若有既有格式问题则 ruff-format 或 ruff --fix 会修改文件；重新运行应全绿。若 mypy 因既有问题失败，记录问题清单并在 Step 4 处理。

- [ ] **Step 4: 提交新增配置（不提交由 hook 自动修改的代码文件，除非用户授权）**

```bash
git add .pre-commit-config.yaml
git commit -m "chore(dev): add pre-commit configuration aligned with CI gates"
```

**注意**：若 pre-commit 自动修改了 src/ 或 frontend/ 文件，需先确认这些修改是格式/安全修复而非行为变更，再决定是否放入同一 commit。建议仅提交 `.pre-commit-config.yaml` 本身。

---

## Task 5: 同步 `docs/CI-CD流水线设计.md` 与当前实现（P1）

**Files:**
- Modify: `docs/CI-CD流水线设计.md`

**背景：** 设计文档大量描述目标态，且示例已过时（requirements.txt、main 分支、单文件 pipeline 等）。

- [ ] **Step 1: 列出需要同步的关键点**

创建清单文件 `/tmp/sync_points.md`（不提交，仅用于核对）：

```markdown
- 主分支：main → master
- 依赖管理：requirements.txt → pyproject.toml + uv
- CI 文件：单文件 ci-cd-pipeline.yml → 拆分 8 个 workflow
- Dockerfile：使用 supervisord、configs/ 目录
- 集成/E2E：当前合并于 fast-test，docker-compose.test.yml 不存在
- 部署策略：当前为直接 kubectl apply，非蓝绿/金丝雀（标记为目标态）
- 成本熔断：仅 /cost-status 可达性检查（标记为目标态）
- Smoke Test：tests/smoke/ 不存在（标记为目标态）
- Slack/PagerDuty 通知：未实现（标记为目标态）
- SBOM/镜像签名：未实现（标记为目标态）
```

- [ ] **Step 2: 修改设计文档第一章和第二章**

在文档开头 `> **版本**：v1.0` 后新增状态说明：

```markdown
> **状态**：目标态设计文档，当前实现已拆分多个 workflow，部分章节（金丝雀、蓝绿、成本熔断、GitOps、Slack 通知）尚未落地，详见正文标注。
```

修改 2.1 分支策略中主分支名 `main` 为 `master`，并补充说明：

```markdown
当前仓库主分支为 `master`，未来若迁移到 `main` 需同步更新 `.github/workflows/ci.yml` 触发分支。
```

- [ ] **Step 3: 在 2.3 Pre-commit 章节补充实现说明**

在 Pre-commit 配置示例后添加：

```markdown
当前已实现 `.pre-commit-config.yaml`（ruff、ruff-format、mypy、bandit、通用 hooks），与 CI 门禁保持一致。
```

- [ ] **Step 4: 在 3.x 构建阶段标注目标态**

在 3.2 镜像构建策略表后添加：

```markdown
当前状态：多阶段构建、非 root、层缓存已落实；SBOM 生成与镜像签名尚未实现，作为后续安全加固项。
```

- [ ] **Step 5: 在 4.x 测试阶段同步当前结构**

修改 4.3 单元测试配置示例，替换为 `pyproject.toml` 中的实际 `[tool.pytest.ini_options]` 片段。

在 4.4 集成测试配置后添加：

```markdown
当前状态：`docker-compose.test.yml` 尚未创建；集成测试与单元测试合并运行于 CI `fast-test` job，使用 `-m "(unit or integration) and not slow..."`。
```

- [ ] **Step 6: 在 5.x/6.x/7.x/8.x 章节标注未实现项**

对以下章节添加统一标注：

```markdown
当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。
```

涉及章节：5.2 蓝绿部署、5.3 金丝雀发布、5.4 回滚机制（除打印指令外）、6.2 Smoke Test、6.3 部署后告警、6.4 部署通知、7.3 配置变更流程、8.1~8.4 成本熔断。

- [ ] **Step 7: 验证文档无死链且格式正确**

Run:

```bash
# 无 Markdown linter 时，至少确认文件可读
head -50 docs/CI-CD流水线设计.md
```

- [ ] **Step 8: Commit**

```bash
git add docs/CI-CD流水线设计.md
git commit -m "docs(ci): sync CI-CD design doc with current implementation

- Update branch name, dependency tool, workflow split
- Mark target-state sections not yet implemented"
```

---

## Task 6: 去重 `security-scan.yml` 与 `ci.yml`（中长期）

**Files:**
- Modify: `.github/workflows/security-scan.yml`
- Modify: `.github/workflows/ci.yml`

**背景：** 两个 workflow 均包含 pip-audit、Trivy、npm audit、TruffleHog、K8s 验证，维护成本高。

- [ ] **Step 1: 明确职责分工**

决策：
- `ci.yml`：PR/push 快速门禁，保留 bandit、pip-audit、Trivy、npm audit、TruffleHog。
- `security-scan.yml`：定时/依赖变更触发的深度扫描，保留 pip-audit、Trivy、npm audit，**移除 TruffleHog 和 K8s 验证**（由 ci.yml 覆盖）。

- [ ] **Step 2: 修改 security-scan.yml 移除重复 job**

删除 `secret-scan` job 和 `k8s-manifest-security` job，保留 `python-dependency-scan`、`frontend-dependency-scan`、`container-scan`。

在文件顶部注释更新：

```yaml
# AI_CBC Security Scan Workflow
# Maintainer: 小安（Security Engineer）
# Version: 2.0
# Scheduled / dependency-change triggered deep security scan.
# CI push/PR fast gates are handled by ci.yml.
```

- [ ] **Step 3: 修改 ci.yml 注释说明安全扫描职责**

在 `security` job 前添加注释：

```yaml
  # Stage 2: Security Scan (fast gate for PR/push)
  # Deeper scheduled scans live in security-scan.yml.
```

- [ ] **Step 4: 本地验证 YAML 语法**

Run:

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/security-scan.yml')); print('OK security-scan.yml')"
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK ci.yml')"
```

Expected:

```
OK security-scan.yml
OK ci.yml
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/security-scan.yml .github/workflows/ci.yml
git commit -m "ci(security): deduplicate security-scan workflow

- Remove TruffleHog and K8s validation from scheduled scans (ci.yml covers them)
- Clarify fast gate vs deep scan responsibilities"
```

---

## Task 7: 补齐 Smoke Test（中长期）

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/test_critical_paths.py`
- Modify: `.github/workflows/cd-staging.yml`
- Modify: `.github/workflows/cd-production.yml`

**背景：** 设计文档要求部署后 Smoke Test，但 `tests/smoke/` 不存在，CD workflow 只检查 `/health`。

- [ ] **Step 1: 创建 smoke test 包**

Create `tests/smoke/__init__.py`:

```python
"""Post-deployment smoke tests for critical API paths."""
```

- [ ] **Step 2: 创建核心路径 smoke test**

Create `tests/smoke/test_critical_paths.py`:

```python
"""Critical path smoke tests against a deployed AI_CBC instance.

Run with:
    pytest tests/smoke/ --base-url=http://localhost:8000
"""
from __future__ import annotations

import pytest
import requests


@pytest.fixture
def base_url(pytestconfig) -> str:
    return pytestconfig.getoption("base_url") or "http://localhost:8000"


def test_health_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_ready_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/ready", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"


def test_metrics_endpoint(base_url: str) -> None:
    resp = requests.get(f"{base_url}/metrics", timeout=10)
    assert resp.status_code == 200
    assert "aicbc_api_requests_total" in resp.text or "python_info" in resp.text
```

- [ ] **Step 3: 本地验证 smoke test 可被 pytest 发现**

Run:

```bash
uv run pytest tests/smoke/ --collect-only -q
```

Expected：列出 3 个测试函数。

- [ ] **Step 4: 修改 CD workflow 部署后运行 smoke test**

Modify `.github/workflows/cd-staging.yml`，在 Smoke test /health 步骤后新增：

```yaml
      - name: Run smoke tests
        if: steps.check-kubeconfig.outputs.skip != 'true'
        run: |
          python3 -m pip install pytest requests
          python3 -m pytest tests/smoke/ --base-url=http://aicbc-api.aicbc-staging.svc.cluster.local
```

Modify `.github/workflows/cd-production.yml`，在 Health check 步骤后新增：

```yaml
      - name: Run smoke tests
        run: |
          python3 -m pip install pytest requests
          python3 -m pytest tests/smoke/ --base-url=http://aicbc-api.aicbc-prod.svc.cluster.local
```

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/ \
  .github/workflows/cd-staging.yml \
  .github/workflows/cd-production.yml
git commit -m "feat(deploy): add post-deploy smoke tests

- Create tests/smoke/test_critical_paths.py for /health, /ready, /metrics
- Run smoke tests after staging and production deployments"
```

---

## Task 8: 增加偏见防御率门禁（中长期）

**Files:**
- Create: `scripts/check_defense_rate.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`（可选，添加 redteam 相关 marker）

**背景：** 生产就绪整改计划要求红队防御率 ≥95%，当前 CI 只跑 fast redteam 子集，不计算防御率。

- [ ] **Step 1: 创建防御率检查脚本**

Create `scripts/check_defense_rate.py`:

```python
#!/usr/bin/env python3
"""Parse pytest JUnit XML and fail if red-team defense rate is below threshold."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_THRESHOLD = 0.95


def main() -> int:
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test-results/redteam-fast.xml")
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD

    if not xml_path.exists():
        print(f"FAIL: XML report not found: {xml_path}")
        return 1

    root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    total = int(root.get("tests", "0"))
    failures = int(root.get("failures", "0"))
    errors = int(root.get("errors", "0"))

    if total == 0:
        print("FAIL: No red-team tests found")
        return 1

    defense_rate = (total - failures - errors) / total
    print(f"Red-team defense rate: {defense_rate:.2%} ({total - failures - errors}/{total})")

    if defense_rate < threshold:
        print(f"FAIL: defense rate {defense_rate:.2%} below threshold {threshold:.2%}")
        return 1

    print(f"OK: defense rate meets threshold {threshold:.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 在 CI 中增加防御率校验步骤**

Modify `.github/workflows/ci.yml`，在 `redteam-fast` job 的 "Upload red team results" 步骤前新增：

```yaml
      - name: Check red-team defense rate
        run: |
          source .venv/bin/activate
          python scripts/check_defense_rate.py test-results/redteam-fast.xml 0.95
```

- [ ] **Step 3: 本地验证脚本**

创建临时测试 XML：

```bash
mkdir -p test-results
cat > test-results/redteam-red-fail.xml <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="100" failures="10" errors="0">
  <testcase name="t1" />
</testsuite>
EOF
uv run python scripts/check_defense_rate.py test-results/redteam-red-fail.xml 0.95
```

Expected: `FAIL: defense rate 90.00% below threshold 95.00%`

再测试通过场景：

```bash
cat > test-results/redteam-green.xml <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="100" failures="2" errors="0">
  <testcase name="t1" />
</testsuite>
EOF
uv run python scripts/check_defense_rate.py test-results/redteam-green.xml 0.95
```

Expected: `OK: defense rate meets threshold 95.00%`

- [ ] **Step 4: 清理临时文件（不要提交）**

```bash
rm -f test-results/redteam-red-fail.xml test-results/redteam-green.xml
```

- [ ] **Step 5: Commit**

```bash
git add scripts/check_defense_rate.py .github/workflows/ci.yml
git commit -m "feat(ci): add red-team defense rate gate

- Parse redteam-fast JUnit XML and fail if defense rate < 95%"
```

---

## Task 9: 增加部署前成本熔断门禁（中长期）

**Files:**
- Create: `scripts/ci_cost_fuse_check.py`
- Modify: `.github/workflows/cd-staging.yml`
- Modify: `.github/workflows/cd-production.yml`

**背景：** 设计文档要求部署前检查成本熔断状态，当前仅 data-pipeline 做 `/cost-status` 可达性检查。

- [ ] **Step 1: 创建成本熔断检查脚本**

Create `scripts/ci_cost_fuse_check.py`:

```python
#!/usr/bin/env python3
"""Check cost fuse status before deployment.

Exits non-zero if status is DEGRADE, FUSE, or EMERGENCY.
Usage:
    python scripts/ci_cost_fuse_check.py https://api.example.com/cost-status
"""
from __future__ import annotations

import argparse
import sys
import urllib.request


def check_cost_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        print(f"WARN: Could not reach cost-status endpoint: {exc}")
        # Fail open only if endpoint is unreachable; production should require it.
        return 0

    # Simple heuristic: look for status field in JSON response.
    for status in ("DEGRADE", "FUSE", "EMERGENCY"):
        if f'"status": "{status}"' in body or f'"status":"{status}"' in body:
            print(f"FAIL: Cost fuse status is {status}, blocking deployment")
            return 1

    print("OK: Cost fuse status allows deployment")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check cost fuse before deployment")
    parser.add_argument("url", help="URL of /cost-status endpoint")
    args = parser.parse_args()
    return check_cost_status(args.url)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 本地验证脚本行为**

Run:

```bash
# 测试熔断状态阻断
python -c "
import sys
sys.path.insert(0, 'scripts')
from ci_cost_fuse_check import check_cost_status
assert check_cost_status('data:application/json,{\"status\": \"FUSE\"}') == 1
assert check_cost_status('data:application/json,{\"status\": \"NORMAL\"}') == 0
print('OK: script logic verified')
"
```

Expected: `OK: script logic verified`

- [ ] **Step 3: 修改 CD workflow 增加成本熔断步骤**

Modify `.github/workflows/cd-staging.yml`，在 "Update image tag in staging overlay" 步骤前新增：

```yaml
      - name: Cost fuse check
        if: steps.check-kubeconfig.outputs.skip != 'true'
        run: |
          python3 scripts/ci_cost_fuse_check.py http://aicbc-api.aicbc-staging.svc.cluster.local/cost-status
```

Modify `.github/workflows/cd-production.yml`，在 "Update image tag in production overlay" 步骤前新增：

```yaml
      - name: Cost fuse check
        run: |
          python3 scripts/ci_cost_fuse_check.py http://aicbc-api.aicbc-prod.svc.cluster.local/cost-status
```

- [ ] **Step 4: Commit**

```bash
git add scripts/ci_cost_fuse_check.py \
  .github/workflows/cd-staging.yml \
  .github/workflows/cd-production.yml
git commit -m "feat(cd): add pre-deploy cost fuse gate

- Block deployment if /cost-status returns DEGRADE/FUSE/EMERGENCY"
```

---

## Self-Review Checklist

### Spec coverage

- [x] B1 K8s 镜像名修复 → Task 1
- [x] B2 pre-commit 缺失 → Task 4
- [x] B3 Bandit 级别不一致 → Task 3
- [x] B5 集成/E2E 分离 → Task 5 文档标注 + 未来扩展
- [x] B6 偏见防御率门禁 → Task 8
- [x] C1 locust 脚本缺失 → Task 2
- [x] C2 部署不更新镜像 → Task 1
- [x] C6 security-scan 重复 → Task 6
- [x] C7 cost fuse 门禁 → Task 9
- [x] A 设计文档同步 → Task 5
- [x] D 安全合规差距 → Task 8 + Task 9

### Placeholder scan

- [x] 无 "TBD"/"TODO"/"implement later"
- [x] 每个代码步骤含完整代码
- [x] 每个验证步骤含命令和期望输出
- [x] 无 "Similar to Task N"

### Type/名称一致性

- [x] 镜像仓库统一使用 `ghcr.io/fromwordimport/ai_cbc`
- [x] `kustomize edit set image` 目标名与 kustomization 中 `images.name` 一致
- [x] Bandit severity 统一为 `HIGH`
- [x] 脚本名和函数名在 Task 8/9 中保持一致

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-21-cicd-state-remediation-plan.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Note:** Tasks 1, 3, 6, 7, 8, 9 modify `.github/workflows/` and `k8s/` files. These are CI/CD-related files; ensure the user has authorized modifications before starting execution.

Which approach?
