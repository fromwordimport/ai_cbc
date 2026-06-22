# CI/CD 流水线设计

> **版本**：v1.0
> **状态**：目标态设计文档，当前实现已拆分多个 workflow，部分章节（金丝雀、蓝绿、成本熔断、GitOps、Slack 通知）尚未落地，详见正文标注。
> **定位**：AI_CBC 项目完整的持续集成/持续交付流水线方案，覆盖代码提交到生产部署的全生命周期
> **负责人**：小维（DevOps/MLOps 工程师）
> **汇报对象**：小P（项目负责人）
> **依赖文档**：`docs/系统部署与运维架构.md`、`consumer-simulation/15-运维手册.md`、`docs/部署架构初步方案与实施路线图.md`、`docs/成本管控与预算模型.md`、`docs/Agent安全架构纲要.md`
> **配套文档**：`consumer-simulation/14-测试规范.md`

---

## 一、总体架构

### 1.1 流水线全景图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI_CBC CI/CD 流水线全景                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  代码提交阶段                    构建阶段                      测试阶段      │
│  ┌─────────────┐              ┌─────────────┐              ┌─────────────┐  │
│  │ Pre-commit  │              │ Docker构建  │              │ 单元测试    │  │
│  │ 分支保护    │─────────────→│ 安全扫描    │─────────────→│ 集成测试    │  │
│  │ 敏感信息    │              │ 镜像签名    │              │ E2E测试     │  │
│  │   扫描      │              │ SBOM生成    │              │ 偏见抽检    │  │
│  └─────────────┘              └─────────────┘              └──────┬──────┘  │
│         │                                                          │        │
│         │                    成本熔断检查点                         │        │
│         │              ┌─────────────────────────┐                 │        │
│         │              │ 部署前检查成本监控状态   │                 │        │
│         │              │ 熔断触发 → 阻断部署     │                 │        │
│         │              └─────────────────────────┘                 │        │
│         │                                                          ▼        │
│  配置管理阶段                  部署阶段                      监控阶段        │
│  ┌─────────────┐              ┌─────────────┐              ┌─────────────┐  │
│  │ Vault密钥   │              │ 环境分级    │              │ 健康检查    │  │
│  │ SealedSecret│              │ 蓝绿/金丝雀 │              │ Smoke Test  │  │
│  │ 环境变量    │              │ 自动回滚    │              │ 告警规则    │  │
│  └─────────────┘              └─────────────┘              └─────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 流水线设计原则

| 原则 | 说明 |
|------|------|
| **安全左移** | 安全扫描、偏见检测、成本检查在最早阶段介入，问题发现越早修复成本越低 |
| **质量门禁** | 每个阶段设置明确的通过/阻断标准，不达标不允许进入下一阶段 |
| **自动化优先** | 从代码提交到生产部署全程自动化，人工审批仅在关键节点 |
| **可观测性** | 每个阶段产出结构化日志和指标，支持快速定位问题 |
| **成本感知** | 部署前自动检查成本熔断状态，避免在预算紧张时引入新风险 |
| **快速反馈** | 前置轻量检查（秒级），后置重量检查（分钟级），失败时第一时间通知 |

---

## 二、代码提交阶段

### 2.1 分支策略

```
main (保护分支，仅接受PR合并)
  │
  ├─── release/v1.0.0 ──→ 生产部署
  │
  ├─── hotfix/security-patch ──→ 紧急修复
  │
  └─── feature/persona-batch-gen (开发者分支)
         │
         └─── feature/persona-cache-opt (子任务分支)
```

当前仓库主分支为 `master`，未来若迁移到 `main` 需同步更新 `.github/workflows/ci.yml` 触发分支。

| 分支类型 | 命名规范 | 来源 | 合并目标 | 生命周期 |
|---------|---------|------|---------|---------|
| `main` | — | — | — | 永久 |
| `feature/*` | `feature/{task-id}-{brief-desc}` | `main` | `main` | 合并后删除 |
| `hotfix/*` | `hotfix/{severity}-{desc}` | `main` | `main` + `release/*` | 合并后删除 |
| `release/*` | `release/v{major}.{minor}.{patch}` | `main` | — | 发布后保留标签 |

### 2.2 分支保护规则

```yaml
# .github/settings.yml 或 GitLab CI 配置
branch_protection:
  main:
    required_pull_request_reviews:
      required_approving_review_count: 2  # 至少2人审批
      dismiss_stale_reviews: true
      require_code_owner_reviews: true    # CODEOWNERS 文件指定 reviewer
    required_status_checks:
      strict: true
      contexts:
        - "quality-check"        # Stage 1 代码质量
        - "unit-test"            # Stage 3 单元测试
        - "security-scan"        # Stage 2 安全扫描
        - "integration-test"     # Stage 4 集成测试（main分支PR）
    restrictions:
      users: []  # 禁止直接push
      teams: ["maintainers"]
    require_linear_history: true
    allow_force_pushes: false
    allow_deletions: false
```

### 2.3 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key        # 检测私钥泄露
      - id: detect-aws-credentials     # 检测AWS凭证

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--strict, --ignore-missing-imports]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.7
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml", "-r", "src/"]
        additional_dependencies: ["bandit[toml]"]

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  - repo: local
    hooks:
      - id: commit-message-check
        name: Commit Message Check
        entry: scripts/check_commit_msg.py
        language: python
        stages: [commit-msg]
```

当前已实现 `.pre-commit-config.yaml`（ruff、ruff-format、mypy、bandit、通用 hooks），与 CI 门禁保持一致。

### 2.4 Commit Message 规范

```
类型(模块): 简短描述

详细描述（可选）

关联任务: TASK-123
关联文档: docs/CI-CD流水线设计.md
```

| 类型 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(persona): 支持批量画像生成` |
| `fix` | Bug修复 | `fix(api): 修复并发请求下的竞态条件` |
| `docs` | 文档更新 | `docs(deploy): 更新CI/CD流水线设计` |
| `test` | 测试相关 | `test(bias): 新增偏见检测单元测试` |
| `refactor` | 重构 | `refactor(model): 优化HB模型收敛速度` |
| `perf` | 性能优化 | `perf(cache): 画像缓存命中率提升30%` |
| `security` | 安全修复 | `security(auth): 修复JWT验证绕过漏洞` |
| `cost` | 成本优化 | `cost(routing): 优化模型路由降低20%费用` |

---

## 三、构建阶段

### 3.1 Docker 镜像构建

```dockerfile
# Dockerfile (多阶段构建)
# Stage 1: 依赖安装
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: 运行环境
FROM python:3.11-slim AS runtime

WORKDIR /app

# 创建非root用户
RUN groupadd -r aicbc && useradd -r -g aicbc aicbc

# 只复制必要的依赖
COPY --from=builder /root/.local /home/aicbc/.local
ENV PATH=/home/aicbc/.local/bin:$PATH

# 复制应用代码
COPY --chown=aicbc:aicbc src/ ./src/
COPY --chown=aicbc:aicbc config/ ./config/

# 安全：移除写权限
RUN chmod -R 555 /app/src /app/config

USER aicbc

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2 镜像构建策略

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| **多阶段构建** | 分离构建依赖和运行环境，减少镜像体积 | 所有服务 |
| **非root运行** | 容器内使用低权限用户 | 所有服务 |
| **层缓存优化** | 依赖层在前，代码层在后 | 所有服务 |
| **SBOM生成** | 每次构建生成软件物料清单 | 生产镜像 |
| **镜像签名** | 使用cosign对镜像进行签名 | 生产镜像 |

当前状态：多阶段构建、非 root、层缓存已落实；SBOM 生成与镜像签名尚未实现，作为后续安全加固项。

### 3.3 依赖安全扫描

```yaml
# .github/workflows/security-scan.yml
name: Security Scan

on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * 1'  # 每周一早2点

jobs:
  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run pip-audit
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --format=json --output=dependency-report.json

      - name: Run Safety CLI
        run: |
          pip install safety
          safety scan --json --output safety-report.json

      - name: Upload scan results
        uses: actions/upload-artifact@v4
        with:
          name: dependency-scan-results
          path: '*-report.json'

  container-scan:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4

      - name: Build image
        run: docker build -t aicbc/api:${{ github.sha }} .

      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'aicbc/api:${{ github.sha }}'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'  # 发现高危漏洞时阻断

      - name: Upload Trivy scan results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
```

### 3.4 镜像签名

```bash
#!/bin/bash
# scripts/sign-image.sh

IMAGE_TAG=$1
REGISTRY="registry.example.com"
IMAGE="${REGISTRY}/aicbc/api:${IMAGE_TAG}"

# 使用 cosign 签名镜像
cosign sign --key env://COSIGN_PRIVATE_KEY "${IMAGE}"

# 验证签名
cosign verify --key env://COSIGN_PUBLIC_KEY "${IMAGE}"

# 生成并附加 SBOM
syft "${IMAGE}" -o spdx-json > sbom.spdx.json
cosign attach sbom --sbom sbom.spdx.json "${IMAGE}"
```

### 3.5 构建阶段门禁

| 检查项 | 工具 | 阻断条件 | 报告位置 |
|--------|------|---------|---------|
| Python依赖漏洞 | pip-audit / Safety | 发现CRITICAL漏洞 | GitHub Security Tab |
| 容器镜像漏洞 | Trivy | 发现CRITICAL/HIGH漏洞 | SARIF → GitHub |
| 代码安全 | Bandit | 发现HIGH severity问题 | 流水线日志 |
| 密钥泄露 | detect-secrets / gitleaks | 发现未加密的密钥 | 流水线日志 |
| 镜像签名 | cosign | 签名失败 | 流水线日志 |
| SBOM生成 | syft | 生成失败 | Artifacts |

---

## 四、测试阶段

### 4.1 测试金字塔与触发策略

```
         /\
        /  \     E2E测试 (慢，覆盖核心场景)
       /____\       触发: 集成测试通过后 / nightly
      /      \     耗时: 10-20分钟
     /________\    数量: ~20个
    /          \   集成测试 (中速，覆盖接口契约)
   /____________\     触发: 单元测试通过后
  /              \   耗时: 5-10分钟
 /________________\  数量: ~50个
/                  \ 单元测试 (快速，覆盖业务逻辑)
/____________________\   触发: 每次代码提交
                       耗时: < 2分钟
                       数量: ~200个
```

### 4.2 自动化测试触发策略

| 测试层级 | 触发条件 | 并行度 | 超时 | 失败处理 |
|---------|---------|--------|------|---------|
| **单元测试** | 每次 `push` / `pull_request` | 全并行 | 5分钟 | 阻断流水线 |
| **集成测试** | 单元测试通过后 | 服务级并行 | 15分钟 | 阻断流水线 |
| **E2E测试** | 集成测试通过后 / 每晚2点 | 串行 | 30分钟 | 阻断流水线 |
| **偏见抽检** | 阶段2后启用，集成测试后 | 串行 | 20分钟 | 防御率<95%阻断 |
| **性能测试** | 每周六早4点 / release前 | 单线程 | 60分钟 | 告警但不阻断 |
| **安全测试** | 每晚3点 / release前 | 串行 | 40分钟 | 高危漏洞阻断 |

### 4.3 单元测试配置

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
addopts = "-v"
# Coverage is CI-only. To run locally: uv run pytest --cov=src --cov-report=term-missing
norecursedirs = [".git", ".tox", "dist", "build", "tests/performance", "tests/manual"]
markers = [
    "unit: pure unit tests with no external dependencies",
    "integration: tests requiring DB/Redis/Celery/API",
    "e2e: end-to-end full pipeline tests",
    "slow: tests taking >30s (deselect with '-m \"not slow\"')",
    "security: fast security validation tests",
    "redteam: slow adversarial/penetration/bias tests",
    "performance: load and regression tests",
    "external: tests requiring real external services (LLM/Mongo/Redis)",
]
```

### 4.4 集成测试配置

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  api-test:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - ENV=test
      - MONGODB_URL=mongodb://mongo:27017/aicbc_test
      - REDIS_URL=redis://redis:6379/1
      - LLM_API_KEY=${TEST_LLM_API_KEY}
    depends_on:
      - mongo
      - redis
    volumes:
      - ./test-results:/app/test-results

  mongo:
    image: mongo:6
    environment:
      - MONGO_INITDB_DATABASE=aicbc_test

  redis:
    image: redis:7-alpine

  # 集成测试执行器
  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    depends_on:
      - api-test
      - mongo
      - redis
    environment:
      - API_URL=http://api-test:8000
    volumes:
      - ./test-results:/app/test-results
    command: pytest tests/integration/ -v --junitxml=/app/test-results/integration.xml
```

当前状态：`docker-compose.test.yml` 尚未创建；集成测试与单元测试合并运行于 CI `fast-test` job，使用 `-m "(unit or integration) and not slow..."`。

### 4.5 测试报告归档

```yaml
# GitHub Actions 测试报告归档
- name: Publish Test Results
  uses: dorny/test-reporter@v1
  if: success() || failure()
  with:
    name: Test Results
    path: 'test-results/*.xml'
    reporter: java-junit

- name: Upload Coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml
    fail_ci_if_error: true
    verbose: true

- name: Archive Test Artifacts
  uses: actions/upload-artifact@v4
  with:
    name: test-results-${{ github.sha }}
    path: |
      test-results/
      coverage.xml
      htmlcov/
    retention-days: 30
```

### 4.6 测试阶段门禁

| 检查项 | 阈值 | 阻断条件 |
|--------|------|---------|
| 单元测试覆盖率 | ≥ 60% | < 60% |
| 单元测试通过率 | 100% | 任何失败 |
| 集成测试通过率 | 100% | 任何失败 |
| E2E测试通过率 | 100% | 任何失败 |
| 偏见检测防御率 | ≥ 95% | < 95%（阶段2后） |
| API P95延迟 | < 5秒 | ≥ 5秒 |
| 测试执行时间 | 单元<5min, 集成<15min | 超时 |

---

## 五、部署阶段

### 5.1 环境分级

```
开发环境 (dev)          预发环境 (staging)         生产环境 (production)
    │                        │                         │
    ▼                        ▼                         ▼
┌─────────┐            ┌─────────┐               ┌─────────┐
│ 1台服务器│            │ 2台服务器│               │ 3+台服务器│
│ 开发分支 │            │ main分支 │               │ release分支│
│ 自动部署 │            │ 自动部署 │               │ 人工审批+自动│
│ 无审批   │            │ 无审批   │               │ 需要审批   │
│ 数据隔离 │            │ 生产-like数据│           │ 生产数据   │
└─────────┘            └─────────┘               └─────────┘
    │                        │                         │
    └──→ 开发者验证 ──→  QA/UAT验证  ──→  业务验收 ───┘
```

| 环境 | 部署触发 | 审批 | 数据 | 可用性目标 |
|------|---------|------|------|-----------|
| `dev` | feature分支合并后自动 | 无需 | 模拟数据 | 无SLA |
| `staging` | main分支合并后自动 | 无需 | 脱敏生产数据 | 99% |
| `production` | release标签推送 | 小P审批 | 生产数据 | 99.5% |

### 5.2 蓝绿部署策略（MVP阶段 - Docker Compose）

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```bash
#!/bin/bash
# scripts/blue-green-deploy.sh

ENV=$1
VERSION=$2
BLUE="aicbc-api-blue"
GREEN="aicbc-api-green"
NGINX_CONF="/etc/nginx/conf.d/aicbc.conf"

# 确定当前运行的是蓝还是绿
current=$(docker-compose ps --filter "name=$BLUE" --format "{{.Name}}" | grep -q "$BLUE" && echo "blue" || echo "green")

if [ "$current" == "blue" ]; then
    target="$GREEN"
    target_port=8001
else
    target="$BLUE"
    target_port=8000
fi

echo "当前运行: $current, 目标部署: $target"

# 1. 部署新版本到目标环境
docker-compose up -d "$target" --no-deps

# 2. 健康检查
for i in {1..30}; do
    if curl -sf "http://localhost:$target_port/health"; then
        echo "健康检查通过"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "健康检查失败，回滚"
        docker-compose stop "$target"
        exit 1
    fi
    sleep 2
done

# 3. Smoke Test
if ! pytest tests/smoke/ --base-url="http://localhost:$target_port"; then
    echo "Smoke Test失败，回滚"
    docker-compose stop "$target"
    exit 1
fi

# 4. 切换流量（修改Nginx upstream）
sed -i "s/server localhost:800[01]/server localhost:$target_port/" "$NGINX_CONF"
nginx -s reload

# 5. 保留旧版本5分钟后停止（用于快速回滚）
(sleep 300 && docker-compose stop "$current") &

echo "部署完成: $target"
```

### 5.3 金丝雀发布策略（生产阶段 - Kubernetes）

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```yaml
# k8s/canary-deployment.yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: aicbc-api
  namespace: aicbc-prod
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: aicbc-api
  service:
    port: 8000
    gateways:
      - aicbc-gateway
    hosts:
      - api.aicbc.example.com
  analysis:
    interval: 1m
    threshold: 5           # 允许5次失败
    maxWeight: 50          # 最大50%流量给新版本
    stepWeight: 10         # 每次增加10%
    metrics:
      - name: request-success-rate
        thresholdRange:
          min: 99
        interval: 1m
      - name: request-duration
        thresholdRange:
          max: 500          # P99延迟 < 500ms
        interval: 1m
      - name: error-rate
        thresholdRange:
          max: 1            # 错误率 < 1%
        interval: 30s
    webhooks:
      - name: load-test
        type: pre-rollout
        url: http://flagger-loadtester.test/
        timeout: 30s
        metadata:
          cmd: "hey -z 2m -q 10 -c 2 http://api.aicbc.example.com/health"
      - name: smoke-test
        type: pre-rollout
        url: http://flagger-loadtester.test/
        timeout: 5m
        metadata:
          type: bash
          cmd: "pytest tests/smoke/ --base-url=http://api.aicbc.example.com"
      - name: cost-check
        type: pre-rollout
        url: http://cost-checker.aicbc-prod:8080/check
        timeout: 10s
        metadata:
          threshold: "0.95"  # 成本熔断检查
```

### 5.4 回滚机制

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

| 回滚场景 | 触发条件 | 回滚方式 | 回滚时间 |
|---------|---------|---------|---------|
| **自动回滚** | 金丝雀指标不达标（错误率>1%或P99>500ms） | Flagger自动切换流量 | < 30秒 |
| **自动回滚** | 健康检查连续失败3次 | K8s自动重启/回退 | < 1分钟 |
| **自动回滚** | Smoke Test失败 | 停止部署，保持当前版本 | 即时 |
| **自动回滚** | 成本熔断触发（预算≥100%） | 阻断部署 | 即时 |
| **手动回滚** | 人工发现线上问题 | `kubectl rollout undo` 或切换Nginx | < 2分钟 |
| **紧急回滚** | P1故障 | 直接切换至上一稳定镜像标签 | < 30秒 |

```bash
#!/bin/bash
# scripts/rollback.sh

ENV=$1
VERSION=$2

echo "开始回滚 $ENV 到上一版本..."

if [ "$ENV" == "k8s" ]; then
    # Kubernetes 回滚
    kubectl rollout undo deployment/aicbc-api -n aicbc-prod
    kubectl rollout status deployment/aicbc-api -n aicbc-prod --timeout=120s
elif [ "$ENV" == "compose" ]; then
    # Docker Compose 回滚
    docker-compose down
    docker-compose pull aicbc-api:$(cat .last_stable_version)
    docker-compose up -d
fi

# 验证回滚
curl -sf http://localhost:8000/health || exit 1

echo "回滚完成"
```

---

## 六、监控阶段

### 6.1 部署后自动化健康检查

```yaml
# .github/workflows/deploy.yml (健康检查步骤)
- name: Health Check After Deploy
  run: |
    # 存活检查
    for i in {1..30}; do
      status=$(curl -s -o /dev/null -w "%{http_code}" https://api.aicbc.example.com/health)
      if [ "$status" == "200" ]; then
        echo "存活检查通过"
        break
      fi
      if [ $i -eq 30 ]; then
        echo "存活检查失败"
        exit 1
      fi
      sleep 5
    done

    # 就绪检查（验证依赖服务）
    ready=$(curl -s https://api.aicbc.example.com/ready | jq -r '.status')
    if [ "$ready" != "ready" ]; then
      echo "就绪检查失败: $ready"
      exit 1
    fi

    # 关键业务接口检查
    curl -sf https://api.aicbc.example.com/api/v1/personas/health || exit 1
    curl -sf https://api.aicbc.example.com/api/v1/questionnaires/health || exit 1
    curl -sf https://api.aicbc.example.com/api/v1/analysis/health || exit 1

- name: Metrics Verification
  run: |
    # 验证Prometheus指标可采集
    curl -sf https://api.aicbc.example.com/metrics | grep "aicbc_api_requests_total" || exit 1
```

### 6.2 Smoke Test

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```python
# tests/smoke/test_critical_paths.py
import pytest
import requests

BASE_URL = "https://api.aicbc.example.com"

class TestCriticalPaths:
    """核心功能Smoke Test - 部署后必须全部通过"""

    def test_health_endpoint(self):
        """健康检查端点"""
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_ready_endpoint(self):
        """就绪检查端点"""
        resp = requests.get(f"{BASE_URL}/ready", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert all(v == "ok" for v in data["checks"].values())

    def test_persona_generation_flow(self):
        """画像生成核心流程"""
        # 创建研究
        study = requests.post(
            f"{BASE_URL}/api/v1/studies",
            json={"name": "smoke-test", "sample_size": 2, "choice_sets": 3}
        ).json()

        # 生成画像
        personas = requests.post(
            f"{BASE_URL}/api/v1/studies/{study['id']}/personas",
            json={"count": 2}
        ).json()
        assert len(personas) == 2
        assert all(p["authenticity_score"] >= 9 for p in personas)

    def test_cbc_questionnaire_flow(self):
        """CBC问卷核心流程"""
        resp = requests.get(f"{BASE_URL}/api/v1/questionnaires/sample")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["choice_sets"]) > 0
        assert data["d_efficiency"] >= 0.85

    def test_analysis_pipeline(self):
        """分析管线核心流程"""
        resp = requests.post(
            f"{BASE_URL}/api/v1/analysis/demo",
            json={"sample_size": 10}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["convergence"]["rhat_max"] < 1.1

    def test_cost_tracking(self):
        """成本追踪可用性"""
        resp = requests.get(f"{BASE_URL}/api/v1/cost/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_daily_cost" in data
        assert "budget_status" in data
```

### 6.3 部署后告警规则

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```yaml
# prometheus/alerting/deploy-alerts.yml
groups:
  - name: deployment_alerts
    rules:
      - alert: DeployHealthCheckFailed
        expr: |
          probe_success{job="deploy-health-check"} == 0
        for: 1m
        labels:
          severity: critical
          category: deployment
        annotations:
          summary: "部署后健康检查失败"
          description: "{{ $labels.instance }} 健康检查连续失败"
          action: "立即执行回滚"
          runbook_url: "https://wiki.aicbc.example.com/runbooks/deploy-failure"

      - alert: DeployErrorRateSpike
        expr: |
          (
            sum(rate(aicbc_api_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(aicbc_api_requests_total[5m]))
          ) > 0.05
        for: 2m
        labels:
          severity: critical
          category: deployment
        annotations:
          summary: "部署后错误率飙升"
          description: "5分钟错误率 {{ $value | humanizePercentage }}"
          action: "检查最近部署，考虑回滚"

      - alert: DeployLatencyRegression
        expr: |
          histogram_quantile(0.95,
            rate(aicbc_api_request_duration_seconds_bucket[10m])
          ) > 5
        for: 3m
        labels:
          severity: warning
          category: deployment
        annotations:
          summary: "部署后延迟回归"
          description: "P95延迟 {{ $value }}s，超过5秒阈值"
          action: "检查新代码性能影响"

      - alert: DeployAuthenticityScoreDrop
        expr: |
          aicbc_authenticity_score_average < 8
        for: 5m
        labels:
          severity: critical
          category: deployment
        annotations:
          summary: "部署后真实性评分下降"
          description: "当前平均分 {{ $value }}，低于阈值8"
          action: "检查Prompt变更影响，考虑回滚"

      - alert: DeployCostAnomaly
        expr: |
          (
            aicbc_cost_per_persona_cny
            /
            avg_over_time(aicbc_cost_per_persona_cny[1d])
          ) > 1.5
        for: 10m
        labels:
          severity: warning
          category: deployment
        annotations:
          summary: "部署后成本异常"
          description: "人均成本较基线上升 {{ $value | humanizePercentage }}"
          action: "检查新代码是否引入额外LLM调用"
```

### 6.4 部署通知模板

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```json
{
  "text": "AI_CBC 部署通知",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🚀 生产环境部署完成"
      }
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*版本:*\n`abc1234`"},
        {"type": "mrkdwn", "text": "*环境:*\nproduction"},
        {"type": "mrkdwn", "text": "*部署人:*\n小维"},
        {"type": "mrkdwn", "text": "*时间:*\n2026-06-09 14:30:00"}
      ]
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*健康检查:* ✅ 通过\n*Smoke Test:* ✅ 通过\n*成本状态:* 🟢 正常"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "查看日志"},
          "url": "https://grafana.aicbc.example.com/d/deploy"
        },
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "紧急回滚"},
          "style": "danger",
          "url": "https://ci.aicbc.example.com/rollback/abc1234"
        }
      ]
    }
  ]
}
```

---

## 七、配置管理

### 7.1 环境变量管理

```
配置层级（优先级从高到低）：

1. 运行时注入（K8s Secret / Docker Secret）
   └── LLM_API_KEY, DB_PASSWORD, JWT_SECRET

2. 环境特定配置（ConfigMap / 环境变量文件）
   └── .env.production, .env.staging, .env.dev

3. 应用默认配置（代码内嵌）
   └── config/default.yaml

4. 基础设施配置（IaC）
   └── terraform/ 或 k8s manifests/
```

| 配置类型 | 存储方式 | 示例 | 轮换策略 |
|---------|---------|------|---------|
| 密钥 | Vault / K8s Secret | `LLM_API_KEY` | 90天自动轮换 |
| 数据库连接 | Vault / K8s Secret | `MONGODB_URL` | 随密钥轮换 |
| 应用配置 | ConfigMap | `MAX_PERSONAS_PER_BATCH` | 随版本发布 |
| 功能开关 | ConfigMap / 配置中心 | `ENABLE_BATCH_SIMULATION` | 实时热更新 |
| 成本阈值 | ConfigMap | `COST_FUSE_THRESHOLD` | 小控审批后更新 |

### 7.2 密钥注入方案

#### 方案A：HashiCorp Vault（推荐用于生产）

```yaml
# k8s/vault-injection.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aicbc-api
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "aicbc-api"
        vault.hashicorp.com/agent-inject-secret-llm-api-key: "secret/data/aicbc/llm"
        vault.hashicorp.com/agent-inject-template-llm-api-key: |
          {{ with secret "secret/data/aicbc/llm" -}}
          export LLM_API_KEY="{{ .Data.data.api_key }}"
          {{- end }}
    spec:
      serviceAccountName: aicbc-api
      containers:
      - name: api
        image: aicbc/api:latest
```

#### 方案B：Sealed Secrets（推荐用于MVP）

```bash
# 1. 创建普通 Secret
cat <<EOF > secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: aicbc-secrets
  namespace: aicbc-prod
type: Opaque
stringData:
  LLM_API_KEY: "sk-xxx"
  MONGODB_URL: "mongodb://..."
EOF

# 2. 使用 kubeseal 加密
kubeseal --format=yaml < secret.yaml > sealed-secret.yaml

# 3. 提交加密后的文件到Git（安全）
git add sealed-secret.yaml

# 4. 删除原始Secret
rm secret.yaml
```

### 7.3 配置变更流程

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```
配置变更申请
    │
    ▼
┌─────────────┐
│ 1. 提交PR   │  变更内容 + 影响分析 + 回滚方案
│    (GitOps) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. 自动化   │  格式校验 + 敏感信息扫描
│    检查     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. 审批     │  密钥变更→小安审批；成本阈值→小控审批
│             │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 4. 自动部署 │  ArgoCD/GitOps Agent 同步
│             │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 5. 验证     │  健康检查 + Smoke Test
│             │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 6. 审计记录 │  变更日志归档
└─────────────┘
```

---

## 八、成本熔断集成

### 8.1 部署前成本检查

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```yaml
# .github/workflows/deploy.yml (成本检查步骤)
- name: Cost Circuit Breaker Check
  id: cost-check
  run: |
    # 查询成本熔断器状态
    COST_STATUS=$(curl -s \
      -H "Authorization: Bearer ${{ secrets.COST_API_TOKEN }}" \
      https://cost-monitor.aicbc.example.com/api/v1/status \
      | jq -r '.status')

    echo "成本熔断器状态: $COST_STATUS"
    echo "status=$COST_STATUS" >> $GITHUB_OUTPUT

    case $COST_STATUS in
      "NORMAL")
        echo "✅ 成本状态正常，继续部署"
        ;;
      "WARNING")
        echo "⚠️ 成本告警（80%），继续部署但发送通知"
        ;;
      "DEGRADE")
        echo "🛑 成本降级（95%），阻断部署"
        echo "当前处于成本降级状态，新部署可能加剧成本压力"
        exit 1
        ;;
      "FUSE"|"EMERGENCY")
        echo "🚨 成本熔断触发，严格阻断部署"
        exit 1
        ;;
      *)
        echo "❌ 无法获取成本状态，阻断部署"
        exit 1
        ;;
    esac

- name: Notify on Cost Warning
  if: steps.cost-check.outputs.status == 'WARNING'
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "⚠️ 部署时成本告警：当前费用已达预算80%，部署将继续但请关注成本趋势"
      }
```

### 8.2 成本熔断与部署的集成矩阵

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

| 熔断级别 | 状态码 | 部署行为 | 通知对象 | 自动动作 |
|---------|--------|---------|---------|---------|
| `NORMAL` | 正常 | 允许部署 | — | 无 |
| `WARNING` | 80%预算 | 允许部署 + 告警 | 小控、小P | 记录审计日志 |
| `DEGRADE` | 95%预算 | **阻断部署** | 小控、小P、小应 | 发送阻断通知 |
| `FUSE` | 100%预算 | **阻断部署** | 全员 | 发送紧急通知 |
| `EMERGENCY` | 120%预算 | **阻断部署 + 锁定** | 管理层 | 启动费用审计 |

### 8.3 部署后成本监控

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```python
# 部署后成本监控脚本 (scripts/post_deploy_cost_monitor.py)
import time
import requests
import sys

DEPLOY_ID = sys.argv[1]
DURATION_MINUTES = 30  # 部署后观察30分钟
CHECK_INTERVAL = 60    # 每分钟检查一次

def check_cost_anomaly():
    """检查部署后成本是否异常"""
    resp = requests.get("https://cost-monitor.aicbc.example.com/api/v1/metrics")
    data = resp.json()

    current_cost_per_persona = data["cost_per_persona_cny"]
    baseline = data["baseline_cost_per_persona_cny"]
    ratio = current_cost_per_persona / baseline

    if ratio > 1.5:
        # 成本较基线上升50%以上，触发告警
        requests.post("https://alert.aicbc.example.com/webhook", json={
            "alert": "DeployCostAnomaly",
            "deploy_id": DEPLOY_ID,
            "current_cost": current_cost_per_persona,
            "baseline": baseline,
            "ratio": ratio,
            "action": "建议检查新代码是否引入额外LLM调用"
        })
        return False
    return True

print(f"开始部署后成本监控，持续{DURATION_MINUTES}分钟...")
for i in range(DURATION_MINUTES):
    if not check_cost_anomaly():
        print(f"⚠️ 第{i}分钟发现成本异常")
    time.sleep(CHECK_INTERVAL)

print("部署后成本监控完成")
```

### 8.4 成本-部署闭环架构

当前状态：本节描述目标态能力，尚未在当前 workflow 中实现。

```
┌─────────────────────────────────────────────────────────────────┐
│                    成本-部署闭环                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐         ┌──────────┐         ┌──────────┐       │
│   │ 成本追踪  │         │ 熔断决策  │         │ 部署门禁  │       │
│   │ CostTracker│──────→│ Circuit  │──────→│ Deploy   │       │
│   │          │         │ Breaker  │         │ Gate     │       │
│   └──────────┘         └──────────┘         └────┬─────┘       │
│        │                                          │             │
│        │ 推送指标                                  │ 允许/阻断   │
│        ▼                                          ▼             │
│   ┌──────────┐                              ┌──────────┐       │
│   │Prometheus│                              │ CI/CD    │       │
│   │ 告警规则  │                              │ 流水线   │       │
│   └────┬─────┘                              └────┬─────┘       │
│        │                                          │             │
│        │ 触发告警                                  │ 执行部署    │
│        ▼                                          ▼             │
│   ┌──────────┐                              ┌──────────┐       │
│   │Alertmanager│                            │ K8s/Compose│      │
│   │          │                              │          │       │
│   └────┬─────┘                              └────┬─────┘       │
│        │                                          │             │
│        │ Webhook                                   │ 运行服务    │
│        ▼                                          ▼             │
│   ┌──────────┐                              ┌──────────┐       │
│   │ 模型降级  │◄─────────────────────────────│ 质量回传  │       │
│   │ Model    │   真实性评分变化              │ (真实性) │       │
│   │ Router   │                               │          │       │
│   └──────────┘                               └──────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 九、完整流水线配置

### 9.1 GitHub Actions 完整流水线

```yaml
# .github/workflows/ci-cd-pipeline.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, release/*, hotfix/*]
  pull_request:
    branches: [main]

env:
  REGISTRY: registry.example.com
  IMAGE_NAME: aicbc/api

jobs:
  # ═══════════════════════════════════════════════════════════
  # Stage 0: 前置检查
  # ═══════════════════════════════════════════════════════════
  preflight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Check branch naming
        run: |
          BRANCH=${GITHUB_REF#refs/heads/}
          if [[ ! "$BRANCH" =~ ^(main|release/.*|hotfix/.*|feature/.*)$ ]]; then
            echo "❌ 分支命名不符合规范: $BRANCH"
            exit 1
          fi

      - name: Check commit message format
        run: |
          git log --format=%s -n 1 | grep -E "^(feat|fix|docs|test|refactor|perf|security|cost)\(.+\): .+" || {
            echo "❌ Commit message 不符合规范"
            exit 1
          }

      - name: Scan for secrets
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: main
          head: HEAD
          extra_args: --debug --only-verified

  # ═══════════════════════════════════════════════════════════
  # Stage 1: 代码质量
  # ═══════════════════════════════════════════════════════════
  quality:
    runs-on: ubuntu-latest
    needs: preflight
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint with ruff
        run: ruff check src/ --output-format=github

      - name: Format check with ruff
        run: ruff format --check src/

      - name: Type check with mypy
        run: mypy src/ --strict --ignore-missing-imports

      - name: Security scan with bandit
        run: bandit -r src/ -f json -o bandit-report.json || true

  # ═══════════════════════════════════════════════════════════
  # Stage 2: 安全扫描
  # ═══════════════════════════════════════════════════════════
  security:
    runs-on: ubuntu-latest
    needs: preflight
    steps:
      - uses: actions/checkout@v4

      - name: Dependency vulnerability scan
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --desc --format=json -o pip-audit.json

      - name: Container image scan (build first)
        run: docker build -t test-image:${{ github.sha }} .

      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'test-image:${{ github.sha }}'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'

      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v2
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'

  # ═══════════════════════════════════════════════════════════
  # Stage 3: 单元测试
  # ═══════════════════════════════════════════════════════════
  unit-test:
    runs-on: ubuntu-latest
    needs: quality
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          pytest tests/unit/ \
            -v \
            --cov=src \
            --cov-report=xml \
            --cov-report=html \
            --cov-fail-under=60 \
            --junitxml=test-results/unit.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: true

      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: unit-test-results
          path: |
            test-results/
            coverage.xml
            htmlcov/

  # ═══════════════════════════════════════════════════════════
  # Stage 4: 集成测试
  # ═══════════════════════════════════════════════════════════
  integration-test:
    runs-on: ubuntu-latest
    needs: [unit-test, security]
    steps:
      - uses: actions/checkout@v4

      - name: Start test environment
        run: |
          docker-compose -f docker-compose.test.yml up -d
          sleep 30  # 等待服务启动

      - name: Run integration tests
        run: |
          docker-compose -f docker-compose.test.yml exec -T test-runner \
            pytest tests/integration/ -v --junitxml=/app/test-results/integration.xml

      - name: Cleanup
        if: always()
        run: docker-compose -f docker-compose.test.yml down -v

      - name: Upload integration results
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-results
          path: test-results/integration.xml

  # ═══════════════════════════════════════════════════════════
  # Stage 5: 偏见与安全抽检（阶段2后启用）
  # ═══════════════════════════════════════════════════════════
  bias-security-sample:
    runs-on: ubuntu-latest
    needs: integration-test
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/heads/release/')
    steps:
      - uses: actions/checkout@v4

      - name: Run red team test sample
        run: |
          python -m pytest tests/security/ \
            -k "redteam" \
            --sample-rate=0.1 \
            --junitxml=test-results/redteam.xml

      - name: Check defense rate
        run: |
          DEFENSE_RATE=$(python scripts/check_defense_rate.py test-results/redteam.xml)
          if (( $(echo "$DEFENSE_RATE < 0.95" | bc -l) )); then
            echo "❌ 红队防御率 $DEFENSE_RATE < 95%，阻断发布"
            exit 1
          fi
          echo "✅ 红队防御率 $DEFENSE_RATE >= 95%"

  # ═══════════════════════════════════════════════════════════
  # Stage 6: 构建与推送
  # ═══════════════════════════════════════════════════════════
  build:
    runs-on: ubuntu-latest
    needs: [integration-test, bias-security-sample]
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/heads/release/')
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
      image_digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USER }}
          password: ${{ secrets.REGISTRY_PASSWORD }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=,suffix=,format=short
            type=ref,event=branch
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          sbom: true
          provenance: true

      - name: Sign image with cosign
        uses: sigstore/cosign-installer@v3
      - run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}

  # ═══════════════════════════════════════════════════════════
  # Stage 7: 部署
  # ═══════════════════════════════════════════════════════════
  deploy-staging:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment:
      name: staging
      url: https://staging.aicbc.example.com
    steps:
      - uses: actions/checkout@v4

      - name: Cost circuit breaker check
        id: cost-check
        run: |
          STATUS=$(curl -s https://cost-monitor.aicbc.example.com/api/v1/status | jq -r '.status')
          echo "status=$STATUS" >> $GITHUB_OUTPUT
          if [[ "$STATUS" == "DEGRADE" || "$STATUS" == "FUSE" || "$STATUS" == "EMERGENCY" ]]; then
            echo "❌ 成本熔断触发，阻断部署: $STATUS"
            exit 1
          fi

      - name: Deploy to staging
        run: |
          sed -i "s|{IMAGE_TAG}|${{ github.sha }}|g" k8s/staging/*.yaml
          kubectl apply -f k8s/staging/ -n aicbc-staging

      - name: Wait for rollout
        run: |
          kubectl rollout status deployment/aicbc-api -n aicbc-staging --timeout=120s

      - name: Smoke test staging
        run: |
          sleep 10
          pytest tests/smoke/ --base-url=https://staging.aicbc.example.com -v

  deploy-production:
    runs-on: ubuntu-latest
    needs: [build, deploy-staging]
    if: startsWith(github.ref, 'refs/heads/release/')
    environment:
      name: production
      url: https://api.aicbc.example.com
    steps:
      - uses: actions/checkout@v4

      - name: Cost circuit breaker check
        id: cost-check
        run: |
          STATUS=$(curl -s https://cost-monitor.aicbc.example.com/api/v1/status | jq -r '.status')
          echo "status=$STATUS" >> $GITHUB_OUTPUT
          if [[ "$STATUS" != "NORMAL" && "$STATUS" != "WARNING" ]]; then
            echo "❌ 成本状态不允许部署: $STATUS"
            exit 1
          fi

      - name: Deploy to production (Canary)
        run: |
          sed -i "s|{IMAGE_TAG}|${{ github.sha }}|g" k8s/production/*.yaml
          kubectl apply -f k8s/production/ -n aicbc-prod

      - name: Wait for canary promotion
        run: |
          # Flagger会自动处理金丝雀发布
          kubectl wait canary/aicbc-api -n aicbc-prod --for=condition=promoted --timeout=600s

      - name: Post-deploy smoke test
        run: |
          pytest tests/smoke/ --base-url=https://api.aicbc.example.com -v

      - name: Post-deploy cost monitoring
        run: |
          python scripts/post_deploy_cost_monitor.py ${{ github.sha }} &

      - name: Notify team
        uses: slackapi/slack-github-action@v1
        with:
          payload: |
            {
              "text": "🚀 AI_CBC 生产环境已部署\n版本: ${{ github.sha }}\n成本状态: ${{ steps.cost-check.outputs.status }}\n部署人: ${{ github.actor }}"
            }
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}

  # ═══════════════════════════════════════════════════════════
  # Stage 8: 通知与审计
  # ═══════════════════════════════════════════════════════════
  notify:
    runs-on: ubuntu-latest
    needs: [deploy-staging, deploy-production]
    if: always()
    steps:
      - name: Record deployment
        run: |
          cat <<EOF > deploy-record.json
          {
            "deploy_id": "${{ github.run_id }}",
            "commit_sha": "${{ github.sha }}",
            "branch": "${{ github.ref }}",
            "actor": "${{ github.actor }}",
            "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            "status": "${{ needs.deploy-production.result || needs.deploy-staging.result }}",
            "cost_status": "${{ steps.cost-check.outputs.status || 'unknown' }}",
            "image": "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}"
          }
          EOF
          # 写入审计日志系统
          curl -X POST https://audit.aicbc.example.com/api/v1/deployments \
            -H "Authorization: Bearer ${{ secrets.AUDIT_TOKEN }}" \
            -d @deploy-record.json
```

---

## 十、流水线运行视图

### 10.1 成功流程

```
开发者 push feature/persona-cache-opt
    │
    ▼
┌─────────────────────────────────────────┐
│ Stage 0: 前置检查                        │
│ ✅ 分支命名规范                          │
│ ✅ Commit message 格式                   │
│ ✅ 无敏感信息泄露                        │
└────────────────────┬────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐     ┌────────┐      ┌────────┐
│ Stage 1│     │ Stage 2│      │ Stage 3│
│ 代码质量│     │ 安全扫描│      │ 单元测试│
│ ✅ ruff │     │ ✅ Trivy│      │ ✅ 覆盖率│
│ ✅ mypy │     │ ✅ pip-audit│  │   65%  │
│ ✅ bandit│    │ ✅ Bandit│     │ ✅ 全部通过│
└────┬───┘     └────┬───┘      └───┬────┘
     │              │              │
     └──────────────┼──────────────┘
                    ▼
            ┌──────────────┐
            │ Stage 4: 集成测试│
            │ ✅ API E2E    │
            │ ✅ 数据流测试  │
            │ ✅ 成本熔断测试│
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Stage 5: 偏见抽检│
            │ ✅ 红队10%抽样 │
            │ ✅ 防御率 97%  │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Stage 6: 构建推送│
            │ ✅ 镜像构建    │
            │ ✅ 签名完成    │
            │ ✅ SBOM生成   │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Stage 7: 部署  │
            │ ✅ 成本检查通过│
            │ ✅ 金丝雀发布  │
            │ ✅ Smoke Test │
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │ Stage 8: 通知  │
            │ ✅ Slack通知  │
            │ ✅ 审计记录   │
            └──────────────┘
```

### 10.2 失败处理流程

| 失败阶段 | 通知方式 | 处理人 | 处理时限 | 回滚动作 |
|---------|---------|--------|---------|---------|
| 前置检查 | PR评论 | 开发者 | 即时 | 修复后重新push |
| 代码质量 | PR评论 + Slack | 开发者 | 即时 | 修复后重新push |
| 安全扫描 | PR评论 + Slack @小安 | 开发者+小安 | 2小时 | 修复漏洞后重新push |
| 单元测试 | PR评论 + Slack | 开发者 | 即时 | 修复测试后重新push |
| 集成测试 | Slack + 邮件 | 开发者+小测 | 4小时 | 定位问题后重新触发 |
| 偏见抽检 | Slack @全员 | 小伦+小应 | 8小时 | 修复偏见问题后重新触发 |
| 构建失败 | Slack + 邮件 | 小维 | 2小时 | 修复构建后重新触发 |
| 部署失败 | 电话 + Slack @全员 | 小维+小端 | 15分钟 | 自动回滚至上一版本 |
| 部署后异常 | 电话 + PagerDuty | 值班人员 | 5分钟 | 手动或自动回滚 |

---

## 十一、与其他文档的衔接

| 本文档章节 | 衔接文档 | 衔接点 |
|-----------|---------|--------|
| 构建阶段 | `consumer-simulation/15-运维手册.md` | Docker Compose部署方式 |
| 部署阶段 | `docs/系统部署与运维架构.md` | K8s manifests和部署策略 |
| 实施路线图 | `docs/部署架构初步方案与实施路线图.md` | 阶段化落地计划 |
| 成本熔断集成 | `docs/成本管控与预算模型.md` | CostCircuitBreaker接口和阈值 |
| 安全扫描 | `docs/Agent安全架构纲要.md` | 红队测试用例和安全门禁 |
| 测试阶段 | `consumer-simulation/14-测试规范.md` | 测试策略和验收标准 |
| 监控告警 | `consumer-simulation/15-运维手册.md` | 告警规则和SOP |
| 密钥管理 | `docs/数据隐私与合规指南.md` | 密钥轮换和审计要求 |

---

## 十二、附录

### 附录A：流水线前置条件清单

| 前置条件 | 交付物 | 负责人 | 目标时间 |
|---------|--------|--------|---------|
| 代码仓库初始化 | GitHub仓库 + 分支保护 | 小端 | 阶段1 Week 1 |
| 项目结构标准化 | `src/`、`tests/`、`docker/`、`k8s/` | 小端 | 阶段1 Week 1 |
| 依赖管理 | `requirements.txt`、`pyproject.toml` | 小端 | 阶段1 Week 1 |
| 容器化基线 | `Dockerfile`、`.dockerignore` | 小维 | 阶段1 Week 2 |
| 测试框架 | pytest + 首个单元测试通过 | 小测 | 阶段1 Week 2 |
| 代码质量工具 | ruff、mypy、pre-commit | 小维 | 阶段1 Week 2 |
| 镜像仓库 | 私有Registry或云镜像仓库 | 小维 | 阶段1 Week 2 |
| CI/CD基线 | GitHub Actions跑通到Stage 4 | 小维 | 阶段1 Week 3 |
| 成本监控API | CostCircuitBreaker HTTP接口 | 小控 | 阶段1 Week 4 |
| 安全测试用例 | 红队测试脚本（≥10%抽样） | 小安 | 阶段2 Week 2 |

### 附录B：工具链选型

| 类别 | 工具 | 版本 | 用途 | 替代方案 |
|------|------|------|------|---------|
| 代码托管 | GitHub | — | 仓库、PR、Actions | GitLab |
| CI/CD | GitHub Actions | — | 流水线编排 | GitLab CI、Jenkins |
| Lint | ruff | ≥0.3.0 | Python代码检查 | flake8、pylint |
| 类型检查 | mypy | ≥1.9.0 | 静态类型检查 | pyright |
| 安全扫描 | Bandit | ≥1.7.0 | Python安全 | — |
| 依赖扫描 | pip-audit / Safety | 最新 | 依赖漏洞 | Snyk |
| 容器扫描 | Trivy | ≥0.49 | 镜像漏洞 | Clair |
| 镜像签名 | cosign | ≥2.2 | 镜像签名验证 | Notary |
| SBOM生成 | syft | ≥1.0 | 软件物料清单 | — |
| 密钥检测 | detect-secrets / truffleHog | 最新 | 密钥泄露 | git-secrets |
| 测试框架 | pytest | ≥7.0 | 单元/集成测试 | unittest |
| 覆盖率 | pytest-cov | ≥4.0 | 覆盖率统计 | coverage.py |
| 容器编排 | Kubernetes | ≥1.28 | 生产部署 | Docker Swarm |
| GitOps | ArgoCD | ≥2.9 | 持续部署 | Flux |
| 金丝雀 | Flagger | ≥1.35 | 渐进式发布 | Argo Rollouts |
| 密钥管理 | Vault / Sealed Secrets | 最新 | 密钥注入 | 云KMS |
| 通知 | Slack | — | 团队通知 | 钉钉、企业微信 |

### 附录C：版本历史

| 日期 | 版本 | 变更内容 | 负责人 |
|------|------|---------|--------|
| 2026-06-09 | v1.0 | 初始版本，覆盖7大阶段完整流水线设计 | 小维 |

---

*本文档由小维编制，作为AI_CBC项目CI/CD实施的执行依据。*
*所有流水线配置以此为准，变更需经小P审批。*
