# ToolCalling 协议设计

> **版本**：v1.0
> **定位**：定义AI_CBC全链路Agent工具调用标准，统一工具注册、调用、错误处理与超时机制
> **负责人**：小端（后端/工具集成工程师）
> **相关文档**：
> - `docs/数据字典.md` — 数据实体定义
> - `docs/全链路集成架构设计.md` — 系统集成架构
> - `src/aicbc/agents/base.py` — Agent基类

---

## 一、设计目标

ToolCalling协议解决以下问题：

1. **标准化接口**：所有子系统工具使用统一的注册、调用、返回格式
2. **数据流契约**：明确 `PersonaProfile` → `CBCRawDataset` → `AnalysisResult` 的转换规范
3. **可靠性**：内置超时、重试、错误分类，防止级联故障
4. **可观测性**：每次工具调用记录耗时、重试次数、状态码

---

## 二、核心概念

### 2.1 架构位置

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 层 (LLM Agent)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ GEN Agent   │  │ SIM Agent   │  │ Analysis Agent      │ │
│  │ (画像生成)   │  │ (选择模拟)   │  │ (统计分析)           │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┴─────────────────────┘            │
│                          │                                  │
│                          ▼                                  │
│              ┌───────────────────────┐                     │
│              │   ToolCalling Protocol │                     │
│              │   (工具调用协议层)      │                     │
│              └───────────┬───────────┘                     │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         ▼                ▼                ▼                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ 画像→问卷   │  │ 作答→数据集  │  │ 结果→报告   │       │
│  │ 上下文绑定  │  │ 聚合转换     │  │ 上下文转换  │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心类型

| 类型 | 说明 | 对应代码 |
|---|---|---|
| `ToolSpec` | 工具规格定义（名称、参数、超时、重试策略） | `protocol.py:ToolSpec` |
| `ToolCallRequest` | 工具调用请求（工具名、参数、超时、元数据） | `protocol.py:ToolCallRequest` |
| `ToolCallResult` | 工具调用结果（状态、数据、错误、耗时） | `protocol.py:ToolCallResult` |
| `ToolRegistry` | 工具注册中心（注册、注销、调用、列表） | `protocol.py:ToolRegistry` |

---

## 三、协议规范

### 3.1 工具注册

```python
from aicbc.tools.protocol import ToolRegistry, ToolSpec, ToolParameter

registry = ToolRegistry()

spec = ToolSpec(
    name="persona_to_questionnaire_context",
    description="将消费者画像绑定到CBC问卷，生成模拟上下文",
    parameters=[
        ToolParameter(name="persona", type="object", required=True),
        ToolParameter(name="questionnaire", type="object", required=True),
    ],
    timeout_seconds=5.0,
    max_retries=0,
)

registry.register(persona_to_questionnaire_context, spec=spec)
```

**注册规则**：
- 工具名全局唯一，使用 `snake_case`
- 参数必须声明类型（`string`/`integer`/`number`/`boolean`/`array`/`object`）
- 每个工具可配置独立超时（默认30s）和重试策略
- 支持同步函数和 `async` 函数自动识别

### 3.2 工具调用

**同步调用**：
```python
from aicbc.tools.protocol import ToolCallRequest

request = ToolCallRequest(
    tool_name="persona_to_questionnaire_context",
    arguments={"persona": persona_dict, "questionnaire": q_dict},
    request_id="req-001",
)
result = registry.call(request)

if result.is_success:
    context = result.data
else:
    logger.error("tool_failed", status=result.status, error=result.error)
```

**异步调用**：
```python
result = await registry.acall(request)
```

**便捷API**：
```python
from aicbc.tools import call_tool

result = call_tool("add", a=1, b=2)
```

### 3.3 调用结果状态码

| 状态 | 含义 | 是否可重试 | 典型场景 |
|---|---|---|---|
| `SUCCESS` | 调用成功 | — | 正常返回 |
| `ERROR` | 执行错误 | 视配置 | 业务逻辑异常 |
| `TIMEOUT` | 超时 | 是 | 计算密集型任务超时 |
| `VALIDATION_ERROR` | 参数校验失败 | 否 | 缺少必填参数、未知参数 |
| `NOT_FOUND` | 工具未注册 | 否 | 工具名拼写错误 |

### 3.4 超时与重试策略

```python
spec = ToolSpec(
    name="hb_model_fit",
    description="拟合HB模型",
    timeout_seconds=300.0,           # 5分钟超时
    max_retries=2,                   # 最多重试2次
    retryable_errors=(               # 仅对这些错误重试
        ConnectionError,
        TimeoutError,
    ),
)
```

**策略说明**：
- 超时时间按工具独立配置，支持请求级覆盖
- 重试仅对 `retryable_errors` 中声明的错误类型生效
- 非重试错误（如 `ValueError`、`ValidationError`）立即失败
- 每次重试记录 `retry_count`，最终返回包含总重试次数

### 3.5 错误处理

```python
from aicbc.tools.protocol import ToolCallError, ToolValidationError, ToolTimeoutError

try:
    result = registry.call(request)
    if not result.is_success:
        # 结构化错误，无需异常
        handle_error(result)
except ToolTimeoutError as exc:
    # 超时异常（仅在直接调用函数时抛出）
    logger.warning("tool_timeout", timeout=exc.timeout_seconds)
except ToolValidationError as exc:
    # 参数校验失败
    logger.error("validation_failed", param=exc.param_name)
```

---

## 四、数据流工具集

### 4.1 工具总览

| 工具名 | 数据流 | 输入 | 输出 | 超时 |
|---|---|---|---|---|
| `persona_to_questionnaire_context` | PersonaProfile → 模拟上下文 | 画像 + 问卷 | 模拟上下文 | 5s |
| `responses_to_raw_dataset` | PersonaResponse[] → CBCRawDataset | 作答列表 + 问卷 | 标准数据集 | 10s |
| `analysis_result_to_report_context` | AnalysisResult → 报告上下文 | 分析结果 + 属性 | 报告上下文 | 5s |
| `validate_data_flow` | 任意 → 校验 | 源类型 + 目标类型 + 数据 | 校验结果 | 3s |

### 4.2 工具1：persona_to_questionnaire_context

**功能**：将消费者画像绑定到CBC问卷，生成模拟上下文。

**输入**：
```json
{
  "persona": { /* PersonaProfile序列化 */ },
  "questionnaire": { /* CBCQuestionnaire序列化 */ }
}
```

**输出**：
```json
{
  "persona_summary": "消费者画像：28岁，女，居住于新一线城市...",
  "tension_narrative": "她渴望通过高品质产品提升生活体验...",
  "scenario_injection": "早9晚7，周末打扫 看到同事晒洗碗机，心动...",
  "relevant_attributes": {"价格": 1.5, "品牌口碑": 1.5, "安装便捷性": 1.5, "能耗等级": 0.3},
  "purchase_constraints": ["厨房空间小", "租房不能大改"],
  "language_samples": ["...", "...", "..."],
  "authenticity_score": 11
}
```

**设计要点**：
- 从四层画像中提取与购买决策相关的特征
- `relevant_attributes` 根据画像的 `decision_factors` 和 `ignored_factors` 加权
- `tension_narrative` 直接注入LLM提示，保持张力一致性

### 4.3 工具2：responses_to_raw_dataset

**功能**：将消费者作答列表聚合为标准交换数据集 `CBCRawDataset`。

**输入**：
```json
{
  "responses": [ /* PersonaResponse[] */ ],
  "study_id": "dishwasher-202506",
  "attributes": [ /* Attribute[] */ ],
  "questionnaire": { /* CBCQuestionnaire */ }
}
```

**输出**：
```json
{
  "metadata": {
    "study_id": "dishwasher-202506",
    "n_respondents": 150,
    "n_choice_sets": 12,
    "n_alternatives": 3,
    "attributes": [ /* ... */ ]
  },
  "choice_records": [
    {
      "respondent_id": "persona-dw-001",
      "respondent_index": 0,
      "segment": "精致白领",
      "choice_set_id": 1,
      "choice_set_index": 0,
      "alternatives": [
        {"alt_index": 0, "chosen": true, "attributes": {"price": 2999, "brand": "美的"}},
        {"alt_index": 1, "chosen": false, "attributes": {"price": 3999, "brand": "西门子"}}
      ],
      "none_chosen": false
    }
  ]
}
```

**设计要点**：
- 每个 `PersonaResponse` 展开为 `n_choice_sets` 条 `ChoiceRecord`
- `chosen` 标志根据 `chosen_alt_index` 与 `alt_index` 匹配设置
- 空 `responses` 列表触发 `ValueError`（非静默失败）

### 4.4 工具3：analysis_result_to_report_context

**功能**：将分析结果转换为报告生成上下文。

**输入**：
```json
{
  "analysis_result": { /* AnalysisResultResponse序列化 */ },
  "attributes": [ /* Attribute[] */ ],
  "study_metadata": { /* 可选 */ }
}
```

**输出**：
```json
{
  "summary": "联合分析完成（HB模型）。共150位受访者的个体效用已估计。模型收敛良好 (R-hat max=1.040)...",
  "key_findings": [
    "最重要的属性是'价格'（重要性=42.5%）",
    "其次为'品牌'（重要性=23.8%）",
    "模型收敛良好 (R-hat max=1.040)"
  ],
  "charts_data": {
    "importance": {"labels": ["价格", "品牌", "容量"], "values": [0.425, 0.238, 0.152]},
    "convergence": {"rhat_max": 1.04, "ess_min": 1200, "converged": true},
    "wtp": ["容量: 包含2个水平对比"]
  },
  "recommendations": [
    "优先优化'价格'属性，其对消费者决策影响最大"
  ],
  "model_type": "hb",
  "processing_time": 45.2
}
```

### 4.5 工具4：validate_data_flow

**功能**：验证子系统间数据流的结构兼容性。

**支持的流**：

| 源类型 | 目标类型 | 校验内容 |
|---|---|---|
| `PersonaProfile` | `CBCRawDataset` | 必填字段：persona_id, segment, layer1-4 |
| `CBCRawDataset` | `AnalysisResult` | metadata必填字段、choice_records非空 |

---

## 五、与现有系统集成

### 5.1 与 BaseAgent 集成

```python
from aicbc.agents.base import BaseAgent
from aicbc.tools.protocol import ToolRegistry

class AnalysisAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.tool_registry = ToolRegistry()
        # 注册分析专用工具
        self.tool_registry.register(run_hb_model, spec=...)
        self.tool_registry.register(compute_wtp, spec=...)

    def execute(self, dataset, attributes):
        # 通过 ToolCalling 协议调用工具
        result = self.tool_registry.call(
            ToolCallRequest(tool_name="run_hb_model", arguments={...})
        )
        return result.data
```

### 5.2 与数据字典对齐

所有数据流工具严格遵循 `docs/数据字典.md` 定义：

- `PersonaProfile`：四层结构、字段名、约束完全一致
- `CBCRawDataset`：`metadata` + `choice_records` 结构
- `AnalysisResult`：`convergence`、`importance`、`wtp` 字段名一致
- Effects Coding 命名：`{attribute_id}_{level_index}` 规范

---

## 六、代码结构

```
src/aicbc/tools/
├── __init__.py          # 公共API导出
├── protocol.py          # 核心协议实现
│   ├── ToolSpec         # 工具规格
│   ├── ToolCallRequest  # 调用请求
│   ├── ToolCallResult   # 调用结果
│   ├── ToolRegistry     # 注册中心
│   └── 便捷API (register_tool, call_tool)
└── pipeline.py          # 数据流工具实现
    ├── persona_to_questionnaire_context
    ├── responses_to_raw_dataset
    ├── analysis_result_to_report_context
    └── validate_data_flow
```

---

## 七、测试覆盖

测试文件：`tests/test_tools_protocol.py`

| 测试类 | 覆盖内容 | 用例数 |
|---|---|---|
| `TestRegistration` | 注册、注销、自动推导、异步识别 | 5 |
| `TestSyncInvocation` | 同步调用、校验错误、超时、重试 | 7 |
| `TestAsyncInvocation` | 异步调用、异步超时 | 2 |
| `TestArgumentValidation` | 必填参数、默认值、未知参数 | 3 |
| `TestOpenAISchema` | OpenAI函数模式生成 | 1 |
| `TestConvenienceAPI` | 装饰器注册、便捷调用 | 3 |
| `TestPipelineTools` | 4个数据流工具全场景 | 8 |
| **合计** | | **29** |

---

## 八、变更日志

| 日期 | 版本 | 变更内容 | 负责人 |
|---|---|---|---|
| 2026-06-10 | v1.0 | 初始版本：ToolCalling协议 + 4个数据流工具 + 29个测试 | 小端 |

---

*本文档与代码同步维护，接口变更需同步更新测试用例。*
