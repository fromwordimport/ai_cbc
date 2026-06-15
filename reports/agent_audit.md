# AI_CBC Agent框架审查报告

> **审查人**: 小应
> **日期**: 2026-06-11
> **审查范围**: `src/aicbc/agents/`（7文件）、Prompt模板库、评估链、LLM客户端
> **关联**: SEC-012（小安发现）

---

## 一、Agent框架

### 1.1 架构评估

| 文件 | 行数 | 核心职责 |
|------|------|---------|
| `agents/__init__.py` | 43 | 公开导出接口 |
| `agents/base.py` | 405 | 三层提示架构基类 + 工具注册 + 自纠正循环 + SEC-008/010输入安全 |
| `agents/consumer_generator.py` | 328 | 消费者画像生成 Agent（继承BaseAgent） |
| `agents/analysis_agent.py` | 482 | 联合分析流水线 Agent（独立类，未继承BaseAgent） |
| `agents/evaluation_chain.py` | 555 | 一致性检验与矛盾检测（EVA-PRICE/BEAND/FEAT规则） |
| `agents/tool_protocol.py` | 896 | 工具调用协议（注册/超时/重试/链路追踪/ToolChain） |
| `agents/subsystem_tools.py` | 565 | 分析子系统工具注册（6个工具） |

**工具调用能力**：ToolRegistry、ToolCaller（sync+async）、参数校验、超时控制、指数退避重试（`min(2^attempt, 10)`秒）、链路追踪（ToolCallRecord）、工具链（ToolChain）、@tool装饰器。

**缺失**：LLM原生 function calling 未集成——ToolCaller是纯代码层调用，不走LLM的tool_use API；Agent不会根据LLM返回的tool_call自主决策。

**架构不一致**：`ConsumerGeneratorAgent`继承`BaseAgent`获得完整能力，`AnalysisAgent`是独立类无框架能力。需统一。

### 1.2 错误处理与回退

| 组件 | 策略 | 评级 |
|------|------|------|
| `BaseAgent._sanitize_task_context()` | 检测危险模式→raise ValueError | 良好 |
| `AnalysisAgent._compute_wtp()` | WTP失败→warning+None | 良好 |
| `ToolCaller` | 超时/异常→重试N次→RETRY_EXHAUSTED | 良好 |
| `ProfileGenerator._generate_layer()` | JSON失败→`_LAYER_FALLBACKS`默认值 | 良好 |
| `LLMChoiceSimulator` | LLM失败→返回随机选择 | 良好 |
| `EvaluationChain.trigger_correction()` | **仅记录意图，不执行实际纠正** | 不足 |

**关键缺失**：ModelRouter与LLMClient是两条独立路径，无"模型A失败后自动切到模型B"的跨模型回退。

---

## 二、提示模板

### 2.1 多层提示架构

代码中`base.py`的三层设计（SystemInstruction/RuleInjection/DynamicExample）职责清晰。文档`05-Prompt模板库.md`的7个模板覆盖完整场景。但**模板与代码不同步**——代码中提示词一部分在外部文件，一部分硬编码在Python字符串中，不是直接从模板库提取的。

### 2.2 Persona注入安全性（确认SEC-012）

**小安发现准确无误**。`behavior_simulator.py` L336-376和`llm_choice_simulator.py` L146-187中，`_system_prompt()`将Persona全部字段通过f-string直接嵌入system prompt：

- 年龄、性别、城市、收入、职业
- 核心价值观、消费态度、品牌偏好
- 共约20个字段，零清洗

**攻击面**：Persona字段可能包含提示注入载荷、角色切换标记、指令覆盖模式。

**现有防护均不覆盖此路径**：`BaseAgent._sanitize_task_context()`仅清洗user消息；`InputSanitizer.sanitize_text()`存在但未被prompt builder调用；`_detect_prompt_leakage()`仅检测输出泄漏。

**风险评级：HIGH**——受影响组件：BehaviorSimulator、LLMChoiceSimulator、ProfileGenerator。

---

## 三、评估链

### 3.1 一致性检验机制

| 检验 | 规则ID | 方法 | 严重度 |
|------|--------|------|--------|
| 价格行为 | EVA-PRICE-001/002 | `_check_price_consistency()` | high/medium |
| 品牌忠诚 | EVA-BRAND-001/002 | `_check_brand_consistency()` | medium/low |
| 决策因素 | EVA-FEAT-001 | `_check_feature_consistency()` | low |
| 跨任务一致性 | - | `_compute_cross_task_consistency()` (Jaccard) | 评分 |

**局限性**：价格敏感度用字符串匹配（"极高" in sensitivity），无法处理自然语言描述；仅检查binary矛盾，不检查连续梯度偏差；品牌检查仅靠频次集中度；不检查心理动机层矛盾。

### 3.2 自我纠正能力

**ConsumerGeneratorAgent自纠正**：循环设计正确（execute→evaluate→should_correct→feedback→re-execute），但**feedback参数未被实际使用**。纠正循环只是用相同prompt重新调用LLM，期望随机性产生不同结果。

**EvaluationChain纠正**：`trigger_correction()`是**存根方法**——`corrected_score=0.0`和`n_choices_replaced=0`均为硬编码，不执行实际重新模拟。

**两套纠正机制完全独立**，无数据流或触发关系。

---

## 四、LLM客户端

### 4.1 Prompt Caching——缺失

`LLMClient._call_anthropic()`未启用Anthropic prompt caching。CBC场景中，同一persona的system prompt（约2000 tokens）在所有choice set之间重复。若启用caching，仅第一次全价，后续15次按cache read（10%价格）计费。**预计节省60-80%的system prompt token成本**。

### 4.2 重试与超时

| 维度 | 实现 | 评级 |
|------|------|------|
| 重试策略 | 指数退避 `sleep(2^(attempt-1))` | 良好 |
| 可重试错误 | 仅捕获APIError，不区分4xx/5xx | 部分 |
| 跨模型回退 | **无** | 缺失 |
| 超时 | SDK层timeout；应用层无总超时 | 一般 |

### 4.3 结构化输出

- OpenAI: `response_format: {"type": "json_object"}` ——良好
- Anthropic: 仅在system prompt追加文本"respond with valid JSON only" ——**弱**
- 不使用Anthropic原生tool_use；不适用response prefill；手动剥离```json代码块是脆弱模式

### 4.4 提示泄漏检测（SEC-011）

已实现但有限：中文指标仅6个；检测到泄漏后不记录审计日志；可能对正常对话产生误报。

---

## 五、改进建议

### P0（阻塞上线）

| 编号 | 问题 | 建议 |
|------|------|------|
| P0-01 | **SEC-012**: Persona字段直接嵌入system prompt | 对每个Persona字段调用`InputSanitizer.sanitize_text()` |
| P0-02 | feedback参数未被使用 | 使feedback注入到ProfileGenerator的prompt中 |
| P0-03 | Anthropic JSON mode不稳健 | 改用response prefill `{"role":"assistant","content":"{"}` 强制JSON |

### P1（高优先级）

| 编号 | 问题 | 建议 |
|------|------|------|
| P1-01 | 无Prompt Caching | 为CBC system prompt启用Anthropic ephemeral caching，预计节省60-80% prompt token |
| P1-02 | AnalysisAgent不走BaseAgent | 重构继承BaseAgent获得统一安全能力 |
| P1-03 | EvaluationChain纠正仅为存根 | 实现实际重模拟逻辑 |
| P1-04 | ModelRouter与LLMClient未集成 | 统一路由入口，实现跨模型回退 |
| P1-05 | 提示模板与代码不同步 | 模板外置为独立文件，建立版本对应关系 |

### P2（中优先级）

| 编号 | 问题 |
|------|------|
| P2-01 | 无LLM原生tool calling |
| P2-02 | 无多轮对话记忆 + token计数 + 上下文压缩 |
| P2-03 | 价格敏感度解析简单（字符串匹配） |
| P2-04 | 两套纠正机制不联动 |
| P2-05 | 泄漏检测中文覆盖面不足 |
| P2-06 | ToolSpec重复定义 |

---

## 六、总结

**整体评估**：Agent框架架构方向正确，7个文件覆盖了提示构建→工具调用→质量评估的完整链路。

**关键风险排序**：
1. **SEC-012（P0）**——Persona字段无清洗直接嵌入system prompt（与小安发现一致）
2. **自纠正未闭环（P0-02/P1-03）**——两处自纠正均未实际生效
3. **Prompt Caching缺失（P1-01）**——CBC场景下显著的token浪费

**已实现防御**：SEC-008（输入清洗）、SEC-009（工具权限标签）、SEC-010（历史长度限制）、SEC-011（输出泄漏检测）、成本熔断（CostFuse/CostTracker）、模型路由（ModelRouter但未集成）。
