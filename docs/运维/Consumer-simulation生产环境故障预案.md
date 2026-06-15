# Consumer-simulation 生产环境故障预案

> **版本**：v1.0  
> **编制**：小应 (LLM Application Engineer)  
> **日期**：2026-06-16  
> **适用范围**：AI_CBC 消费者模拟子系统 (ConsumerGeneratorAgent + ProfileGenerator + LLMClient)

---

## 一、预案概述

本预案针对 Consumer-simulation 子系统在生产环境中可能遇到的故障场景，提供分级响应策略和自动化降级方案。核心目标是：在 LLM API 不稳定、成本超支、或生成质量下降时，确保系统能够优雅降级并维持最低可用性。

---

## 二、故障场景与响应矩阵

### 2.1 故障场景分级

| 级别 | 场景 | 触发条件 | 影响范围 | 响应时间 |
|------|------|---------|---------|---------|
| **P0** | LLM API 完全不可用 | 连续 3 次重试失败，所有 provider 不可用 | 画像生成完全中断 | 立即 |
| **P1** | LLM API 响应超时/降级 | 单次请求 > 30s 或成本熔断触发 DEGRADE | 生成质量下降，延迟增加 | 5 分钟内 |
| **P2** | 批量生成任务失败率升高 | 单批次失败率 > 20% | 部分画像缺失，数据不完整 | 15 分钟内 |
| **P3** | 偏见审计通过率下降 | 单批次偏见检测失败率 > 10% | 生成质量风险，伦理合规风险 | 30 分钟内 |
| **P4** | 成本熔断触发 | 达到 FUSE 或 EMERGENCY 阈值 | 新请求被阻断 | 立即通知 |

---

## 三、LLM API 超时与降级方案 (P0/P1)

### 3.1 现有机制

当前 `LLMClient` 已实现以下机制：

- **指数退避重试**：`max_retries=3`，退避间隔 `2^(attempt-1)` 秒
- **双 Provider 支持**：Anthropic (Claude) + OpenAI (GPT)，自动切换
- **LRU 缓存**：128 条缓存，命中时零成本零延迟
- **成本熔断**：`CostFuse` 在 DEGRADE 状态自动降级到轻量模型
- **Prompt 泄露检测**：自动拦截包含系统指令的响应

### 3.2 生产环境增强建议

#### 3.2.1 缓存预热策略

```python
# 在系统启动时预热常见 seed 组合的缓存
CACHE_WARMUP_SEEDS = [
    {"life_stage": "精致白领", "city_tier": "一线", "income_bracket": "25-40万"},
    {"life_stage": "新手父母", "city_tier": "二线", "income_bracket": "15-25万"},
    # ... 高频组合
]
```

**实施建议**：
- 部署后自动执行缓存预热脚本
- 监控缓存命中率，低于 60% 时触发告警
- 缓存持久化到 Redis，跨 Pod 共享

#### 3.2.2 Provider 优先级与故障转移

```python
# 建议的 Provider 优先级配置
PROVIDER_PRIORITY = {
    "standard": ["anthropic", "openai"],  # 正常状态
    "degraded": ["openai", "anthropic"],  # 降级状态（OpenAI 通常更便宜）
    "emergency": ["openai"],              # 紧急状态（仅保留最便宜的）
}
```

**实施建议**：
- 在 `LLMClient` 中增加 Provider 健康检查端点
- 连续 2 次失败自动切换 Provider
- 记录 Provider 成功率到 Prometheus 指标

#### 3.2.3 超时动态调整

```python
# 根据历史延迟数据动态调整超时
DYNAMIC_TIMEOUT = {
    "base_timeout": 30,        # 基础超时 30s
    "p95_multiplier": 1.5,     # P95 延迟 × 1.5
    "max_timeout": 120,        # 最大 120s
    "min_timeout": 10,         # 最小 10s
}
```

---

## 四、画像生成失败重试机制 (P2)

### 4.1 现有机制

当前 `ProfileGenerator` 已实现：

- **逐层 fallback**：每层生成失败时使用 `_LAYER_FALLBACKS` 默认值
- **JSON 解析容错**：解析失败时返回 fallback，不中断整体流程
- **字段缺失填充**：LLM 返回缺少字段时，从 fallback 补全

### 4.2 生产环境增强建议

#### 4.2.1 批次失败隔离

```python
# 当前已实现：generate_batch 中单个失败不影响整体
# 增强建议：失败项自动重试（最多 2 次）
MAX_BATCH_RETRY = 2
BATCH_RETRY_DELAY = 5  # 秒
```

#### 4.2.2 失败告警与人工介入

| 失败率 | 自动动作 | 告警级别 |
|--------|---------|---------|
| > 10% | 记录详细日志 | WARNING |
| > 20% | 触发自动重试 | ERROR |
| > 50% | 暂停新批次，通知 oncall | CRITICAL |

#### 4.2.3 简化模板降级

当完整四层生成持续失败时，启用简化模板：

```python
SIMPLIFIED_TEMPLATE = {
    "layer1": "直接填充 demographics 模板",
    "layer2": "基于 demographics 的规则匹配",
    "layer3": "预定义张力组合库",
    "layer4": "基于 demographics 的场景模板",
}
```

**适用条件**：
- 连续 3 个批次失败率 > 30%
- LLM API 完全不可用超过 10 分钟
- 成本熔断达到 EMERGENCY 级别

---

## 五、批量任务队列监控 (Celery)

### 5.1 关键监控指标

| 指标 | 告警阈值 | 说明 |
|------|---------|------|
| `celery_queue_length` | > 100 | 队列堆积 |
| `celery_task_latency` | > 60s | 任务延迟 |
| `celery_task_failure_rate` | > 5% | 任务失败率 |
| `celery_worker_heartbeat` | 缺失 > 30s | Worker 失联 |
| `persona_generation_rate` | < 1/min | 生成速率过低 |

### 5.2 队列堆积处理

```python
# 队列堆积时的自动扩容策略
QUEUE_SCALING = {
    "threshold_1": {"queue_length": 50, "action": "增加 1 个 Worker"},
    "threshold_2": {"queue_length": 100, "action": "增加 2 个 Worker"},
    "threshold_3": {"queue_length": 200, "action": "增加 4 个 Worker + 告警"},
    "max_workers": 10,  # 防止无限扩容
}
```

### 5.3 死信队列处理

```python
# 失败任务进入死信队列后的处理
DEAD_LETTER_HANDLING = {
    "retry_after": "1小时",      # 1小时后自动重试
    "max_retries": 3,            # 最多重试 3 次
    "manual_review": "3次后进入人工审核队列",
    "alert": "每次进入死信队列都触发告警",
}
```

---

## 六、成本熔断与 LLM 调用降级联动

### 6.1 现有熔断机制

`CostFuse` 已实现四级熔断：

| 状态 | 阈值 | 行为 |
|------|------|------|
| NORMAL | < 80% | 正常调用 |
| WARNING | >= 80% | 告警，继续正常调用 |
| DEGRADE | >= 95% | 自动降级到轻量模型 (`claude-haiku-4-5`) |
| FUSE | >= 100% | 阻断新调用 |
| EMERGENCY | >= 120% | 完全阻断，通知小P |

### 6.2 生产环境增强建议

#### 6.2.1 模型降级策略细化

```python
# 根据任务类型选择降级模型
DEGRADE_STRATEGY = {
    "persona_generation": {      # 画像生成
        "standard": "claude-sonnet-4-6",
        "degraded": "claude-haiku-4-5",
        "emergency": "gpt-4o-mini",  # 更便宜的备选
    },
    "bias_audit": {             # 偏见审计
        "standard": "claude-haiku-4-5",  # 本来就用轻量模型
        "degraded": "gpt-4o-mini",
        "emergency": "本地规则匹配",       # 完全不用 LLM
    },
    "authenticity_score": {     # 真实性评分
        "standard": "claude-sonnet-4-6",
        "degraded": "claude-haiku-4-5",
        "emergency": "启发式评分",         # 简化规则评分
    },
}
```

#### 6.2.2 成本熔断与业务联动

```python
# 当成本达到 WARNING 时，主动降低非核心任务频率
COST_ADAPTIVE_THROTTLING = {
    "warning": {
        "batch_size": "从 50 降到 30",
        "concurrency": "从 3 降到 2",
        "cache_ttl": "从 1h 延长到 4h",
    },
    "degrade": {
        "batch_size": "从 30 降到 10",
        "concurrency": "从 2 降到 1",
        "disable_auxiliary": True,  # 禁用 language_samples 和 dishwasher_context
    },
}
```

---

## 七、Prompt 生产化管理

### 7.1 版本管理

```yaml
# 建议的 Prompt 版本管理规范
prompt_versioning:
  format: "{major}.{minor}.{patch}"
  examples:
    - "1.0.0": 初始版本
    - "1.1.0": 增加公平性规则
    - "1.1.1": 修复 SP-004 关键词误报
  rollback: "支持回滚到任意历史版本"
  a_b_test: "支持同时运行两个版本，对比生成质量"
```

### 7.2 A/B 测试框架

```python
# Prompt A/B 测试配置
AB_TEST_CONFIG = {
    "experiment_id": "prompt_v1_2_vs_v1_3",
    "split_ratio": 0.5,          # 50% 流量到新版本
    "metrics": [
        "authenticity_score_avg",
        "bias_detection_rate",
        "generation_latency_p95",
        "cost_per_persona",
    ],
    "duration": "7天",
    "winner_criteria": "authenticity_score 提升 > 5% 且 bias_detection_rate 不下降",
}
```

### 7.3 回滚策略

| 触发条件 | 回滚动作 | 回滚时间 |
|---------|---------|---------|
| 新版本偏见检测失败率 > 15% | 自动回滚到上一版本 | < 1 分钟 |
| 新版本真实性评分下降 > 10% | 自动回滚到上一版本 | < 1 分钟 |
| 新版本生成成本上升 > 50% | 告警，人工确认后回滚 | < 5 分钟 |
| 新版本导致 API 错误率上升 | 自动回滚到上一版本 | < 1 分钟 |

---

## 八、监控与告警

### 8.1 关键 Dashboard

| Dashboard | 指标 | 刷新频率 |
|-----------|------|---------|
| LLM 调用健康 | 延迟、成功率、缓存命中率 | 10s |
| 成本监控 | 实时成本、熔断状态、预算使用率 | 1min |
| 生成质量 | 真实性评分、偏见通过率、张力覆盖率 | 5min |
| 队列状态 | Celery 队列长度、Worker 数量、任务延迟 | 10s |
| 批次统计 | 成功率、失败原因分布、重试次数 | 1min |

### 8.2 告警规则

```yaml
alerts:
  - name: "LLM API 高延迟"
    condition: "p95_latency > 30s for 5m"
    severity: warning
    action: "通知 oncall，自动降级模型"

  - name: "LLM API 完全不可用"
    condition: "success_rate == 0 for 2m"
    severity: critical
    action: "立即通知 oncall + 小P，启用简化模板"

  - name: "成本熔断触发"
    condition: "fuse_status in [FUSE, EMERGENCY]"
    severity: critical
    action: "阻断新请求，通知小P审批"

  - name: "批量生成失败率过高"
    condition: "batch_failure_rate > 20% for 10m"
    severity: warning
    action: "自动重试失败项，通知 oncall"

  - name: "偏见检测通过率下降"
    condition: "bias_pass_rate < 90% for 30m"
    severity: warning
    action: "检查 Prompt 版本，考虑回滚"

  - name: "Celery 队列堆积"
    condition: "queue_length > 100 for 5m"
    severity: warning
    action: "自动扩容 Worker，通知 oncall"

  - name: "Worker 失联"
    condition: "worker_heartbeat_missing > 30s"
    severity: critical
    action: "自动重启 Worker，通知 oncall"
```

---

## 九、应急响应流程

### 9.1 P0 响应流程 (LLM API 完全不可用)

```
1. 00:00 系统检测到连续失败
2. 00:00 自动触发告警 (PagerDuty/Slack)
3. 00:01 自动启用 LRU 缓存响应（仅对缓存命中请求）
4. 00:02 自动切换到备用 Provider
5. 00:05 若备用 Provider 也失败，启用简化模板
6. 00:10 通知小P和 oncall 工程师
7. 00:30 若仍未恢复，暂停新批次生成，保留队列
8. 持续监控，恢复后自动切换回正常模式
```

### 9.2 P4 响应流程 (成本熔断)

```
1. 系统检测到成本达到 FUSE 阈值
2. 立即阻断新 LLM 调用
3. 通知小P (PM) 审批
4. 小P 确认后，手动重置熔断或调整预算
5. 或等待自然日/周重置
6. 期间缓存命中请求仍可服务
```

---

## 十、预案验证与演练

### 10.1 验证清单

| 验证项 | 方法 | 频率 |
|--------|------|------|
| 缓存预热效果 | 对比预热前后的缓存命中率 | 每次部署 |
| Provider 切换 | 模拟主 Provider 失败，验证切换时间 | 每月 |
| 成本熔断 | 模拟成本达到阈值，验证阻断行为 | 每季度 |
| 简化模板 | 验证简化模板生成的画像质量 | 每季度 |
| 队列扩容 | 模拟队列堆积，验证自动扩容 | 每月 |
| 死信队列 | 模拟任务失败，验证重试和人工审核 | 每季度 |

### 10.2 演练计划

```
2026-Q3: 首次全链路演练
  - 模拟 Anthropic API 完全不可用 30 分钟
  - 验证 Provider 切换 + 简化模板降级
  - 验证队列堆积自动扩容

2026-Q4: 成本熔断演练
  - 模拟成本达到 EMERGENCY 阈值
  - 验证熔断阻断 + 小P 审批流程
  - 验证恢复后的自动降级解除
```

---

## 十一、附录

### 11.1 相关代码文件

| 文件 | 职责 |
|------|------|
| `src/aicbc/llm/client.py` | LLM 调用、重试、缓存 |
| `src/aicbc/cost/fuse.py` | 成本熔断、模型降级 |
| `src/aicbc/generators/profile_generator.py` | 画像生成、fallback |
| `src/aicbc/agents/consumer_generator.py` | 批量生成、错误隔离 |
| `src/aicbc/agents/base.py` | Agent 基础框架、自校正 |
| `src/aicbc/core/scoring/bias_auditor.py` | 偏见审计 |
| `src/aicbc/core/scoring/authenticity_scorer.py` | 真实性评分 |
| `configs/prompts/persona_generation.txt` | Prompt 模板 |

### 11.2 相关配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `LLM_MAX_RETRIES` | 3 | LLM 调用最大重试次数 |
| `LLM_TIMEOUT_SECONDS` | 120 | LLM 调用超时时间 |
| `COST_FUSE_DAILY_CNY` | 1000 | 每日成本熔断阈值 |
| `COST_FUSE_WEEKLY_CNY` | 5000 | 每周成本熔断阈值 |
| `COST_FUSE_MONTHLY_CNY` | 20000 | 每月成本熔断阈值 |
| `COST_FUSE_DEGRADE_MODEL` | claude-haiku-4-5 | 降级模型 |

### 11.3 联系人与升级路径

| 级别 | 联系人 | 升级条件 |
|------|--------|---------|
| L1 | oncall 工程师 | 所有告警 |
| L2 | 小应 (LLM Engineer) | 技术问题持续 > 30 分钟 |
| L3 | 小P (PM) | 成本熔断、业务影响 |
| L4 | 小伦 (Ethics) | 偏见检测大规模失败 |

---

> **文档维护**：本预案每季度 review 一次，或在重大架构变更后更新。  
> **下次 review**：2026-09-16
