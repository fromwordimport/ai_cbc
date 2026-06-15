# ModelRouter 与 CostFuse 统一方案

> **提案人**: 小控
> **日期**: 2026-06-11
> **引用**: cost_audit.md P0-3 (双预算状态机), P0-4 (定价表双写)

---

## 一、现状分析

### 1.1 两条预算决策链（完全独立）

```
调用方                      LLMClient.generate()
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
     CostFuse.pre_call_check()      (ModelRouter.route() 未被调用!)
              │
              ▼
     CostTracker.should_allow_call()
       ├── 多维度: study/daily/weekly/monthly
       ├── 线程安全: threading.Lock()
       ├── 持久化: data/cost_state.json
       └── 自动重置: _maybe_reset_budgets()
```

```
ModelRouter (独立于以上链路，自行维护)
  ├── _current_budget_status  (手动 update_budget_status())
  ├── _current_daily_cost     (手动喂入)
  ├── _daily_budget           (从 settings 读取一次)
  └── route() → 基于独立状态做 NORMAL/WARNING/DEGRADE/FUSE/EMERGENCY 决策
```

**冲突场景**：如果外部代码调用了 `ModelRouter.update_budget_status(500, 1000)` 但 `CostTracker` 实际累计已达 1100（FUSE），那么 `ModelRouter.route()` 返回 NORMAL 模型，而 `CostFuse.pre_call_check()` 返回 blocked。两套逻辑输出矛盾决策。

### 1.2 定价表双写

| 位置 | 模型数 | 示例值 (claude-sonnet-4-6) | 备注 |
|------|--------|---------------------------|------|
| `LLMClient._COST_PER_1K` (L38) | 6 | (3.0, 15.0) /M tokens | 含 gpt-4-turbo、claude-opus-4-6 |
| `ModelRouter.DEFAULT_MODELS` (L97) | 5 | (0.003, 0.015) /1k tokens | 含 claude-opus-4-8 |

差异：Router 写 `claude-opus-4-8`，Client 写 `claude-opus-4-6` 和 `gpt-4-turbo`。数值一致（仅单位不同 `/M` vs `/1k`），但任何价格调整需改两处。

### 1.3 补充发现：ModelRouter.route() 零生产调用

经 grep 确认，`ModelRouter.route()` 仅在自身 docstring 示例中被调用（L12），**全量生产代码（LLMClient、behavior_simulator、llm_choice_simulator 等）均不经过 ModelRouter**。实际调用链为：

```
behavior_simulator / llm_choice_simulator
  → LLMClient.generate(study_id=...)
    → CostFuse.pre_call_check()   ← 唯一预算决策点
    → _call_anthropic() / _call_openai()
    → CostFuse.record_call()
```

ModelRouter 当前是**存在但未接线的独立模块**。这降低了 P0-3 方案的紧迫性（双状态机目前不会在运行时冲突），但也意味着统一方案同时是**接线方案**——将任务感知路由真正接入调用链。

---

## 二、P0-3 统一方案：双预算状态机

### 方案 A（推荐）: ModelRouter.route() 内调 CostFuse.pre_call_check()

```
ModelRouter.route(task)
  │
  ├─ 1. 调用 CostFuse.pre_call_check(study_id)
  │      └─ 唯一状态源: CostTracker (多维度,线程安全,持久化)
  │
  ├─ 2. 根据返回的 (allowed, status, effective_model) 决策:
  │      - FUSE/EMERGENCY → raise RuntimeError (阻断)
  │      - DEGRADE → 使用 CostFuse 返回的 effective_model
  │                    或 fallback 到 rule.degrade_model
  │      - WARNING + low_priority → 主动降级
  │      - NORMAL → rule.default_model
  │
  ├─ 3. 保留 ModelRouter 独有逻辑:
  │      - 任务类型 → 路由规则 (persona→sonnet, review→haiku, deep→opus)
  │      - 故障计数 & 自动禁用 (10次失败)
  │      - A/B 测试配置
  │      - preferred_model 覆盖
  │
  └─ 4. 废弃: update_budget_status(), _current_budget_status, _current_daily_cost
       (这些字段变为只读镜像，或直接删除)
```

**优点**：
- CostFuse/CostTracker 成为唯一预算状态源，消除冲突
- 保留 ModelRouter 的任务路由、故障转移、A/B 测试等成熟逻辑
- 改动集中在 `route()` 方法（约 20 行），风险可控
- 现有 49 个测试不受影响（CostFuse 不感知调用方）

**缺点**：
- ModelRouter 增加对 CostFuse 的依赖
- 需额外传入 `study_id` 参数到 `route()`

### 方案 B: 废弃 ModelRouter 独立状态机，路由完全委托 CostFuse

```
ModelRouter.route(task)
  │
  └─ 仅做任务→默认模型映射，不做预算决策
      预算决策完全由 LLMClient.generate() 中的 CostFuse.pre_call_check() 负责
      删除: _current_budget_status, update_budget_status(), BudgetStatus enum
```

**优点**：
- 最简单，ModelRouter 退化为纯任务→模型查找表
- 无状态同步问题

**缺点**：
- 丢失 WARNING 级别的选择性降级（"低复杂度任务主动降级"）
- 丢失任务感知降级：CostFuse 只有一个全局 `degrade_model`，
  无法区分 "persona生成降级到haiku" vs "深度分析降级到sonnet"
- 丢失故障计数与自动禁用（10次失败）
- CostFuse 需要承担更多路由逻辑，职责膨大

### 推荐结论: 方案 A

原因：
1. **保留已有的路由智能** — ModelRouter 的任务感知路由（persona用sonnet、review用haiku、deep_analysis用opus）是经过设计的，方案B会丢失这些
2. **故障转移不能丢** — 10次失败自动禁用的 failover 机制在 CostFuse 中没有等价物
3. **改造量小** — `route()` 方法增加 ~20 行，删除 `update_budget_status()` 调用和2个实例变量
4. **唯一真相源** — CostTracker 已经线程安全+持久化+多维度，ModelRouter 无需重复造轮子

---

## 三、P0-4 统一方案：统一定价模块

### 新建 `src/aicbc/config/pricing.py`

```python
"""Unified LLM model pricing registry.

Single source of truth for all model pricing data.
Used by both LLMClient (cost estimation) and ModelRouter (routing decisions).

Pricing format: (input_cost_per_1k_tokens_USD, output_cost_per_1k_tokens_USD)
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ModelPricing:
    """Pricing and metadata for a single model."""
    provider: str          # "anthropic" | "openai"
    input_cost_per_1k: float   # USD per 1K input tokens
    output_cost_per_1k: float  # USD per 1K output tokens
    max_tokens: int
    quality_tier: str      # "highest" | "high" | "medium"


# === Central pricing registry ===
# Update prices HERE only; all consumers read from this module.

MODEL_REGISTRY: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4-8": ModelPricing(
        provider="anthropic",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
        max_tokens=200_000,
        quality_tier="highest",
    ),
    "claude-sonnet-4-6": ModelPricing(
        provider="anthropic",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        max_tokens=200_000,
        quality_tier="high",
    ),
    "claude-haiku-4-5": ModelPricing(
        provider="anthropic",
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        max_tokens=50_000,
        quality_tier="medium",
    ),
    # OpenAI
    "gpt-4o": ModelPricing(
        provider="openai",
        input_cost_per_1k=0.005,
        output_cost_per_1k=0.015,
        max_tokens=128_000,
        quality_tier="high",
    ),
    "gpt-4o-mini": ModelPricing(
        provider="openai",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.00060,
        max_tokens=128_000,
        quality_tier="medium",
    ),
    "gpt-4-turbo": ModelPricing(
        provider="openai",
        input_cost_per_1k=0.010,
        output_cost_per_1k=0.030,
        max_tokens=128_000,
        quality_tier="high",
    ),
}


def get_pricing(model: str) -> ModelPricing | None:
    """Look up pricing for a model. Returns None if unknown."""
    return MODEL_REGISTRY.get(model)


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate LLM call cost in USD."""
    p = MODEL_REGISTRY.get(model)
    if p is None:
        return 0.0
    return (prompt_tokens * p.input_cost_per_1k + completion_tokens * p.output_cost_per_1k) / 1000.0
```

### 改造范围

| 文件 | 改动 |
|------|------|
| `src/aicbc/config/pricing.py` | **新建** — 唯一定价源 |
| `src/aicbc/llm/client.py` | 删除 `_COST_PER_1K` 字典 (L38-49)，`_estimate_cost()` 改为调 `pricing.estimate_cost_usd()` |
| `src/aicbc/llm/router.py` | 删除 `DEFAULT_MODELS` 中的 `input_cost_per_1k`/`output_cost_per_1k` 字段（或改为从 `pricing.MODEL_REGISTRY` 读取），`ModelConfig` 改为引用 `ModelPricing` |

### 向后兼容

- `LLMClient._estimate_cost()` 签名不变，仅内部实现改为调 `pricing.estimate_cost_usd()`
- `ModelRouter.DEFAULT_MODELS` 保留 `ModelConfig` 结构，但定价字段从 `pricing.MODEL_REGISTRY[name]` 懒加载
- 所有现有测试应通过（价格数值不变）

---

## 四、工作量估算

| # | 任务 | 文件 | 性质 | 估时 |
|---|------|------|------|------|
| 1 | 新建统一定价模块 | `config/pricing.py` (新) | 新建 ~50行 | 30min |
| 2 | LLMClient 改用统一定价 | `llm/client.py` | 删除 `_COST_PER_1K`，改 `_estimate_cost()` | 20min |
| 3 | ModelRouter 改用统一定价 | `llm/router.py` | `ModelConfig` 定价字段从 registry 读 | 20min |
| 4 | ModelRouter.route() 集成 CostFuse | `llm/router.py` | `route()` + ~20行，删独立状态变量 | 1h |
| 5 | ModelRouter 增加 study_id 参数 | `llm/router.py` | `route(task, study_id=None)` 签名 | 10min |
| 6 | ~~更新调用方~~ | ~~各处~~ | 跳过：route() 零生产调用，无需改调用方 | 0 |
| 7 | ModelRouter + CostFuse 集成测试 | `tests/` (新) | 5-8 用例 | 1.5h |
| 8 | 回归测试 | `tests/` (现有) | 确认 49 用例全通过 | 30min |

| 合计 | **~0.8 人日** (含测试，跳过调用方更新) |
|------|----------------------------------------|

---

## 五、实施顺序

```
Phase 1: P0-4 统一定价模块 (不依赖任何改动，可独立交付)
  1 → 2 → 3   (新建 pricing.py → 改 client.py → 改 router.py)

Phase 2: P0-3 ModelRouter 集成 CostFuse (依赖 Phase 1)
  4 → 5 → 6   (改 route() → 加 study_id → 更新调用方)

Phase 3: 测试验证
  7 → 8       (集成测试 → 回归测试)
```

Phase 1 和 Phase 2 无强依赖，可先后执行；Phase 1 建议先行（风险更低，消除定价双写后可独立验证）。

---

## 六、风险与注意事项

1. **ModelRouter.route() 零生产调用（已确认）** — 方案A的改造本质上是"接线 + 统一"：在 `route()` 内部完成 CostFuse 集成后，无需更新调用方（步骤6可跳过）。真正的接线工作是在 `LLMClient.generate()` 中增加 `router.route()` 调用，但这属于可选增强——当前 `CostFuse.pre_call_check()` 已覆盖阻断和降级
2. **CostFuse 依赖 CostTracker 单例** — `ModelRouter` 构造时需获取 `CostFuse` 实例，可通过依赖注入或模块级 `get_cost_tracker()` 获取
3. **study_id 可选** — `route()` 中 `study_id` 默认 `None`，CostFuse 在无 study_id 时只检查全局/日/周/月维度，行为正确
4. **不删除 BudgetStatus enum** — 保留为兼容层（标记 deprecated），避免破坏外部引用
5. **接线优先级** — 当前 CostFuse 已提供模型降级（全局 degrade_model），ModelRouter 的任务感知路由（persona用sonnet、deep用opus）作为后续增强，不阻塞本次统一
