# AI_CBC 成本管控审查报告

> **审查人**: 小控
> **日期**: 2026-06-11
> **审查范围**: `src/aicbc/cost/`, `src/aicbc/llm/`, `src/aicbc/monitoring/`, 相关测试文件

---

## 一、成本追踪模块

### 1.1 模块清单

| 模块 | 文件 | 状态 |
|------|------|------|
| 核心追踪器（主） | `src/aicbc/cost/tracker.py` (500行) | 活跃，线程安全 |
| 熔断器 | `src/aicbc/cost/fuse.py` (169行) | 活跃 |
| 模型路由器 | `src/aicbc/llm/router.py` (476行) | 存在但未与 CostFuse 联动 |
| 旧追踪器（冗余） | `src/aicbc/monitoring/cost_tracker.py` (434行) | 孤岛，无任何代码引用 |
| Prometheus 指标 | `src/aicbc/monitoring/metrics.py` | 活跃（但仅旧追踪器使用） |

### 1.2 计费精度

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Token 计费精度 | PASS | `_estimate_cost()` 按 `(prompt_tokens * input_price + completion_tokens * output_price) / 1000` 计算 |
| 模型差异化定价 | PASS | `_COST_PER_1K` 字典覆盖 Anthropic 3 模型和 OpenAI 3 模型 |
| 汇率转换 | PASS | `_USD_TO_CNY = 7.2` |
| 价格表完整性 | WARN | `ModelRouter.DEFAULT_MODELS` 引用 `claude-sonnet-4-6` 作为 deep_analysis 默认模型，但 `LLMClient._COST_PER_1K` 定价一致 |
| 定价双写风险 | WARN | `LLMClient._COST_PER_1K` 和 `ModelRouter.DEFAULT_MODELS` 各自维护定价表 |
| 缓存计费 | PASS | `CostRecord` 有 `cached: bool` 字段 |

### 1.3 累计逻辑与并发安全

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 并发安全（数据操作） | PASS | 所有读写操作通过 `threading.Lock()` 保护 |
| 并发安全（单例创建） | WARN | `get_cost_tracker()` 非原子操作 |
| 多维度累计 | PASS | per_study / daily / weekly / monthly / global |
| 日/周/月自动重置 | PASS | `_maybe_reset_budgets()` |
| 旧追踪器线程安全 | FAIL | `monitoring/cost_tracker.py` 完全无锁保护 |
| 累计溢出保护 | WARN | `CostSummary.records` 列表无限增长 |

### 1.4 study_id 传递链（与上期对比）

| 检查点 | 上期(6月10日) | 本期(6月11日) |
|--------|-------------|-------------|
| `LLMClient.generate(study_id=)` | FAIL: 硬编码 None | PASS: 透传 |
| `pre_call_check(study_id=)` | FAIL: 硬编码 None | PASS: 透传 |
| `record_call(study_id=)` | FAIL: 无 | PASS: 透传 |

---

## 二、熔断机制

### 2.1 五级阈值表

| 级别 | 触发条件 | 降级行为 | 状态 |
|------|---------|---------|------|
| NORMAL | < 80% | 正常执行 | PASS |
| WARNING | >= 80% | 日志告警，低优先级任务可主动降级 | PASS |
| DEGRADE | >= 95% | 自动切换到 `degrade_model`（默认 `claude-haiku-4-5`） | PASS |
| FUSE | >= 100% | 阻断所有新 LLM 调用，抛出 `CostFuseError` | PASS |
| EMERGENCY | >= 120% | 阻断所有调用（与 FUSE 行为相同，仅日志级别更高） | WARN |

### 2.2 告警通知机制

| 通知渠道 | 状态 | 说明 |
|----------|------|------|
| 结构化日志 | PASS | WARNING/DEGRADE->warning, FUSE/EMERGENCY->error |
| 状态变更去重 | PASS | `_last_notified_status` |
| 邮件/Webhook | FAIL | 未实现 |
| 通知小P | FAIL | 仅错误文案，不实际发送通知 |

### 2.3 恢复机制

| 恢复路径 | 状态 | 说明 |
|----------|------|------|
| 日/周/月预算自动重置 | PASS | `_maybe_reset_budgets()` |
| 进程重启恢复 | PASS | `_load_state()` 从 `./data/cost_state.json` |
| 手动重置 API | FAIL | 无管理端点 |

### 2.4 预算配置

| 配置项 | 默认值 | 环境变量 | .env.example |
|--------|--------|----------|-------------|
| `single_study_cny` | 500.0 | `COST_FUSE_SINGLE_STUDY_CNY` | 是 |
| `daily_cny` | 1000.0 | `COST_FUSE_DAILY_CNY` | 是 |
| `weekly_cny` | 5000.0 | `COST_FUSE_WEEKLY_CNY` | 是 |
| `monthly_cny` | 20000.0 | `COST_FUSE_MONTHLY_CNY` | **否 -- 缺失** |
| `degrade_model` | `claude-haiku-4-5` | `COST_FUSE_DEGRADE_MODEL` | 是 |

---

## 三、模型路由

### 3.1 成本感知路由

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 成本感知切换 | PASS | `ModelRouter.update_budget_status()` |
| 与 CostFuse 联动 | FAIL | ModelRouter 维护独立 `_current_budget_status`，不读取 CostTracker |
| DEGRADE 降级 | PASS | 强制使用 `rule.degrade_model` |
| WARNING 选择性降级 | PASS | 低复杂度/优先级任务降级 |
| 故障转移 | PASS | degrade->fallback->gpt-4o-mini 链 |
| 故障计数与自动禁用 | PASS | 10 次失败后自动禁用 |

### 3.2 降级链

| 任务类型 | 默认模型 | 降级模型 | 兜底模型 |
|----------|----------|----------|----------|
| persona_generation | claude-sonnet-4-6 | claude-haiku-4-5 | gpt-4o |
| choice_simulation | claude-sonnet-4-6 | claude-haiku-4-5 | gpt-4o |
| review_scoring | claude-haiku-4-5 | gpt-4o-mini | - |
| result_interpretation | claude-haiku-4-5 | gpt-4o-mini | - |
| deep_analysis | claude-sonnet-4-6 | claude-haiku-4-5 | gpt-4o |
| default | claude-sonnet-4-6 | claude-haiku-4-5 | gpt-4o |

### 3.3 关键问题：双预算状态机

`ModelRouter._current_budget_status` 与 `CostFuse.tracker -> CostTracker` 各自维护独立预算状态，可能返回不一致的模型决策。

---

## 四、测试覆盖

### 4.1 测试文件统计

| 测试文件 | 用例数 | 覆盖场景 |
|----------|--------|---------|
| test_cost_tracker.py | 18 | 基础记录、熔断阈值、CostFuse集成、通知去重 |
| test_cost_fuse_integration.py | 8 | LLMClient+CostFuse集成、批量模拟熔断 |
| test_security_cost_anomalies.py | 23 (成本相关) | 阈值边界、批量异常、熔断安全、Agent降级 |
| **合计** | **49** | |

### 4.2 未覆盖的边界条件

| 未覆盖场景 | 优先级 |
|-----------|--------|
| 持久化往返测试 | P0 |
| ModelRouter 与 CostFuse 集成测试 | P0 |
| 状态文件损坏恢复 | P1 |
| 单例并发创建 | P1 |
| 日/周/月自动重置直接测试 | P1 |
| 降级模型不可用时的回退 | P1 |

---

## 五、持久化方案建议（ISS-006）

当前已实现 JSON 文件持久化（`_save_state()` / `_load_state()`），但存在不足：

| 问题 | 严重度 |
|------|--------|
| 每次记录都写磁盘（I/O 压力大） | 高 |
| 非原子写入（崩溃可能半写） | 高 |
| 仅保存摘要，不保存 records 明细 | 中 |
| 相对路径依赖 CWD | 中 |

**推荐方案（最小改动，~30行）**：
1. 原子写入：写 `.tmp` 后 `os.replace()` 
2. 节流写入：`_dirty` 标志，每30秒批量写入
3. 路径可配置：环境变量 `COST_STATE_FILE`

---

## 六、改进建议

### P0（阻塞发布 — 4项）

| # | 问题 | 工作量 |
|---|------|--------|
| 1 | 双 CostTracker 并存，删除/废弃 `monitoring/cost_tracker.py` | 0.5天 |
| 2 | 持久化非原子写入 | 0.5天 |
| 3 | ModelRouter 与 CostFuse 未联动 | 1天 |
| 4 | 定价表双写，统一到 `config/pricing.py` | 0.5天 |

### P1（发布前 — 6项）

| # | 问题 | 工作量 |
|---|------|--------|
| 5 | 无批量成本预估前置检查 | 0.5天 |
| 6 | FUSE/EMERGENCY 行为无差异 | 0.5天 |
| 7 | 无外部告警（webhook） | 1天 |
| 8 | 单例创建非线程安全 | 0.5小时 |
| 9 | `.env.example` 缺少月度配置 | 5分钟 |
| 10 | Prometheus 指标未集成到主追踪器 | 0.5天 |

### P2（后续迭代 — 5项）

| # | 问题 |
|---|------|
| 11 | `records` 列表无限增长 |
| 12 | 无管理 API |
| 13 | 无 prompt 缓存降本 |
| 14 | 降级模型不可用时的回退 |
| 15 | `claude-sonnet-4-6` 已作为 deep_analysis 默认模型，定价完整 |

---

## 七、总结

**综合评估：中等风险**

- 五级熔断框架完整，线程安全，49 用例覆盖良好
- 上期 P0 问题基本修复（study_id 透传、持久化、自动重置）
- 当前 P0: 4 项（双 CostTracker、非原子持久化、Router 未联动、定价双写）
- 预计修复工作量：**2.5 人日**
