# GitHub Actions CI/CD 编写指南

> **核心定位**：本指南不仅是一份自动化配置手册，更是帮助团队构建 **快速、安全、可预期的软件交付能力** 的战略实践框架。它让技术实现直接对齐业务增长与产品进化。

## 0. 为什么需要这份指南——业务与产品的原始驱动力

在动手写第一行 YAML 之前，团队必须理解 CI/CD 究竟在解决什么业务和产品问题：

| 视角   | 核心诉求                                                                 | 期望的 CI/CD 能力                                                      |
|--------|--------------------------------------------------------------------------|------------------------------------------------------------------------|
| **业务** | 缩短价值交付周期，抢占市场；降低线上事故与品牌风险；释放团队创造力；满足合规审计 | 快速构建-测试-发布闭环；标准化的质量门禁；自动化安全与合规检查；交付指标可视化 |
| **产品** | 极速验证产品假设；保障用户体验无缝、一致；让数据反馈驱动决策；打破协作壁垒     | 小时级迭代；零停机部署与自动回滚；特性开关与灰度发布；埋点与功能同步上线 |

下面所有设计原则和技术实践，都是为了满足这张表里的诉求。

---

## 1. 设计原则（技术 + 业务/产品解释）

### 原则 1：快且准的反馈
- **技术实现**：CI 力争 5 分钟内完成，使用缓存、矩阵并行、失败快速中止。
- **业务价值**：需求从提出到上线的平均时间（Lead Time）大幅缩短，业务部门能更快响应市场变化。
- **产品价值**：产品经理上午提出的优化想法，下午就能通过 A/B 测试看到数据，验证成本几乎为零。

### 原则 2：稳定可靠，结果可重复
- **技术实现**：每次运行在全新、干净的环境中，依赖版本锁定，避免“环境漂移”。
- **业务价值**：发布不再是一场惊心动魄的赌博。一致的构建和部署流程将变更失败率降到最低，保护品牌声誉。
- **产品价值**：用户不会遭遇“本地没问题，一上线就崩”的体验断崖，核心流程（支付、登录）稳定性得到持续保障。

### 原则 3：安全内建，合规左移
- **技术实现**：密钥全用 Secrets，依赖扫描、代码安全分析自动化，制品可溯源。
- **业务价值**：满足金融、医疗等行业的审计要求，所有发布记录完整可查，避免监管罚款。
- **产品价值**：安全漏洞在开发阶段就被拦截，产品无需在“带病上线”和“延期损失”之间做痛苦选择。

### 原则 4：流水线即代码，可维护可复用
- **技术实现**：一切配置在 `.github/workflows/` 下版本化，模块化封装为可复用工作流或 Action。
- **业务价值**：新成员第一天就能通过标准流水线安全提交代码，团队整体吞吐量随规模线性增长，而非陷入维护泥潭。
- **产品价值**：产品、测试、运营可以在同一个流水线界面上看到功能从“开发中”到“可体验”的实时状态，沟通成本断崖式下降。

### 原则 5：部署平滑，用户无感
- **技术实现**：滚动更新、蓝绿部署、金丝雀发布，配合健康检查和自动回滚。
- **业务价值**：即使在流量高峰期也可以安全发布，避免停机造成的直接收入损失。
- **产品价值**：用户在使用过程中后台即完成升级，新功能灰度放量，一旦指标异常秒级回滚，体验丝滑无中断。

---

## 2. 工作流拆分：让交付节奏匹配业务与产品节奏

不要把 CI 和 CD 写在一个 YAML 文件里。拆分工作流是为了让不同的业务关注点独立运作、互不阻塞。

| 工作流文件          | 触发条件                   | 技术职责                           | 服务的业务/产品目标                                      |
| ------------------- | -------------------------- | ---------------------------------- | -------------------------------------------------------- |
| `ci.yml`            | `push`、`pull_request`     | lint、test、安全扫描               | **质量内建**：让 Bug 根本不流向用户；加速 PR 评审        |
| `cd-staging.yml`    | 推送到 `develop` 分支      | 构建制品，部署到测试环境           | **快速预览**：产品/QA 能立刻体验最新功能，提供反馈       |
| `cd-azure-b2ats.yml`| push 到 `master` / 手动触发 | 构建镜像，SSH 部署到 Azure VM 生产环境 | **生产交付**：将验证后的版本发布到生产环境               |
| `feature-switch.yml`| 手动触发，或特定标签      | 管理特性开关（Feature Flag）配置   | **产品实验**：按需开启/关闭功能，灰度发布，A/B 测试      |
| `data-pipeline.yml` | 跟随功能分支或定时        | 验证埋点数据管道，同步数据产品定义 | **数据闭环**：保证功能上线时埋点就绪，支持产品决策       |
| `security-scan.yml` | 定时 (`cron`) 或 PR 上     | 依赖漏洞、容器安全深度扫描         | **合规与风险控制**：持续监控第三方风险                   |
| `nightly.yml`       | 定时 (`cron`)              | 全量集成测试，性能基准测试         | **长期质量守护**：避免性能劣化导致用户流失               |

**关键点**：特性开关（Feature Flag）的管理应作为一等公民纳入 CI/CD。产品希望灰度放量，那流水线就必须支持仅配置变更而不重新构建部署的能力。可通过专门的 workflow 调用 Flag 管理 API 实现。

---

## 3. CI 工作流编写模板（核心：为“质量内建”服务）

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
      - run: npm ci
      - name: Lint (代码规范)
        run: npm run lint
      - name: Dependency vulnerability scan (依赖漏洞扫描)
        run: npm audit --audit-level=high
      - name: Static code analysis (静态代码安全)
        uses: github/codeql-action/analyze@v2

  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: true
      matrix:
        node-version: [18, 20]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'
      - run: npm ci
      - name: Run unit & integration tests
        run: npm test -- --coverage
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-${{ matrix.node-version }}
          path: coverage/
```

**业务/产品对应点**：
- `fail-fast` + 精确的测试分类，确保**核心业务逻辑回归**第一时间被发现，保护支付、下单等关键路径。
- 漏洞扫描阻止带有已知漏洞的包进入生产，**降低产品安全风险**。
- 测试报告存档为**未来审计和质量度量**提供数据支撑。

---

## 4. CD 工作流编写模板（核心：为“安全、无感发布”服务）

### 4.1 部署到测试环境（产品/业务快速预览）

```yaml
name: CD Staging

on:
  push:
    branches: [develop]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Build and push Docker image
        run: |
          docker build -t app:${{ github.sha }} .
          docker push app:${{ github.sha }}
      - name: Deploy to staging
        run: kubectl set image deployment/app-staging app=app:${{ github.sha }}
      - name: Notify product channel
        run: |
          curl -X POST ${{ secrets.SLACK_PRODUCT_WEBHOOK }} \
            -d '{"text":"新版本已部署到测试环境，产品同学可体验验证"}'
```

**价值**：产品团队可立即体验新功能，缩短“开发-反馈”循环，避免到预发布才第一次看到效果。

### 4.2 部署到生产（Azure VM + Docker Compose）

> **当前项目实际使用**：`.github/workflows/cd-azure-b2ats.yml` 负责构建镜像并通过 SSH 部署到 Azure VM。原基于 `kubectl` 的 `cd-production.yml` 已删除，因为生产环境未使用 Kubernetes。

**前提**：在 GitHub 仓库 Settings → Environments → `azure-b2ats` 配置好 `AZURE_VM_IP`、`AZURE_VM_USER`、`AZURE_VM_SSH_KEY` 等 Secrets。

```yaml
name: CD Azure B2ats v2

on:
  push:
    branches: [master]
  workflow_dispatch:

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Build and push image
        run: |
          docker build -t ghcr.io/${{ github.repository }}:${{ github.sha }} .
          docker push ghcr.io/${{ github.repository }}:${{ github.sha }}

  deploy:
    runs-on: ubuntu-latest
    needs: build-push
    environment: azure-b2ats
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        env:
          IMAGE_TAG: ${{ github.sha }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          host: ${{ secrets.AZURE_VM_IP }}
          username: ${{ secrets.AZURE_VM_USER }}
          key: ${{ secrets.AZURE_VM_SSH_KEY }}
          envs: IMAGE_TAG,GITHUB_TOKEN
          script_stop: true
          script: |
            cd /opt/aicbc
            git remote set-url origin https://x-access-token:${GITHUB_TOKEN}@github.com/${{ github.repository }}.git
            git fetch origin master
            git reset --hard origin/master
            export IMAGE_TAG=${IMAGE_TAG}
            bash scripts/deploy-to-azure-b2ats.sh

      - name: Verify deployment health
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.AZURE_VM_IP }}
          username: ${{ secrets.AZURE_VM_USER }}
          key: ${{ secrets.AZURE_VM_SSH_KEY }}
          script_stop: true
          script: |
            cd /opt/aicbc
            for i in {1..30}; do
              if docker compose -f docker-compose.azure-b2ats.yml exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" > /dev/null 2>&1; then
                echo "Health check passed"
                exit 0
              fi
              echo "Waiting for API health... ($i/30)"
              sleep 2
            done
            echo "ERROR: Health check failed" >&2
            exit 1
```

以下为历史 Kubernetes 生产部署示例，保留作为参考：

<details>
<summary>Kubernetes 生产部署示例（参考）</summary>

```yaml
name: CD Production

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Build and push image
        run: |
          docker build -t app:${{ github.ref_name }} .
          docker push app:${{ github.ref_name }}
      - name: Canary deployment (10% traffic)
        run: |
          kubectl set image deployment/app-canary app=app:${{ github.ref_name }}
          # 等待 5 分钟观测指标
          sleep 300
      - name: Health check on canary
        run: |
          curl --fail https://canary.example.com/health || ./rollback.sh canary
      - name: Promote to full production
        run: |
          kubectl set image deployment/app app=app:${{ github.ref_name }}
      - name: Final health check
        run: |
          curl --fail https://api.example.com/health || ./rollback.sh full
      - name: Send deployment summary to business dashboard
        run: |
          curl -X POST ${{ secrets.BI_WEBHOOK }} \
            -d '{"version":"${{ github.ref_name }}","status":"success"}'
```

**业务/产品价值**：
- **审批门禁**确保业务负责人知情并同意发布。
- **金丝雀发布**先让 10% 真实用户验证，一旦健康检查失败自动回滚，对绝大多数用户毫无影响，完全满足“无感发布”的产品要求。
- 部署结果实时回传至业务仪表盘，支持**交付指标（Deployment Frequency, Change Failure Rate）** 的自动化统计。

</details>

### 4.3 特性开关管理（单独工作流，支撑产品实验）

产品常需要在不下发新版本的情况下打开/关闭功能或修改放量比例。可以将开关配置存于仓库或配置中心，由特定工作流操作。

```yaml
name: Feature Flag Management

on:
  workflow_dispatch:
    inputs:
      flag_name:
        description: 'Feature flag key'
        required: true
      state:
        type: choice
        options: [on, off, 50%]
        description: 'Flag state'

jobs:
  update-flag:
    runs-on: ubuntu-latest
    steps:
      - name: Update flag via Feature Service API
        run: |
          curl -X PUT https://flags.example.com/api/flag \
            -H "Authorization: Bearer ${{ secrets.FLAG_SERVICE_TOKEN }}" \
            -d '{"flag":"${{ github.event.inputs.flag_name }}","state":"${{ github.event.inputs.state }}"}'
```

这样，运营/产品人员可申请手动触发此工作流，实现**功能灰度和快速关闭**，而完全不需要研发介入。

---

## 5. 数据闭环：让产品决策有据可依

好的 CI/CD 必须保证业务埋点与功能同时上线，避免出现“功能上线了，数据还看不到”的断层。

- **在 CI 的测试阶段，增加埋点校验**：检查声明的埋点事件是否都有采集代码对应。
- **在 CD 部署步骤后，加入数据管道验证**：
  ```yaml
  - name: Verify analytics pipeline
    run: |
      # 发送测试事件到数据接收端点
      curl -X POST https://analytics.example.com/test-event -d '{"event":"deployment","version":"${{ github.ref_name }}"}'
      # 等待数秒后查询数据仓库确认事件已落地（可集成数据平台 API）
  ```
- **将数据产品规范纳入流水线**：定义 `analytics-schema.json`，当 PR 修改它时自动触发校验工作流，确保埋点文档与实现一致。

---

## 6. 安全与合规：从“拦路虎”到“加速器”

业务方（尤其是金融、医疗）最关注审计与合规，CI/CD 可以内置这些能力：

- **完整审计链**：每个部署 job 自动生成包含 git commit、构建人、审批人、部署目标的日志，上传为不可变 artifact 或写入审计系统。
- **密钥与权限最小化**：使用 GitHub Environment 的保护规则，不同环境使用不同的服务账号，且密钥定期轮换。
- **安全扫描门禁**：高危漏洞自动阻塞部署，并通知安全负责人。

将合规检查自动化的最大业务价值是：**发布审批不必再是漫长的邮件往来，而是流水线中一个可见、快速的人工确认点**。

---

## 7. 通知与可观测性：让交付变成透明的数字

除了技术通知，还必须为业务和产品提供可观测窗口：

- **产品/业务通知**：在 Slack/钉钉等专属频道广播部署事件、特性开关变更、回滚通知。
- **交付仪表板**：利用 GitHub Actions 的指标或第三方工具，展示四个关键业务指标（DORA metrics）：
  - **发布频率**（Deployment Frequency）
  - **变更前置时间**（Lead Time for Changes）
  - **变更失败率**（Change Failure Rate）
  - **平均恢复时间**（Mean Time to Recovery）

这些指标直接反映 CI/CD 对业务的实际影响，也是持续改进的依据。

```yaml
- name: Send DORA metrics
  run: |
    curl -X POST ${{ secrets.METRICS_API }} \
      -d '{"team":"product","deploy_time":"${{ github.event.release.published_at }}","lead_time":"1200","status":"success"}'
```

---

## 8. 性能优化清单（兼顾技术效率与业务成本）

| 优化点               | 技术做法                                                      | 业务/产品收益                                        |
| -------------------- | ------------------------------------------------------------- | ---------------------------------------------------- |
| 依赖缓存             | `cache` 指令缓存 npm/docker 层                                | 节省 CI 分钟数，降低研发成本；更快的反馈支撑更快迭代 |
| 路径过滤触发         | `paths-ignore: ['docs/**']`                                   | 避免文档修改触发完整流程，节约资源                   |
| 矩阵并行             | `matrix` 并行测试不同环境                                     | 不影响交付速度的情况下扩大兼容性覆盖                 |
| 锁死关键版本         | `ubuntu-22.04` 代替 `ubuntu-latest`                          | 消除环境突变导致的产品体验不一致风险                 |
| 制品仓库与部署解耦   | 构建一次镜像，多处部署（测试→预发→生产）                      | 确保上线版本就是测试过的版本，避免“幻影”Bug         |

---

## 9. 常见反模式（业务与产品最怕的坑）

| 反模式                                         | 对业务/产品的伤害                                       | 正确做法                                                    |
| ---------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------- |
| 一个几千行的 YAML，CI/CD 不分                   | 发布灵活度极差，无法快速支持产品的小需求或紧急修复      | 拆分成独立工作流，CI、CD、特性开关管理各司其职              |
| 生产部署无审批，或无自动回滚                     | 误发高风险代码导致线上事故，恢复耗时长，用户流失        | 启用 Environment Protection，强制审批 + 健康检查自动回滚    |
| 环境配置不一致（开发/生产数据库连接串不同）      | 测试环境正常，生产崩溃，产品体验瞬间变差                | 所有环境差异以 Secrets 和 ConfigMap 统一管理，流水线校验一致性 |
| 忽略埋点与功能的同步                             | 新功能上线无数据，产品完全瞎眼，决策全靠猜              | 将埋点验证纳入 CI，数据管道检查纳入 CD                      |
| 没有交付度量                                     | 无法知道团队到底是变快了还是变慢了，改进无方向          | 跟踪 DORA 指标，定期回顾并优化流水线                        |

---

## 10. 团队落地与持续进化

1. **从业务痛点出发，小步启动**：选择当前最痛的场景（如“上线总出问题”或“测试环境总没法及时体验”），优先落地对应的工作流。不要一开始追求完美。
2. **让产品、业务人员看得见**：把流水线状态嵌入内部 Wiki 或大屏，让非技术角色也能实时了解“功能走到哪了”。
3. **将交付指标纳入团队复盘**：每月看一次发布频率、前置时间、失败率，识别瓶颈（如审批等待过久、测试不稳定），用数据推动流程改进。
4. **保障特性开关的治理**：开关是产品加速器，也是技术债务。必须制定开关清理策略，在功能稳定后从代码中移除，避免线上配置爆炸。
5. **培养“全栈交付”思维**：鼓励开发人员不仅为功能写代码，也为该功能的可测试性、可观测性、可部署性负责，最终使整个 CI/CD 成为团队共同的肌肉记忆。