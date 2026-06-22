# AI_CBC CI/CD 流程与项目状态一致性审查报告

> **版本**：v1.0
> **日期**：2026-06-21
> **审查范围**：`.github/workflows/` 全部 workflow、`docker/`、`k8s/`、`pyproject.toml`、`frontend/package.json`、`docs/CI-CD流水线设计.md`、`docs/生产就绪评估/` 整改要求
> **审查方式**：静态配置比对 + 本地可执行验证（未修改任何 CI/CD 文件）
> **负责人**：小维（DevOps/MLOps）/ 小测（QA）协同复核

---

## 一、执行摘要

本次审查对 AI_CBC 项目当前 8 个 GitHub Actions workflow、容器构建产物、K8s 编排、前后端测试配置与 `docs/CI-CD流水线设计.md` 及生产就绪整改要求进行了逐项比对。

**核心结论**：

- **CI 阶段基本可用**：代码质量（ruff/mypy/bandit）、依赖/镜像安全扫描（pip-audit/Trivy/npm audit）、密钥扫描（TruffleHog）、fast test、前端构建测试均已配置。
- **CD 阶段存在严重缺陷**：由于 K8s 镜像名称与 CI 推送名称不匹配，且 `kustomize edit set image` 目标名错误，Staging/Production 实际无法部署新构建的镜像。
- **设计文档与现状差距大**：`docs/CI-CD流水线设计.md` 大量章节描述的是目标态（金丝雀、蓝绿、成本熔断、GitOps、Smoke Test、Slack 通知），尚未在当前 workflow 中落地，且部分示例代码已过时。
- **生产就绪关键门禁缺失**：红队防御率、偏见审计、成本熔断均未在 CI/CD 中作为可阻断门禁验证。

**当前状态判定**：CI/CD 流程**不满足生产就绪要求**，在未修复 CD 镜像名错误等关键问题前，不应承担生产发布职责。

---

## 二、审查维度与优先级

按用户指定优先级：**B（与代码/项目结构匹配度）> C（可执行性）> A（与设计文档一致性）> D（安全与合规差距）**。

---

## 三、B. 与当前代码/项目结构的匹配度

### 3.1 严重不匹配

| 编号 | 问题 | 实际状态 | 影响 |
|------|------|---------|------|
| B1 | **K8s 镜像名称与 CI 推送不一致，且 `kustomize edit set image` 目标名错误** | CI 推送到 `ghcr.io/fromwordimport/ai_cbc:<sha>`；K8s manifests / kustomization 使用 `ghcr.io/fromwordimport/aicbc:0.1.0`；CD workflow 执行 `kustomize edit set image aicbc-api=...` | `aicbc-api` 与 kustomization 中的 image name 不匹配，kustomize 不会替换任何容器镜像。Staging/Production 永远部署旧镜像 `ghcr.io/fromwordimport/aicbc:0.1.0`，新构建不会生效 |
| B2 | **`.pre-commit-config.yaml` 缺失** | `pyproject.toml` 含 `pre-commit` 依赖，`docs/CI-CD流水线设计.md` 明确配置 pre-commit hooks，仓库中不存在该文件 | 本地提交阶段无法执行设计文档要求的 ruff/mypy/bandit/detect-secrets 等 hooks |

### 3.2 部分不一致 / 配置漂移

| 编号 | 问题 | 实际状态 | 影响 |
|------|------|---------|------|
| B3 | **Bandit 严重级别与 `pyproject.toml` 配置不一致** | `pyproject.toml` 设 `severity = "MEDIUM"`；CI 用 `--severity-level high`，且 `ci_check_bandit.py` 只检查 `HIGH` | 实际门禁比项目配置宽松，中等级别问题不会被阻断 |
| B4 | **mypy 处于“继续执行”状态** | CI 中 `continue-on-error: true`，并标注 `TODO(#51)` | 类型检查不阻断合并，与设计文档“质量门禁”原则有差距 |
| B5 | **CI 未独立运行集成/E2E 测试** | `fast-test` job 合并运行 `-m "(unit or integration) and not slow..."`；无单独 `integration-test` / `e2e` job | 与设计文档 4.2/9.1 中“集成测试在单元测试通过后单独阶段”不一致，且 E2E 完全缺失 |
| B6 | **CI 未验证 6 条公平性硬规则 / 偏见防御率** | 红队 fast job 只跑 `security and not slow` 测试，不计算或校验防御率 | 生产就绪整改计划要求偏见防御率 ≥95%，当前 CI 无对应门禁 |
| B7 | **主分支名为 `master`，设计文档写 `main`** | `.github/workflows/ci.yml` 触发分支为 `master`；设计文档全篇使用 `main` | 文档与实际仓库不一致，但不会导致运行失败 |

### 3.3 已落实的匹配项

- `docker/Dockerfile` 路径、多阶段构建、非 root 用户、`HEALTHCHECK` 与 `docker/CLAUDE.md` 一致。
- `uv pip install -e ".[dev,analysis]"` 与 `pyproject.toml` 的 extras 分组匹配。
- pytest 测试标记、默认 fast 集合与 `tests/CLAUDE.md` 一致。
- 前端 `npm ci / tsc --noEmit / test:coverage / build / npm audit` 与 `frontend/package.json` 和 `vite.config.ts` 的 60% 覆盖率阈值匹配。
- `scripts/validate_k8s_manifests.py` 本地运行通过，K8s manifests 与 `k8s/CLAUDE.md` 的安全约定一致。

---

## 四、C. 可执行性与潜在失败点

### 4.1 会导致失败

| 编号 | 问题 | 说明 |
|------|------|------|
| C1 | **`nightly.yml` 引用不存在的 `scripts/locust_baseline.py`** | `performance` job 第 153 行执行 `locust -f scripts/locust_baseline.py`，仓库中只有 `tests/performance/*.py`，无 Locust 基线脚本。该 job 到达此步骤会失败 |
| C2 | **Staging/Production 部署实际不会更新镜像** | 同 B1。即使 CI 构建成功，K8s 仍使用旧 tag，部署等同于空跑 |

### 4.2 潜在风险 / 不可靠

| 编号 | 问题 | 说明 |
|------|------|------|
| C3 | **`cd-staging` 在 `KUBECONFIG_STAGING` 未配置时静默跳过** | `if: steps.check-kubeconfig.outputs.skip != 'true'` 导致缺少 secret 时整个部署成功但无实际部署，容易掩盖环境未就绪 |
| C4 | **`cd-azure-b2ats.yml` 与 `cd-staging.yml` 同时触发** | 两者都在 `master` push 后启动，互相独立，可能产生竞态或重复构建 |
| C5 | **`feature-switch.yml` / `data-pipeline.yml` 是 skeleton** | 只有日志记录 / 上传 artifact，不实际切换功能标志或导出数据，属于占位 workflow |
| C6 | **`security-scan.yml` 与 `ci.yml` 的 security job 大量重复** | pip-audit、Trivy、npm audit、TruffleHog、K8s 验证均同时存在于两个 workflow，维护成本高，容易产生规则不一致 |
| C7 | **cost fuse 未在 CI/CD 中验证或阻断部署** | `/cost-status` 在 data-pipeline 中仅做可达性检查，无成本熔断门禁 |
| C8 | **生产部署依赖手动输入 image_tag 或默认当前 sha** | 若输入错误 tag 或无对应镜像，`verify-image` job 会失败，但无更严格的 tag 来源校验（如必须来自已跑通 CI 的 commit） |

### 4.3 可执行性已确认

- `scripts/validate_k8s_manifests.py` 本地运行通过。
- `scripts/deploy-to-azure-b2ats.sh` 和 `docker-compose.azure-b2ats.yml` 存在且路径正确。
- `scripts/ci_check_bandit.py`、`scripts/ci_check_pip_audit.py` 存在，逻辑与 workflow 调用方式匹配。

---

## 五、A. 与 `docs/CI-CD流水线设计.md` 的一致性

### 5.1 专项一致性评估

按文档章节逐项比对：

| 章节 | 文档描述 | 实际状态 | 一致度 |
|------|---------|---------|--------|
| **2.1 分支策略** | 主分支为 `main`；分支类型 `feature/*`、`hotfix/*`、`release/*` | 实际主分支为 `master`；分支类型 workflow 已支持 | ⚠️ 主分支名不一致 |
| **2.2 分支保护** | 要求 2 人审批、`CODEOWNERS`、required status checks、线性历史 | 仓库无 `CODEOWNERS` 文件；GitHub 设置不可见 | ❌ 未验证/未配置 |
| **2.3 Pre-commit** | 详细的 `.pre-commit-config.yaml` | 文件不存在 | ❌ 未实现 |
| **2.4 Commit Message** | 9 种 type，regex 校验 | `ci.yml` 校验 10 种 type（多了 `ci`），基本匹配 | ✅ 基本一致 |
| **3.1 Dockerfile** | 示例使用 `requirements.txt`、`pip install --user`、`config/` 目录 | 实际使用 `pyproject.toml`、`uv`、`supervisord`、`configs/` 目录 | ⚠️ 示例过时 |
| **3.2 镜像策略** | 多阶段、非 root、层缓存、SBOM、镜像签名 | 多阶段/非 root/层缓存已落实；SBOM、签名未实现 | ⚠️ 部分实现 |
| **3.3 依赖扫描** | 示例用 `requirements.txt`、`Safety CLI` | 实际用 `pyproject.toml`、`pip-audit`、无 Safety | ⚠️ 示例过时 |
| **3.4 镜像签名** | cosign 签名 + syft SBOM | 未实现 | ❌ 未实现 |
| **3.5 构建门禁** | pip-audit/Safety、Trivy、Bandit、密钥检测、cosign、syft | 仅 pip-audit、Trivy、Bandit、TruffleHog；cosign/syft 缺失 | ⚠️ 部分实现 |
| **4.2 测试触发策略** | 单元/集成/E2E/偏见抽检/性能/安全分阶段触发 | 无独立集成/E2E stage；偏见抽检无 defense rate 校验；性能仅 nightly | ⚠️ 部分实现 |
| **4.3 单元测试配置** | 示例 `pytest.ini` 仅跑 `tests/unit/` | 实际用 `pyproject.toml`，fast-test 跑 unit+integration | ⚠️ 配置不一致 |
| **4.4 集成测试配置** | `docker-compose.test.yml` + 单独 test-runner | 文件不存在；集成测试合并到 fast-test | ❌ 未实现 |
| **4.5 测试报告归档** | 使用 `dorny/test-reporter`、Codecov、artifact | 实际用 `codecov-action`、`upload-artifact`，无 `dorny/test-reporter` | ⚠️ 部分实现 |
| **4.6 测试门禁** | 覆盖率≥60%、偏见防御率≥95%、P95 < 5s | 仅覆盖率门禁落实；偏见防御率无校验 | ⚠️ 部分实现 |
| **5.1 环境分级** | dev/staging/production 三级 | 仅有 staging/production K8s + Azure B2ats；无 dev CI/CD | ⚠️ 部分实现 |
| **5.2 蓝绿部署** | `scripts/blue-green-deploy.sh` + Docker Compose | 脚本不存在 | ❌ 未实现 |
| **5.3 金丝雀发布** | Flagger `Canary` 资源 | 不存在 | ❌ 未实现 |
| **5.4 回滚机制** | 自动/手动/紧急回滚，`scripts/rollback.sh` | 脚本不存在；CD workflow 仅打印 rollback 指令 | ❌ 未实现 |
| **6.1 部署后健康检查** | `/health`、`/ready`、业务接口、`/metrics` | 仅 `/health` | ⚠️ 部分实现 |
| **6.2 Smoke Test** | `tests/smoke/test_critical_paths.py` | 目录不存在 | ❌ 未实现 |
| **6.3 部署后告警** | `prometheus/alerting/deploy-alerts.yml` | `docker/prometheus.yml` 引用 `/etc/prometheus/rules/*.yml` 但无 rules 文件挂载 | ❌ 未实现 |
| **6.4 部署通知** | Slack 通知模板 | 未实现 | ❌ 未实现 |
| **7.1 环境变量** | 四级配置层级 | 基本通过 `.env`/ConfigMap/Secret 实现 | ✅ 基本一致 |
| **7.2 密钥注入** | Vault / Sealed Secrets / ESO 详细示例 | 仅有 `secret.yaml` 模板 + 外部创建说明；无 Vault/Sealed/ESO 实际配置 | ⚠️ 部分实现 |
| **7.3 配置变更流程** | GitOps/ArgoCD 六步流程 | 未实现 | ❌ 未实现 |
| **8.1~8.4 成本熔断** | 部署前成本检查、成本-部署闭环、部署后监控 | 仅 data-pipeline 对 `/cost-status` 做可达性检查 | ❌ 未实现 |
| **9.1 完整流水线** | 单文件 `ci-cd-pipeline.yml`，含 8 个 stage | 实际拆分为 8 个 workflow 文件；部署 stage 镜像更新失效 | ⚠️ 结构不同，功能部分缺失 |
| **10.1/10.2 运行视图** | 成功/失败处理流程 | 未配置 Slack/PagerDuty/邮件通知 | ❌ 未实现 |

### 5.2 关键结论

1. **文档是“目标态”而非“现状”**：大量章节（金丝雀、蓝绿、成本熔断、GitOps、Smoke Test、Slack 通知）描述的是规划能力，不是当前已落地方案。
2. **示例代码已过时**：Dockerfile 示例、pytest.ini 示例、security-scan.yml 示例仍使用 `requirements.txt`、`pip install`、`Safety CLI` 等，与项目实际使用的 `pyproject.toml` + `uv` 不一致。
3. **分支策略不一致**：文档以 `main` 为主分支，实际为 `master`。
4. **部署阶段文档与实现严重脱节**：文档描绘的 Flagger/蓝绿/Smoke Test/成本检查均未实现，且实际 K8s CD 因镜像名错误无法更新镜像。

---

## 六、D. 安全与合规差距

### 6.1 生产就绪评估相关

| 编号 | 要求 | 当前状态 |
|------|------|---------|
| D1 | 红队防御成功率 ≥95% | CI 不计算防御率；`tests/redteam/` 存在但 fast job 只跑 security 子集 |
| D2 | 6 条公平性硬规则嵌入 Prompt 并通过偏见审计 | CI 未验证 |
| D3 | 成本熔断机制经验证 | `/cost-status` 仅做可达性检查，无熔断门禁 |
| D4 | 审计日志完整 | 有中间件但 CI/CD 未将其作为门禁 |

### 6.2 安全扫描已配置但执行层面有风险

| 编号 | 问题 | 说明 |
|------|------|------|
| D5 | Trivy / npm audit / pip-audit 设为阻断 | 上游漏洞可能频繁导致 CI 失败，需配套白名单/例外流程 |
| D6 | Secret 管理依赖外部预先创建 | `secret.yaml` 被排除在 kustomization 外，文档已说明，但 CI/CD 未验证 secret 存在性 |

### 6.3 已落实

- TruffleHog 密钥扫描、Bandit 代码安全扫描、Trivy 镜像扫描、pip-audit/npm audit 依赖漏洞扫描均已配置。
- K8s manifests 安全上下文（runAsNonRoot、readOnlyRootFilesystem、seccomp、drop ALL 等）符合 `k8s/CLAUDE.md`。

---

## 七、综合结论与优先级修复建议

### 7.1 综合结论

| 维度 | 整体评价 | 最突出问题 |
|------|---------|-----------|
| **B. 与代码/项目结构匹配** | ⚠️ 中等 | K8s 镜像名不匹配导致部署无效；`.pre-commit-config.yaml` 缺失；Bandit 严重级别与 `pyproject.toml` 不一致 |
| **C. 可执行性** | 🔴 存在会失败的点 | `nightly.yml` 引用不存在的 `scripts/locust_baseline.py`；Staging/Production 部署实际不更新镜像 |
| **A. 与设计文档一致** | 🔴 差距较大 | 设计文档大量描述目标态未落地；部署/可观测性/成本熔断/配置管理章节实现度低 |
| **D. 安全与合规** | 🟡 扫描到位但门禁不足 | 红队防御率、偏见审计、成本熔断未在 CI/CD 中作为门禁验证 |

**当前状态判定**：CI/CD 流程**不满足生产就绪要求**。在修复关键 CD 缺陷前，不应承担生产发布职责。

### 7.2 必须优先修复的 5 个问题

1. **修复 K8s CD 镜像名称**（P0）：统一 `ghcr.io/fromwordimport/ai_cbc` 与 `ghcr.io/fromwordimport/aicbc`，并修正 `kustomize edit set image` 的目标名，使 Staging/Production 能真正部署新镜像。
2. **补齐 `scripts/locust_baseline.py` 或移除 nightly 对应步骤**（P0）：避免 nightly workflow 失败。
3. **同步 `docs/CI-CD流水线设计.md`**（P1）：将文档中未实现的章节标记为“目标态/待实现”，或更新为当前实际方案（`master` 分支、`uv`、拆分 workflow 等）。
4. **统一 Bandit 严重级别**（P1）：使 `pyproject.toml` 与 CI 的 `--severity-level` 配置一致。
5. **补全 `.pre-commit-config.yaml` 或从文档中移除相关描述**（P1）：消除文档与实现的差异。

### 7.3 中长期建议

- 将 `security-scan.yml` 与 `ci.yml` 的 security job 去重，或明确分工（如 security-scan 负责定时深度扫描，CI 负责 PR 快速扫描）。
- 补齐 `tests/smoke/` 与部署后 Smoke Test 步骤。
- 在 CI 或 CD 中增加偏见防御率、成本熔断状态的可阻断门禁。
- 若暂时不实现金丝雀/蓝绿部署，应在文档中明确当前采用“直接 apply + rollout status”策略。

---

## 八、附录：审查方法与验证记录

### 8.1 审查文件清单

- `.github/workflows/ci.yml`
- `.github/workflows/cd-staging.yml`
- `.github/workflows/cd-production.yml`
- `.github/workflows/cd-azure-b2ats.yml`
- `.github/workflows/security-scan.yml`
- `.github/workflows/nightly.yml`
- `.github/workflows/data-pipeline.yml`
- `.github/workflows/feature-switch.yml`
- `docker/Dockerfile`
- `docker-compose.yml`
- `docker-compose.azure-b2ats.yml`
- `k8s/base/kustomization.yaml`
- `k8s/base/deployment.yaml`
- `k8s/base/worker-deployment.yaml`
- `k8s/base/beat-deployment.yaml`
- `k8s/overlays/staging/kustomization.yaml`
- `k8s/overlays/prod/kustomization.yaml`
- `pyproject.toml`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `scripts/validate_k8s_manifests.py`
- `scripts/ci_check_bandit.py`
- `scripts/ci_check_pip_audit.py`
- `scripts/deploy-to-azure-b2ats.sh`
- `docs/CI-CD流水线设计.md`
- `docs/生产就绪评估/2026-06-14-生产就绪评估报告.md`
- `docs/生产就绪评估/2026-06-14-生产就绪整改计划.md`

### 8.2 本地验证命令

```bash
# K8s 静态验证（已通过）
uv run python scripts/validate_k8s_manifests.py
```

输出：

```
== AI_CBC K8s Manifest Static Validator ==

No issues found. Static validation passed.
```

### 8.3 未修改文件声明

本次审查**未修改任何 CI/CD 相关文件**，仅执行只读分析和一次本地验证脚本。
