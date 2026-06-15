# AI_CBC Performance Regression Test Specification
# Version: 1.0
# Maintainer: 小维 (DevOps/MLOps Engineer)
# Date: 2026-06-15

## 1. 目的

本文档定义 AI_CBC 性能回归测试基线的规范，包括：
- 压测场景（并发级别）
- KPI 阈值（P50/P95/P99 响应时间、错误率、吞吐量）
- 执行流程（Locust → CSV → pytest 断言）
- CI 集成方案
- 资源降级触发条件

## 2. 压测场景

| 场景 | 并发用户数 | 孵化率 | 持续时间 | 用途 |
|------|-----------|--------|----------|------|
| light | 10 | 2/s | 3min | 冒烟测试 / 快速回归 |
| medium | 100 | 10/s | 5min | 标准回归基线 |
| heavy | 500 | 50/s | 10min | 容量验证 |
| stress | 1000 | 100/s | 15min | 极限测试 / 发现瓶颈 |

## 3. KPI 阈值（medium 场景标准基线）

| Endpoint | P50 | P95 | P99 | 最小 RPS | 最大错误率 |
|----------|-----|-----|-----|----------|-----------|
| GET /health | 200ms | 500ms | 1000ms | 50 | 0.1% |
| GET /ready | 200ms | 500ms | 1000ms | 50 | 0.1% |
| GET /studies | 500ms | 2000ms | 5000ms | 20 | 0.1% |
| POST /studies | 500ms | 2000ms | 5000ms | 10 | 0.1% |
| POST /studies/{id}/generate | 1000ms | 5000ms | 10000ms | 5 | 0.1% |
| POST /personas/generate | 2000ms | 10000ms | 30000ms | 2 | 0.1% |
| POST /studies/{id}/simulate-responses | 1000ms | 5000ms | 10000ms | 5 | 0.1% |
| POST /studies/{id}/analyze | 2000ms | 30000ms | 60000ms | 1 | 0.1% |

**注**：阈值基于 Staging 环境目标设定，PERF-1 生产栈压测后需根据实际数据调整。

## 4. 执行流程

### 4.1 本地执行

```bash
# Step 1: 启动全栈（或仅 API）
docker compose up -d

# Step 2: 运行 Locust 压测
cd tests/performance
uv run locust -f test_load.py --host http://localhost:8000 --headless \
    -u 100 -r 10 --run-time 5m --csv aicbc_load

# Step 3: 运行回归断言
uv run pytest tests/performance/test_regression_baseline.py -v
```

### 4.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PERF_LOAD_TIER` | medium | 当前压测场景（light/medium/heavy/stress） |
| `AICBC_API_KEY` | dev-key-change-in-prod | API 认证密钥 |
| `AICBC_ROLE` | admin | 用户角色 |

## 5. CI 集成方案

### 5.1 触发条件

性能回归测试 **不** 在每次 PR 时运行（耗时过长），仅在以下场景触发：
- 每日定时（cron: `0 2 * * *`）
- Release 分支合并前（手动触发 `workflow_dispatch`）
- PERF-2 优化方案验证后

### 5.2 CI Stage 建议（新增 Stage 4b）

```yaml
  performance-regression:
    runs-on: ubuntu-latest
    needs: [deploy-staging]
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4

      - name: Install uv and locust
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          uv pip install locust pytest

      - name: Run load test against staging
        run: |
          cd tests/performance
          uv run locust -f test_load.py \
            --host https://staging.aicbc.example.com \
            --headless -u 100 -r 10 --run-time 5m --csv aicbc_load
        env:
          AICBC_API_KEY: ${{ secrets.STAGING_API_KEY }}

      - name: Run regression assertions
        run: |
          cd tests/performance
          uv run pytest test_regression_baseline.py -v
        env:
          PERF_LOAD_TIER: medium

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: performance-regression-results
          path: |
            tests/performance/aicbc_load_*.csv
          retention-days: 30
```

### 5.3 失败处理

- 性能回归失败 **不** 阻塞 main 分支合并（避免噪声）
- 失败时自动创建 Issue 并 @小速（性能工程师）和 @小维（DevOps）
- 连续 3 次失败触发告警（Slack/邮件）

## 6. 资源降级触发条件

当性能回归测试发现资源瓶颈时，按以下优先级自动降级：

| 条件 | 降级动作 | 影响 |
|------|----------|------|
| CPU > 80% 持续 2min | API HPA 扩容至 maxReplicas | 成本增加 |
| Memory > 85% 持续 2min | 限制 LLM 并发请求数 | 画像生成延迟增加 |
| P99 > 阈值 150% | 切换 LLM 模型至降级版本（claude-haiku） | 生成质量略降 |
| 错误率 > 1% | 关闭非核心功能（审计日志、详细指标） | 可观测性降低 |
| 队列积压 > 100 | 分析任务限流，拒绝新分析请求 | 用户体验下降 |

## 7. 历史基线管理

- 每次性能回归通过的 CSV 结果归档至 `s3://aicbc-performance-baselines/YYYY-MM-DD/`
- 基线对比：当前结果 vs 最近 7 天平均 vs 最近 30 天平均
- 趋势告警：P95 连续 7 天上升 > 10% 触发性能退化告警

## 8. 相关文件

- `tests/performance/test_load.py` — Locust 压测脚本
- `tests/performance/test_regression_baseline.py` — pytest 回归断言
- `k8s/deployment.yaml` — API HPA 配置
- `k8s/configmap.yaml` — 资源限制与降级参数

## 9. 修订记录

| 版本 | 日期 | 修改内容 | 作者 |
|------|------|----------|------|
| 1.0 | 2026-06-15 | 初始版本，基于 PERF-1/2/3 输出 | 小维 |
