# AI_CBC 性能压测准备报告

> **版本**：v0.3.0-pre  
> **维护人**：小速（性能工程师）  
> **日期**：2026-06-15  
> **状态**：准备阶段（前置依赖 BE-6 未完成，暂不启动正式压测）

---

## 1. 执行摘要

本报告汇总了 PERF-1（生产栈性能压测方案）、PERF-2（性能瓶颈定位与优化）、PERF-3（资源基线与降级预案）、QA-3（性能回归测试基线）四项任务的准备状态。

**核心结论**：
- 现有压测脚本 `tests/performance/test_load.py` 已验证可用，但覆盖场景有限
- 当前部署配置存在 3 项性能隐患，需在正式压测前修复
- 已知 4 大性能瓶颈，已有优化方案草案
- 资源基线基于 K8s 配置初步评估，待压测数据回填后校准

---

## 2. 前置依赖状态

| 任务 | 状态 | 阻塞影响 |
|------|------|----------|
| BE-6: Celery Worker + Redis 集成验证 | 未开始 | 阻塞正式压测执行（异步任务队列未就绪） |
| BE-3: docker-compose 全栈健康检查 | 未开始 | 阻塞本地全栈压测验证 |
| BE-1: MongoDB 可插拔存储端到端验证 | 进行中 | 阻塞持久化存储压测 |

**建议**：待 BE-6 完成后，优先在 staging 环境执行 100 并发压测，再逐步扩展至 500/1000。

---

## 3. 现有压测脚本审查（test_load.py）

### 3.1 脚本能力

| 用户类型 | 权重 | 场景覆盖 | 状态 |
|----------|------|----------|------|
| HealthCheckUser | 5 | /health, /ready, /metrics | 已验证 |
| StudyManagementUser | 3 | CRUD studies, 问卷生成 | 已验证 |
| FullPipelineUser | 1 | 端到端完整流程 | 部分验证（60s 内未完成） |

### 3.2 脚本缺陷与改进建议

1. **FullPipelineUser 超时问题**：单循环包含 6 个串行请求（创建研究 → 生成问卷 → 生成画像 → 模拟作答 → 运行分析 → 读取结果），在 60s 压测窗口内无法完成。建议：
   - 增加独立的 `AsyncPipelineUser` 仅测试异步提交（202 Accepted）+ 轮询状态
   - 将 `wait_time` 从 5-10s 缩短至 1-3s 以适配短周期压测

2. **缺少场景覆盖**：
   - 缺少只读热点接口压测（`/dashboard/summary`, `/studies/{id}`）
   - 缺少分析任务状态轮询压测
   - 缺少并发画像生成压测（`/personas/generate` 是敏感接口，限流 10/60s）

3. **缺少压力梯度**：脚本仅支持固定并发，建议增加渐进式加压场景（如 10→50→100→200 阶梯式）。

---

## 4. 已知性能瓶颈（来自 v0.2.0 报告）

### 4.1 瓶颈清单

| 优先级 | 瓶颈点 | 根因 | 影响 | 优化方案 |
|--------|--------|------|------|----------|
| P0 | `/studies/{id}/generate` 同步 D-optimal | CPU 密集型算法在 FastAPI 事件循环中同步执行 | 平均 2800ms，阻塞其他请求 | 改为 Celery 异步任务，API 返回 202 Accepted |
| P0 | 单 Uvicorn worker | Dockerfile 和 configmap 均配置 `API_WORKERS=1` | 无法利用多核，CPU 密集型任务串行 | 改为 `API_WORKERS=4`（或按 CPU 核心数动态） |
| P1 | `/metrics` 实时聚合 | Prometheus 指标在请求链中实时计算 | 平均 1516ms，高并发下放大 | 增加指标缓存或走独立 /metrics 进程 |
| P1 | 内存存储 threading.Lock | 写操作串行化 | 并发写请求排队 | 启用 MongoDB + 连接池 |
| P2 | LLM 调用延迟不可控 | 外部 API 延迟 1-10s | 画像生成和分析任务耗时 | 增加并发控制、降级模型、超时重试 |

### 4.2 关键配置问题

**问题 1：Dockerfile 单 worker**
```dockerfile
CMD ["python", "-m", "uvicorn", "src.aicbc.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
未指定 `--workers`，默认单进程。建议改为：
```dockerfile
CMD ["python", "-m", "uvicorn", "src.aicbc.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**问题 2：ConfigMap API_WORKERS=1**
```yaml
API_WORKERS: "1"
```
K8s deployment 已配置 3 replicas，但每个 pod 仍为单 worker，总并发处理能力 = 3 × 1 = 3 个请求并行。建议改为 `"4"` 使总并行能力 = 12。

**问题 3：Ingress 速率限制与 HPA 冲突**
```yaml
nginx.ingress.kubernetes.io/rate-limit: "100"
nginx.ingress.kubernetes.io/rate-limit-window: "1m"
```
Ingress 层限制 100 req/min，但 HPA 可扩容至 10 pods。若压测超过 100 req/min，请求会在 Ingress 层被拒绝，无法真实测试后端扩容能力。建议压测时临时调高或关闭 Ingress 限流。

---

## 5. Staging 压测方案

### 5.1 环境要求

| 组件 | 配置 | 备注 |
|------|------|------|
| API | 3 replicas, 4 workers/replica | 修复 API_WORKERS=1 后 |
| Worker | 2-4 replicas, 2 concurrency/replica | 根据队列深度动态扩容 |
| MongoDB | 1 replica + 连接池 50 | 启用持久化存储 |
| Redis | 1 replica | 限流 + Celery broker |
| Nginx | 1 replica | 反向代理，压测时关闭限流 |

### 5.2 压测阶段

| 阶段 | 并发数 | 持续时间 | 目标 | 通过标准 |
|------|--------|----------|------|----------|
| 冒烟 | 10 | 2min | 验证脚本 + 环境连通性 | 0 失败，P95 < 2s |
| 基线 | 100 | 5min | 建立性能基线 | 错误率 < 0.1%, P95 < 5s |
| 负载 | 500 | 5min | 测试扩容能力 | 错误率 < 1%, HPA 触发扩容 |
| 压力 | 1000 | 5min | 测试极限 + 降级 | 错误率 < 5%, 服务不崩溃 |
| 稳定性 | 200 | 30min | 长时间稳定性 | 内存无泄漏, CPU 平稳 |

### 5.3 监控指标

| 类别 | 指标 | 告警阈值 |
|------|------|----------|
| API | P50/P95/P99 延迟 | P95 > 5s 告警 |
| API | 错误率 | > 1% 告警 |
| API | 吞吐 (req/s) | 记录基线 |
| K8s | CPU 利用率 | > 80% 触发 HPA |
| K8s | 内存使用 | > 90% 告警 |
| MongoDB | 连接数 | > 40 告警 |
| Redis | 队列深度 | > 100 告警 |
| Celery | 任务积压 | > 50 告警 |
| LLM | Token 消耗速率 | 监控成本 |

---

## 6. 资源基线评估

### 6.1 当前 K8s 资源配置

| 组件 | Replicas | Request CPU | Limit CPU | Request Mem | Limit Mem | 总 Request CPU | 总 Limit CPU | 总 Request Mem | 总 Limit Mem |
|------|----------|-------------|-----------|-------------|-----------|----------------|--------------|----------------|--------------|
| API | 3 | 250m | 1000m | 512Mi | 2Gi | 750m | 3000m | 1536Mi | 6Gi |
| Worker | 2 | 500m | 2000m | 1Gi | 4Gi | 1000m | 4000m | 2Gi | 8Gi |
| Beat | 1 | 100m | 250m | 256Mi | 512Mi | 100m | 250m | 256Mi | 512Mi |
| MongoDB | 1 | 250m | 1000m | 512Mi | 2Gi | 250m | 1000m | 512Mi | 2Gi |
| Redis | 1 | 100m | 250m | 256Mi | 512Mi | 100m | 250m | 256Mi | 512Mi |
| **合计** | - | - | - | - | - | **2200m** | **8500m** | **4.5Gi** | **17Gi** |

### 6.2 资源需求预测（100/500/1000 并发）

| 并发 | API Replicas | Worker Replicas | 预估 CPU | 预估内存 | 备注 |
|------|--------------|-----------------|----------|----------|------|
| 100 | 3 | 2 | 2000m | 6Gi | 当前配置可满足 |
| 500 | 6 | 4 | 5000m | 14Gi | HPA 扩容至 6 API pods |
| 1000 | 10 | 8 | 10000m | 28Gi | HPA 扩容至 max 10 API pods，Worker 需手动扩容 |

**风险点**：
- Worker 未配置 HPA，1000 并发下分析任务队列可能积压
- MongoDB 单 replica，存在单点故障风险，高并发下连接数可能成为瓶颈
- Redis 单 replica，Celery broker 和缓存共用，建议分离或启用 Sentinel

---

## 7. 降级预案

### 7.1 触发条件

| 条件 | 动作 | 影响 |
|------|------|------|
| P95 > 10s | 启用 LLM 降级模型（haiku） | 画像质量可能下降 |
| 队列深度 > 100 | 限制画像生成批量大小（max 10） | 单次研究耗时增加 |
| CPU > 90% | 关闭非核心功能（审计日志、详细指标） | 安全审计数据减少 |
| 内存 > 90% | 限制并发分析任务数 | 分析排队时间增加 |
| 错误率 > 5% | 启用熔断，拒绝新研究创建 | 服务只读 |

### 7.2 自动扩容策略

```yaml
# HPA 调整建议（deployment.yaml）
behavior:
  scaleUp:
    stabilizationWindowSeconds: 0
    policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 4
        periodSeconds: 15
    selectPolicy: Max
  scaleDown:
    stabilizationWindowSeconds: 300  # 保持 5min 稳定窗口
    policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

建议增加 Worker HPA：
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: aicbc-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: aicbc-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: External
      external:
        metric:
          name: celery_queue_length
        target:
          type: Value
          value: "50"
```

---

## 8. 性能回归测试基线（QA-3）

### 8.1 KPI 定义

| 接口 | P50 | P95 | P99 | 错误率 | 备注 |
|------|-----|-----|-----|--------|------|
| GET /health | < 100ms | < 500ms | < 1000ms | < 0.1% | 探针接口 |
| GET /ready | < 200ms | < 1000ms | < 2000ms | < 0.1% | 依赖检查 |
| GET /studies | < 200ms | < 1000ms | < 2000ms | < 0.1% | 列表查询 |
| POST /studies | < 500ms | < 2000ms | < 5000ms | < 0.1% | 创建研究 |
| POST /studies/{id}/generate | < 1000ms | < 5000ms | < 10000ms | < 1% | 异步后仅提交 |
| POST /personas/generate | < 2000ms | < 10000ms | < 30000ms | < 1% | LLM 调用 |
| POST /studies/{id}/analyze | < 500ms | < 2000ms | < 5000ms | < 0.1% | 异步提交 |
| GET /dashboard/summary | < 500ms | < 2000ms | < 5000ms | < 0.1% | 聚合查询 |

### 8.2 CI 集成方案

在 `.github/workflows/ci-cd.yml` 中增加性能测试阶段：

```yaml
performance-test:
  needs: [deploy-staging]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install Locust
      run: pip install locust
    - name: Run smoke test
      run: |
        cd tests/performance
        locust -f test_load.py --host https://staging.aicbc.example.com \
          --headless -u 10 -r 2 --run-time 2m --only-summary
    - name: Run baseline test
      run: |
        cd tests/performance
        locust -f test_load.py --host https://staging.aicbc.example.com \
          --headless -u 100 -r 20 --run-time 5m --csv aicbc_baseline
    - name: Upload results
      uses: actions/upload-artifact@v4
      with:
        name: performance-results
        path: tests/performance/*.csv
```

---

## 9. 下一步行动

| 序号 | 行动 | 负责人 | 依赖 | 优先级 |
|------|------|--------|------|--------|
| 1 | 修复 Dockerfile API_WORKERS=1 | 小维 | 无 | P0 |
| 2 | 修复 ConfigMap API_WORKERS=1 | 小维 | 无 | P0 |
| 3 | 扩展压测脚本（增加场景覆盖） | 小速 | 无 | P1 |
| 4 | 等待 BE-6 完成（Celery + Redis 集成） | 小端 | BE-6 | P0 |
| 5 | 在 staging 执行 100 并发基线压测 | 小速 | BE-6, 配置修复 | P0 |
| 6 | 执行 500/1000 并发压力测试 | 小速 | 100 并发通过 | P1 |
| 7 | 回填数据到本报告，更新 v1.0 | 小速 | 压测完成 | P1 |
| 8 | 配置 Worker HPA | 小维 | 压测数据 | P2 |

---

## 10. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| BE-6 延迟导致压测窗口压缩 | 中 | 高 | 提前准备脚本，BE-6 完成后 24h 内启动 |
| MongoDB 单点成为瓶颈 | 高 | 中 | 压测中监控连接数，必要时提前评估 Atlas |
| LLM API 限流导致压测失败 | 中 | 中 | 压测中使用 mock LLM 或限制并发 |
| 配置修复未同步到 staging | 低 | 高 | 压测前执行配置审查清单 |

---

**报告日期**：2026-06-15  
**下次更新**：BE-6 完成后，执行首轮压测后回填数据
