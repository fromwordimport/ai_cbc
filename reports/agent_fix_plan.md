# Agent Framework P0/P1 修复方案

> **版本**: v1.0 | **作者**: 小应(LLM应用工程师) | **日期**: 2026-06-12

---

## 审查发现总结

| 编号 | 严重度 | 问题 | 影响 |
|------|--------|------|------|
| P0-02 | 严重 | `ConsumerGeneratorAgent.execute()` 接受 `feedback` 但从未注入生成流程 | 自纠正循环退化为"相同prompt重试，赌随机性" |
| P0-03 | 严重 | `EvaluationChain.trigger_correction()` 是存根方法 | 选择矛盾检测后有记录无修正，corrected_score/n_choices_replaced 硬编码为0 |
| P1-02 | 高 | `AnalysisAgent` 未继承 `BaseAgent` | 缺少输入净化、工具权限控制、三层提示架构 |
| P1-03 | 中 | 两套纠正机制(CGAgent vs EvaluationChain)完全独立 | 画像纠正与选择纠正无数据流互通 |

---

## P0-02: Feedback注入方案

### 现状分析

**调用链**: `BaseAgent.run_with_correction()` -> `_build_correction_feedback(reason, evaluation)` -> `execute_fn(**kwargs, feedback=feedback)` -> `ConsumerGeneratorAgent.execute(feedback=...)`

**断裂点**: `consumer_generator.py` 第180-184行:
```python
if feedback:
    log.info("generation_with_feedback", feedback_preview=feedback[:100])
    # Note: ProfileGenerator doesn't natively support feedback injection.
    # For now, we rely on the LLM's context window by regenerating.
    # A more sophisticated approach would modify the prompt template.
```

`ProfileGenerator.generate(persona_id, seed_config)` 不接受 feedback 参数，`_build_prompt()` 和 `_generate_layer()` 也无 feedback 注入点。

### Feedback 应包含的信息

`_build_correction_feedback()` 已从 `evaluation` dict 提取信息。当前 `_evaluate()` 返回:
```python
{
    "authenticity_score": float,       # 0-14
    "authenticity_passed": bool,       # >= 9?
    "dimensions": [...],               # 7维度细分，每个有name/score/rationale
    "has_tension": bool,               # 标签数>=2?
    "narrative_ok": bool,              # 叙事>=50字?
    "details": AuthenticityResult,
}
```

建议 feedback 结构化为:
```python
{
    "failed_checks": [
        "内在一致性: 得分0/2 — 张力标签与叙事解释脱节",
        "语言自然度: 得分0/2 — 出现3处营销术语(性价比、痛点、场景化)",
    ],
    "specific_suggestions": [
        "请确保矛盾标签(如'高收入'+'极简主义')在心理叙事中被明确提及和解释",
        "请用口语化语言替换营销术语，想象真实消费者在微信群里的表达",
    ],
}
```

### 注入方案: 三步修改

**第一步**: `ProfileGenerator.generate()` 签名扩展
```python
def generate(
    self,
    persona_id: str,
    seed_config: SeedConfig,
    feedback: str | None = None,   # 新增
) -> PersonaProfile:
```
向后兼容 (feedback=None 时行为不变)。

**第二步**: `ProfileGenerator._build_prompt()` 注入 feedback
```python
def _build_prompt(
    self,
    layer_num: int,
    seed_config: SeedConfig,
    previous_layers: dict[int, dict[str, Any]],
    feedback: str | None = None,   # 新增
) -> str:
```
在 prompt 末尾添加一个新的替换变量 `{{correction_feedback}}`:
```
{% if correction_feedback %}
【修正指导 — 请特别注意】
上一次生成的画像存在以下问题，请在本次生成中修正：
{{correction_feedback}}
{% endif %}
```
- feedback 注入到所有4层(每层prompt都带修正指导)
- 对 Layer 1 (人口统计) 的修正指导影响最小，但对 Layer 3 (心理动机) 影响最大

**第三步**: `ConsumerGeneratorAgent.execute()` 传递 feedback
```python
def execute(self, ..., feedback: str = "") -> PersonaProfile:
    ...
    profile = self.call_tool(
        "generate_profile",
        persona_id=persona_id,
        seed_config=seed_config,
        feedback=feedback,   # 新增传递
    )
```

### 风险

- feedback 文本可能过长导致 prompt 膨胀 (已有 `_MAX_TASK_CONTEXT_LENGTH=4000` 保护)
- feedback 措辞可能被 LLM 理解为"强制要求"导致过度修正
- 解决方案: feedback 用"【修正指导】"而非"【必须】"语气

---

## P0-03: trigger_correction 实现方案

### 现状分析

`EvaluationChain.trigger_correction()` 当前代码(第247-281行):
```python
def trigger_correction(self, persona, questionnaire, report) -> CorrectionRecord:
    ...
    record = CorrectionRecord(
        ...
        corrected_score=0.0,      # 硬编码 — 应来自重新模拟后的评估
        n_choices_replaced=0,     # 硬编码 — 应计数实际替换的选择
    )
    self._correction_history.append(record)
    return record
```

方法没有调用任何重新模拟逻辑，也没有传入 `LLMChoiceSimulator` 实例。

### 需要传递的数据

从 `EvaluationReport` 中提取:
```python
{
    "persona_id": str,
    "contradictions": [
        {
            "rule_id": "EVA-PRICE-001",
            "category": "price_behavior",
            "severity": "high",
            "description": "价格敏感度为'极高'却持续选择高价选项",
            "expected_behavior": "倾向于选择低价选项",
            "actual_behavior": "平均选择价格¥4500，仅20%选择低价",
        },
        ...
    ],
    "problematic_choice_set_indices": [2, 5, 7],  # 需从contradictions推导
}
```

### 实现方案: 四步修改

**第一步**: `LLMChoiceSimulator` 新增 `resimulate_sets()` 方法
```python
def resimulate_sets(
    self,
    persona: PersonaProfile,
    questionnaire: CBCQuestionnaire,
    set_indices: list[int],
    contradiction_descriptions: list[str],
    seed: int | None = None,
) -> tuple[list[ChoiceRecord], list[SingleChoiceDetail], float]:
    """Re-simulate specific choice sets with contradiction awareness.

    Args:
        persona: The virtual consumer to roleplay.
        questionnaire: The full CBC questionnaire.
        set_indices: Indices of choice sets to re-simulate.
        contradiction_descriptions: Human-readable descriptions of what
            went wrong (e.g., "你的价格敏感度很高，但你选了高价选项").
        seed: Random seed.

    Returns:
        (new_choice_records, new_single_choices, cost_cny).
    """
```
修改 `_build_system_prompt()` 或新增一个带反馈的系统提示构建函数:
```python
def _build_correction_system_prompt(persona, contradictions):
    base = _build_system_prompt(persona)
    corr_lines = [
        "\n\n【自我纠正指令】",
        "在之前的购物选择中，你的行为与你的真实性格存在矛盾：",
    ]
    for c in contradictions:
        corr_lines.append(f"- {c}")
    corr_lines.append(
        "\n请重新做出选择，确保选择体现你的真实性格和偏好。"
        "不要刻意反转所有之前的选择——只修正那些明显不符合你性格的选择。"
    )
    return base + "\n".join(corr_lines)
```

**第二步**: `EvaluationChain` 新增 `_derive_problematic_sets()` 方法
```python
def _derive_problematic_sets(
    self,
    contradictions: list[ContradictionFinding],
    questionnaire: CBCQuestionnaire,
    response: PersonaResponse,
) -> list[int]:
    """Derive which choice set indices are problematic based on contradictions.
    
    当前 contradictions 不直接包含 choice_set_index，需要增加此映射。
    方案: 在 _check_price_consistency 等检测方法中记录具体 choice_set_index。
    """
```

**第三步**: 扩展 `ContradictionFinding` 数据结构
```python
@dataclass
class ContradictionFinding:
    ...
    affected_choice_sets: list[int] = field(default_factory=list)  # 新增
```

**第四步**: 重写 `trigger_correction()`
```python
def trigger_correction(
    self,
    persona: PersonaProfile,
    questionnaire: CBCQuestionnaire,
    report: EvaluationReport,
    response: PersonaResponse,              # 新增参数
    simulator: LLMChoiceSimulator,          # 新增参数
) -> CorrectionRecord:
    # 1. 确定需要重新模拟的选择集
    problematic_sets = self._derive_problematic_sets(
        report.contradictions, questionnaire, response
    )
    
    # 2. 构建矛盾描述
    descriptions = [c.description for c in report.contradictions]
    
    # 3. 执行重新模拟
    new_records, new_choices, cost = simulator.resimulate_sets(
        persona, questionnaire, problematic_sets, descriptions
    )
    
    # 4. 重新评估
    updated_response = response.model_copy(update={"responses": new_choices})
    new_report = self.evaluate(persona, questionnaire, updated_response)
    
    # 5. 返回真实的 CorrectionRecord
    return CorrectionRecord(
        corrected_score=new_report.consistency_score,
        n_choices_replaced=len(problematic_sets),
        ...
    )
```

### 风险

- 重新模拟=额外LLM调用=成本增加 (每choice set约$0.001-0.005)
- 修正可能不收敛: 需要在 `trigger_correction` 上也加最大重试次数
- `contradiction` 到 `choice_set_index` 的映射需要改造现有的 `_check_*` 方法

---

## P1-02: AnalysisAgent 统一方案

### 现状

`AnalysisAgent` (analysis_agent.py) 是一个独立类:
- 自己的 `__init__(config)` — 无三层提示、无工具注册
- 自己的 `run(dataset, attributes)` — 无 execute-evaluate-correct 循环
- 无输入净化 (`_sanitize_task_context`) — dataset/attributes 直接使用
- 无 AgentState 跟踪 — 无 turn 记录

### 继承 BaseAgent 需要的改动

继承 `BaseAgent[dict[str, Any]]`:

```python
class AnalysisAgent(BaseAgent[dict[str, Any]]):
    def __init__(self, config: AnalysisAgentConfig | None = None, **kwargs):
        self.config = config or AnalysisAgentConfig()
        
        system = SystemInstruction(
            role="联合分析专家",
            expertise=["分层贝叶斯模型", "MNL模型", "WTP计算", "收敛诊断"],
            constraints=[
                "R-hat > 1.1 必须报告未收敛",
                "价格系数必须为负",
                "个体效用必须使用effects coding",
            ],
        )
        rules = RuleInjection(
            rules=[
                "RULE-001: 收敛诊断: R-hat_max < 1.1, ESS_bulk_min >= 400",
                "RULE-002: 价格系数必须为负，若为正则标记warning",
                "RULE-003: 不充分的样本(<50 respondents)使用MNL作为fallback",
            ],
        )
        super().__init__(
            system_instruction=system,
            rules=rules,
            max_corrections=1,  # 分析通常不需要多次纠正
            **kwargs,
        )
        
        # 注册分析工具
        self.register_tool("validate_dataset", validate_dataset, ...)
        self.register_tool("fit_hb", self._fit_model, ...)
        self.register_tool("compute_wtp", self._compute_wtp, ...)
    
    def execute(self, dataset, attributes) -> dict[str, Any]:
        """实现 BaseAgent 的抽象方法，封装原先的 run() 逻辑"""
        # 1. SEC-008: 净化输入 (BaseAgent自动处理)
        # 2. 原有管道逻辑
        ...
    
    def _should_correct(self, evaluation):
        """分析阶段的纠正条件: 模型不收敛时触发"""
        if not evaluation.get("converged", True):
            return True, "模型未收敛，建议增加采样"
        if evaluation.get("price_anomaly"):
            return True, "价格系数异常"
        return False, ""
```

### 改动量

| 改动项 | 描述 | 工时 |
|--------|------|------|
| 类声明 + `__init__` | 添加 SystemInstruction/RuleInjection + super().__init__() | 1h |
| `execute()` 方法 | 将 `run()` 逻辑迁移到 `execute()`，保留 `run()` 作为兼容别名 | 2h |
| 工具注册 | 将分析步骤注册为 callable tools | 1h |
| 输入净化 | `_sanitize_task_context` 需要在 execute 中对 attributes/dataset 做检查 | 0.5h |
| `_should_correct()` | 实现模型不收敛时的纠正逻辑(增加采样并重试) | 1h |
| 测试更新 | 更新现有 test_analysis_* 测试 | 2h |
| **合计** | | **7.5h** |

### 是否值得现在做?

**结论: 值得，但分阶段。**

**v1 (P0优先)**: 做最小改动 — 添加输入净化和收敛纠正
- 在 `run()` 开头调用 `_sanitize_task_context` 对 dataset.metadata 做检查
- 如果模型不收敛，自动增加采样次数并重试一次
- 不改变类继承关系 `(保持向后兼容)`
- 工时: ~3h

**v2 (完整重构)**: 完整继承 BaseAgent
- 重构为 BaseAgent 子类，注册所有分析步骤为 tools
- 增加完整的三层提示和工具权限控制
- 工时: ~7.5h
- 风险: API 变更 (`run()` -> `execute()`, 但可保留兼容别名)

**建议**: 先做 v1 确保安全性(输入净化)，v2 在下个 sprint 做。

---

## P1-03: 两套纠正机制的统一

### 分析

| 维度 | CGAgent 纠正 | EvaluationChain 纠正 |
|------|-------------|---------------------|
| 阶段 | 画像生成时 | 选择模拟后 |
| 对象 | PersonaProfile | ChoiceRecord / PersonaResponse |
| 触发条件 | authenticity_score < 9 | contradiction_score > 0.3 |
| 纠正方式 | 重新生成画像 | (存根) 重新模拟选择 |
| 实现 | BaseAgent.run_with_correction | EvaluationChain.trigger_correction |

**当前**: 两套机制完全独立，画像纠正后不会触发选择重新模拟(画像变了但旧的选择还在)。

### 统一方案

```
┌─ ConsumerGeneratorAgent ────────────────────────┐
│  execute(seed) → evaluate(persona) → correct?   │
│    ↓ (persona 改变后)                            │
│    └─ 通知 EvaluationChain: persona 已改变       │
└─────────────────────────────────────────────────┘
                        ↓
┌─ EvaluationChain ───────────────────────────────┐
│  evaluate(persona, q, response) → contradictions │
│    ↓                                             │
│  trigger_correction(persona, q, response, sim)  │
│    → 重新模拟 → 重新评估                         │
└─────────────────────────────────────────────────┘
```

**建议**: 不在 v1 强制统一。两套机制处理不同层面的纠正(画像质量 vs 选择一致性)，各自独立运行即可。v1 只需:
1. 在 `EvaluationChain.evaluate()` 的返回结果中包含 `persona_version` 字段，标记评估时用的画像版本
2. 在 `CorrectionRecord` 中增加 `persona_generation_correction_count` 字段，记录画像经历过多少次纠正
3. 不做架构合并

---

## 工时估算

| 编号 | 任务 | 工时 | 依赖 |
|------|------|------|------|
| P0-02 | ProfileGenerator 扩展 feedback 参数 | 2h | 无 |
| P0-02 | ConsumerGeneratorAgent.execute 传递 feedback | 1h | 上 |
| P0-02 | prompt 模板增加 correction_feedback 块 | 1h | 上 |
| P0-02 | 单元测试更新 | 2h | 上 |
| **P0-02 小计** | | **6h** | |
| P0-03 | ContradictionFinding 增加 affected_choice_sets 字段 | 1h | 无 |
| P0-03 | _check_price/brand/feature_consistency 记录具体 choice_set_index | 3h | 上 |
| P0-03 | LLMChoiceSimulator.resimulate_sets() 新方法 | 2h | 无 |
| P0-03 | trigger_correction 重写(调用 resimulate + 重新评估) | 2h | 上 |
| P0-03 | 单元测试更新 | 2h | 上 |
| **P0-03 小计** | | **10h** | |
| P1-02 | AnalysisAgent v1 输入净化 + 收敛重试 | 3h | 无 |
| **P1-02 v1 小计** | | **3h** | |
| P1-03 | EvaluationReport 增加 persona_version 字段 | 0.5h | 无 |
| P1-03 | CorrectionRecord 增加 persona_generation_correction_count | 0.5h | 无 |
| **P1-03 小计** | | **1h** | |
| **总计** | | **20h** | |

**v2 延后项**:
- P1-02 v2: AnalysisAgent 完整继承 BaseAgent (7.5h)
- P1-03 v2: 两套纠正机制架构合并 (8h)

---

## 实施顺序建议

```
Day 1-2:  P0-02 (6h) → 画像生成的自纠正回路真正生效
Day 2-4:  P0-03 (10h) → 选择矛盾检测后有实际修正
Day 4:    P1-02 v1 (3h) → 分析阶段输入安全
Day 4:    P1-03 (1h) → 纠正记录可追溯
Day 5:    集成测试 + 端到端验证
```
