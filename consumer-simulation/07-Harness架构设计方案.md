# 消费者画像生成Agent — Harness架构设计方案

> **版本**：v1.0  
> **定位**：确保AI生成消费者画像时的质量、一致性与真实性的约束与校验系统  
> **设计哲学**：轻约束创造力，重校验底线

---

## 一、设计目标

| 目标 | 说明 |
|------|------|
| **结构一致性** | 输出格式统一，下游Agent可解析 |
| **逻辑自洽性** | 矛盾标签必须有叙事解释 |
| **偏见免疫** | 防止刻板印象放大 |
| **迭代可收敛** | 不通过时可自动修正，而非无限重试 |
| **人机协同** | 关键节点保留人工审核能力 |

---

## 二、总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Request Handler                           │
│  接收：生成数量、业务场景、多样性要求、人工审核阈值              │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  Seed Generator                              │
│  功能：基于标签体系生成"人生阶段+核心焦虑+消费能力"种子组合      │
│  约束：组合必须产生可见张力（内置张力检测规则）                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│               Profile Generator (LLM Agent)                  │
│  输入：种子 + 标签体系 + Prompt模板                          │
│  输出：结构化人物画像（JSON/Markdown）                       │
│  内嵌：Prompt层自检规则（先验引导）                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────▼────────┐          ┌─────────▼──────────┐
│  Schema Validator│          │  Logic Validator   │
│  结构校验        │          │  逻辑一致性校验     │
│  - 必填字段      │          │  - 矛盾标签解释     │
│  - 字段类型      │          │  - 收入-消费匹配    │
│  - 枚举值范围    │          │  - 叙事完整性       │
└───────┬────────┘          └─────────┬──────────┘
        │                             │
        └──────────────┬──────────────┘
                       │
              ┌────────▼────────┐
              │  Bias Detector  │
              │  偏见检测        │
              │  - 刻板印象扫描  │
              │  - 多样性检查    │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ Authenticity    │
              │ Scorer          │
              │ 真实感评分       │
              │  - 7维度评分    │
              │  - 总分阈值判定  │
              └────────┬────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
    ┌─────▼─────┐            ┌──────▼──────┐
    │ 通过(≥阈值) │            │ 不通过(<阈值) │
    └─────┬─────┘            └──────┬──────┘
          │                         │
          │              ┌──────────▼──────────┐
          │              │   Feedback Loop     │
          │              │   反馈修正Agent      │
          │              │   - 接收问题报告     │
          │              │   - 生成修改指令     │
          │              │   - 回传Generator   │
          │              │   (最多重试3次)      │
          │              └──────────┬──────────┘
          │                         │
          │              ┌──────────▼──────────┐
          │              │ 仍不通过 → 人工审核  │
          │              └─────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────┐
│                  Output Formatter                            │
│  输出：标准化画像文件 + 校验报告 + 元数据                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详细设计

### 3.1 Request Handler（请求处理器）

**职责**：解析用户请求，转换为内部任务描述。

**输入Schema**：

```yaml
request:
  count: 5                    # 生成数量
  scenario: "护肤品新品测试"   # 业务场景（影响画像侧重）
  diversity:
    min_age_span: 20          # 年龄跨度要求
    min_city_tiers: [1,2,3,4] # 必须覆盖的城市层级
    gender_balance: true      # 性别均衡
  quality_gate:
    min_authenticity_score: 9 # 最低真实感评分
    max_retry: 3              # 自动重试次数
    human_review_threshold: 7 # 低于此分强制人工审核
```

**输出**：`GenerationTask` 对象，供后续模块消费。

---

### 3.2 Seed Generator（种子生成器）

**职责**：生成"人生阶段+核心焦虑+消费能力"种子组合，确保组合天然产生张力。

**核心算法流程**：

```
1. 从标签体系中采样人生阶段（按业务场景加权）
2. 为该人生阶段匹配1-2个高概率焦虑标签
3. 采样收入档位（与人生阶段匹配，但允许异常值）
4. 张力检测：计算种子组合的"矛盾指数"
   - 矛盾指数 = f(人生阶段期望行为, 收入能力, 焦虑类型)
   - 指数过低（<0.3）→ 重新采样
   - 指数过高（>0.9）→ 可能不现实，降低概率
5. 输出种子 + 张力说明
```

**内置张力检测规则示例**：

```python
# 伪代码示意 — 张力规则库
tension_rules = [
    # 规则：退休+高收入 → 必须有非节俭标签才产生张力
    {
        "life_stage": "退休生活",
        "income": ">30万",
        "required_tag": ["享乐主义", "科技极客", "体验消费"],
        "tension_bonus": 0.3
    },
    # 规则：学生+高消费 → 必须有收入解释
    {
        "life_stage": "学生",
        "spending_pattern": "高消费",
        "requires_explanation": ["家庭支持", "兼职收入", "信贷消费"],
        "tension_bonus": 0.4
    },
    # 规则：初入职场+高收入 → 来源合法性
    {
        "life_stage": "初入职场单身",
        "income": ">30万",
        "requires_explanation": ["金融行业", "互联网大厂", "家族支持", "副业"],
        "tension_bonus": 0.5
    }
]
```

---

### 3.3 Profile Generator（画像生成器）

**职责**：基于种子和Prompt模板，调用LLM生成完整画像。

**Prompt结构**：

```
[系统指令] + [标签体系] + [种子信息] + [生成规则] + [输出Schema] + [自检要求]
```

**关键设计决策**：

| 设计点 | 方案 | 理由 |
|--------|------|------|
| **分层生成** | 先生成Layer 1（骨架），校验通过后再生成Layer 2-4 | 避免整篇返工，降低token成本 |
| **温度控制** | 创意层（小传、语言样本）用较高温度；结构层用较低温度 | 结构必须稳定，叙事需要变化 |
| **内嵌自检** | 要求模型在输出末尾完成"强制自检段落" | 利用LLM的自我纠错能力 |
| **输出格式** | 优先JSON + Markdown双输出 | 机器可读 + 人类可审 |

---

### 3.4 Validation Pipeline（四层校验管道）

校验管道按顺序执行，任何一层失败即触发Feedback Loop。

#### Layer A: Schema Validator（结构校验）

**职责**：确保输出符合预定义结构。

| 校验项 | 规则 | 失败处理 |
|--------|------|---------|
| 必填字段 | 所有Layer 1-4字段必须存在 | 标记缺失，Feedback Loop要求补全 |
| 枚举值 | 标签值必须在预定义枚举范围内 | 拒绝，Feedback Loop要求修正 |
| 字段类型 | 字符串/数组/数值类型正确 | 自动转换或拒绝 |
| 数组长度 | 标签数组1-3个元素 | 超限则截断或拒绝 |
| 引用完整性 | 场景中引用的标签必须在画像中存在 | 标记悬空引用 |

**实现要点**：
- 使用JSON Schema或Pydantic模型进行强类型校验
- 枚举值从`消费者画像.md`中提取，作为配置加载
- 失败信息需精确定位到字段路径（如`layer3.psychology.tension_combination`）

#### Layer B: Logic Validator（逻辑校验）

**职责**：检验画像的内在逻辑一致性。这是**最核心的校验层**。

**校验规则集**：

```
RULE-001: 矛盾标签必须有叙事解释
  触发条件：tension_combination.labels.length > 0
  通过标准：narrative_explanation.length >= 50字
  失败反馈："请为矛盾组合提供心理解释，至少50字"

RULE-002: 收入与消费行为匹配度
  触发条件：income_personal = "3万以下" AND spending_level = "高"
  通过标准：必须存在explanation（如"家庭支持""信贷""冲动后后悔"）
  失败反馈："低收入高消费需要合理解释，否则不成立"

RULE-003: 人生阶段与核心焦虑匹配度
  触发条件：life_stage = "退休生活" AND anxiety = "育儿焦虑"
  通过标准：必须有特殊说明（如"帮子女带娃""隔代抚养压力"）
  失败反馈："人生阶段与焦虑不匹配，请解释或更换"

RULE-004: 品牌关系与行为一致性
  触发条件：brand_loyalty = "单一品牌深度忠诚" AND switching_reason != null
  通过标准：switching_reason必须为空或"不适用"
  失败反馈："深度忠诚者不应有转换原因，逻辑冲突"

RULE-005: 场景反应完整性
  触发条件：scene_reactions.length < 5
  通过标准：必须覆盖5个预定义场景
  失败反馈："请补全场景反应库，当前缺少{缺失场景}"

RULE-006: 语言样本自然度初筛
  触发条件：language_samples中包含营销术语（如"品牌价值""用户痛点""心智"）
  通过标准：不得包含营销/学术术语
  失败反馈："语言样本过于正式，请使用口语化表达"

RULE-007: 秘密动机隐秘性
  触发条件：secret_motivation过于明显（如直接从标签推导）
  通过标准：表面动机与秘密动机之间需有"认知距离"
  失败反馈："秘密动机过于直白，请增加一层心理防御"

RULE-008: 时间线一致性
  触发条件：past叙事与present行为无因果链
  通过标准：present的行为至少有一条可由past解释
  失败反馈："过去经历与现在行为之间缺乏因果联系"
```

#### Layer C: Bias Detector（偏见检测）

**职责**：扫描并标记刻板印象，防止模型滑向"省力叙事"。

**检测维度**：

```
1. 刻板印象模式库（Keyword + Semantic匹配）
   ──────────────────────────────────────────
   模式A："老年人 = 被诈骗 + 不会用手机 + 节俭"
   模式B："Z世代 = 冲动 + 月光 + 沉迷短视频"
   模式C："小镇青年 = 土味 + 向往都市 + 拼多多"
   模式D："女性 = 只看颜值 + 情绪化 + 爱购物"
   模式E："男性 = 只看参数 + 理性 + 不爱逛街"
   模式F："宝妈 = 育儿焦虑 + 成分党 + 容易被种草"
   
   检测方法：
   - 关键词N-gram匹配（快速过滤）
   - 语义相似度计算（Embedding cosine similarity）
   - 阈值：similarity > 0.7 触发警告

2. 标签组合刻板度
   ─────────────────────
   统计常见"省力组合"在已有画像库中的出现频率
   如果某组合出现率 > 30%，标记为"高刻板风险"
   
   示例：
   - "退休+节俭+电视购物"出现4次/10个画像 → 高风险
   - "Z世代+情绪消费+抖音"出现5次/10个画像 → 高风险

3. 叙事简化度
   ─────────────
   检测人物小传是否只用了单一标签的"默认叙事"
   方法：计算小传文本与标签描述的互信息
   互信息过高 = 叙事过于标签化，缺乏个性化演绎

4. 多样性指数（批次级）
   ───────────────────
   计算当前批次画像的多样性得分：
   - 年龄分布熵（Shannon Entropy）
   - 城市层级覆盖度
   - 职业类别分散度
   - 核心价值观多样性
   
   低于阈值则要求增加差异化，或拒绝批次通过
```

**输出**：`BiasReport`（含风险等级、具体问题、修改建议）

#### Layer D: Authenticity Scorer（真实感评分）

**职责**：7维度评分，总分判定画像是否达到"演活人"标准。

**评分机制**：

```yaml
scoring:
  dimensions:
    - name: "内在一致性"
      weight: 1.0
      criteria: "矛盾标签有解释，行为可由动机推导"
      auto_check: true    # 可由规则引擎初评
      
    - name: "情境敏感性"
      weight: 1.0
      criteria: "场景反应与画像标签一致，不同场景有差异化"
      auto_check: false   # 需LLM辅助评分
      
    - name: "认知有限性"
      weight: 1.0
      criteria: "知识边界清晰，不表现超人理性"
      auto_check: true
      
    - name: "社会摩擦感"
      weight: 1.0
      criteria: "表现出面子、犹豫、矛盾等真实社会行为"
      auto_check: false
      
    - name: "时间延续性"
      weight: 1.0
      criteria: "过去-现在-未来叙事连贯，有因果链"
      auto_check: true
      
    - name: "语言自然度"
      weight: 1.0
      criteria: "语言风格符合身份，无营销/学术术语"
      auto_check: true
      
    - name: "知识边界感"
      weight: 1.0
      criteria: "对超出认知的领域表现真实无知或漠不关心"
      auto_check: false
  
  scale: [0, 1, 2]        # 0=不合格, 1=部分合格, 2=优秀
  passing_threshold: 9     # 满分14分，9分及格
  excellent_threshold: 12  # 12分以上为优秀
```

**评分方式**：
- **规则引擎初评**：对`auto_check: true`的维度进行快速打分
- **LLM辅助深评**：对语义类维度，调用专门的审校Agent评分
- **人机混合**：低于`human_review_threshold`时，强制等待人工确认

**评分校准说明**：
由于规则引擎评分的维度（内在一致性、认知有限性、时间延续性、语言自然度）与 LLM 辅助评分的维度（情境敏感性、社会摩擦感、知识边界感）使用不同的评分机制，可能存在系统性偏差。校准策略如下：

1. **每月校准**：抽取 30 个样本，由人工对全部 7 个维度独立评分，计算规则引擎维度与 LLM 维度的平均偏差值
2. **偏差修正**：如果两类维度的平均分差 > 0.3 分，对偏高的一方施加修正系数（如 LLM 维度平均偏低 0.4 分则统一 +0.4）
3. **阈值不调**：总分及格线 9/14 保持不变，校准只影响各维度的原始分，不改变阈值
4. **记录校准日志**：每次校准的修正系数记录在 `calibration_log` 中，便于审计

**审校Agent Prompt模板**（用于语义维度评分）：

```markdown
你是一位严苛的社会学审校员。请对以下消费者画像的真实感进行评分。

【画像】
{persona_content}

【评分维度】（每项0-2分）

1. 情境敏感性（0-2分）：
   - 场景反应是否与画像标签一致？
   - 不同场景下是否有差异化反应？
   - 评分：____
   - 理由：____

2. 社会摩擦感（0-2分）：
   - 是否表现出真实的犹豫、矛盾、面子考虑？
   - 还是过于理性、过于完美？
   - 评分：____
   - 理由：____

3. 知识边界感（0-2分）：
   - 对超出人物认知范围的事物，是否表现真实无知？
   - 还是无所不知、过度自信？
   - 评分：____
   - 理由：____

【总分】____/6
【关键问题】（如有）
【最小修改建议】（如评分<4分）
```

---

### 3.5 Feedback Loop（反馈修正循环）

**职责**：当校验不通过时，生成精确的修改指令并回传给Generator，驱动迭代优化。

**设计原则**：

```
1. 精确制导：不重新生成整个画像，只修改问题部分
2. 渐进修正：每次只解决1-2个问题，避免引入新问题
3. 重试上限：最多3次自动重试，之后转人工
4. 退化检测：如果修改后总分下降，回滚到最高分版本
5. 保留核心：修改不得破坏已验证通过的部分（尤其是矛盾张力）
```

**反馈指令模板**：

```markdown
【校验结果】
画像编号：{id}
总分：{score}/14
未通过项：{failed_items}

【修改指令】
请针对以下问题修改画像，保持其他部分不变：

问题1：{具体描述}
- 当前状态：{问题原文摘录}
- 修改方向：{明确的指导}
- 参考标准：{通过样例}

问题2：{具体描述}
- 当前状态：{问题原文摘录}
- 修改方向：{明确的指导}

【保留要求】（以下部分不得改变）
- 种子三要素：{life_stage} + {anxiety} + {income}
- 矛盾张力：{tension_combination}
- 已通过校验的字段：{passed_fields}

【历史修改记录】（避免循环修改）
- 第1次修改：{修改内容} → 结果：{改善/恶化/无变化}
- 第2次修改：{修改内容} → 结果：{改善/恶化/无变化}
```

**状态管理**：
- 每次重试保留完整历史版本
- 记录修改前后的分数变化
- 如果连续两次分数下降，触发"回滚+策略切换"（如从"targeted修正"切换为"full_regeneration"）

---

### 3.6 Output Formatter（输出格式化器）

**职责**：标准化最终输出，附带完整元数据和校验痕迹。

**输出文件结构**：

```
output/
├── personas/
│   ├── persona-001.md          # 人类可读格式（Markdown）
│   ├── persona-002.md
│   └── ...
├── personas.json               # 机器可读格式（JSON数组）
├── batch-report.md             # 批次总结报告
└── validation/
    ├── persona-001-validation.json   # 单个画像校验详情
    ├── persona-002-validation.json
    └── batch-diversity-report.json   # 批次多样性统计
```

**批次报告内容（batch-report.md）**：

```yaml
batch_report:
  meta:
    generated_at: "2026-06-07T14:30:00Z"
    model: "claude-sonnet-4-6"
    config_version: "1.0"
  
  summary:
    total_requested: 5
    total_generated: 5
    passed_automatic: 3
    passed_after_retry: 1
    pending_human_review: 1
    rejected: 0
    average_authenticity_score: 10.2
    median_authenticity_score: 10.5
  
  diversity_metrics:
    age_entropy: 0.85           # 0-1，越高越多样
    city_tier_coverage: [1,2,3]  # 实际覆盖的城市层级
    gender_ratio: "3:2"
    occupation_diversity: 0.72
    value_diversity: 0.68
    overall_diversity_score: 0.74
  
  bias_scan:
    stereotype_flags: 1
    flagged_personas: ["persona-003"]
    high_risk_combinations: ["退休+节俭+被诈骗"]
    narrative_simplification_warnings: 0
  
  quality_distribution:
    excellent (12-14): 2
    good (9-11): 2
    needs_review (7-8): 1
    rejected (<7): 0
  
  recommendations:
    - "增加二线城市画像，当前仅覆盖一线和新一线"
    - "注意避免老年人刻板印象，persona-003被标记"
    - "整体多样性良好，价值观维度可进一步扩展"
```

---

## 四、配置文件规范

```yaml
# harness-config.yaml

profile_generation:
  model:
    name: "claude-sonnet-4-6"    # 主生成模型
    backup: "gpt-4o"             # 备用模型
    temperature:
      creative: 0.8              # 小传、语言样本、秘密动机
      structural: 0.3            # 标签、枚举值、场景反应
      mixed: 0.6                 # 需要兼顾结构和新意的部分
  
  seed:
    tension_min: 0.3             # 矛盾指数最低阈值
    tension_max: 0.9             # 矛盾指数最高阈值（过高可能不真实）
    retry_on_low_tension: true   # 张力不足时重新采样
    max_seed_attempts: 10        # 最大采样尝试次数
  
  generation_strategy:
    mode: "layered"              # layered（分层）| full（全文）
    layer1_timeout: 30           # Layer 1生成超时（秒）
    full_timeout: 120            # 全文生成超时（秒）
  
  output:
    format: "both"               # markdown | json | both
    include_layer_breakdown: true
    include_self_check: true
    include_validation_trace: true  # 保留校验痕迹

validation:
  schema:
    strict_enum: true            # 枚举值严格匹配
    allow_custom_tags: false     # 不允许自定义标签
    max_tag_per_dimension: 3     # 每个维度最多标签数
  
  logic:
    ruleset: "standard"          # standard | strict | relaxed
    income_spending_check: true
    life_stage_anxiety_check: true
    brand_loyalty_consistency: true
    timeline_causality: true
  
  bias:
    stereotype_library: "default"    # 刻板印象模式库路径
    diversity_min_entropy: 0.6       # 多样性最低熵值
    flag_threshold: 0.7              # 语义相似度阈值
    max_stereotype_occurrence: 0.3   # 单组合最大出现率
  
  authenticity:
    scoring_model: "hybrid"      # rule_based | llm_assisted | hybrid
    passing_threshold: 9         # 及格线
    excellent_threshold: 12      # 优秀线
    human_review_threshold: 7    # 低于此分强制人工审核
    llm_review_model: "claude-haiku-4-5"  # 审校Agent模型

feedback_loop:
  max_auto_retry: 3            # 最大自动重试次数
  retry_strategy: "targeted"   # targeted（精确修正）| full_regeneration（全文重写）
  rollback_on_degradation: true
  preserve_tension: true       # 修改不得破坏矛盾张力
  issue_batch_size: 2          # 每次最多处理的问题数

output:
  formats: ["markdown", "json"]
  include_validation_report: true
  include_diversity_report: true
  include_generation_trace: true    # 保留生成历史

human_in_the_loop:
  enabled: true
  trigger: "threshold_or_bias"      # always | threshold_or_bias | never
  review_queue_ttl_hours: 24        # 审核队列超时时间
  notify_channels: ["slack", "email"]  # 通知渠道

  # 人工审核 SLA（服务水平协议）
  sla:
    priority_response:
      HIGH: 2    # 高危偏见/总分<7，2小时内必须响应
      MEDIUM: 8  # 重试3次未通过，8小时内响应
      LOW: 24    # 一般质量问题，24小时内响应
    escalation:
      enabled: true
      escalate_after_multiplier: 2.0  # 超时×2 后自动升级（如 HIGH 4h未响应→通知上级）
      escalate_to: ["小伦", "小P"]     # 升级通知对象
    timeout_action:
      HIGH: "auto_reject"    # 高危超时自动拒绝，画像进入 DEPRECATED
      MEDIUM: "auto_hold"    # 中危超时保留在队列中，不自动通过
      LOW: "auto_approve"    # 低危超时自动通过（仅限总分≥9的画像）
    queue_health_check:
      interval_hours: 4      # 每4小时检查队列积压
      alert_threshold: 10    # 队列积压 > 10 条时告警
      max_queue_depth: 50    # 队列深度硬上限，触发后暂停新画像生成
```

---

## 五、状态机与生命周期

```
[INIT] → 接收请求，解析配置
  │
  ▼
[SEEDING] → 生成种子组合，张力检测
  │  └─ 张力不足 → 重新采样（最多10次）
  ▼
[GENERATING-L1] → 生成Layer 1（骨架）
  │
  ▼
[VALIDATING-L1] → Schema + Logic校验Layer 1
  │  └─ 失败 → 反馈修正 → [REGENERATING-L1]
  ▼
[GENERATING-FULL] → 生成完整画像（Layer 1-4）
  │
  ▼
[VALIDATING-FULL] → 四层校验管道
  │
  ├── 全部通过 ──→ [FORMATTING] → [COMPLETED]
  │
  ├── 部分失败 ──→ [FEEDBACK] → [REGENERATING-FULL] → [VALIDATING-FULL]
  │                    ↑_____________________________________│ (循环，最多3次)
  │
  └── 严重失败 ──→ [HUMAN_REVIEW] → [ACCEPTED] → [FORMATTING] → [COMPLETED]
                                     │
                                     └──→ [REJECTED] → [ARCHIVED]
```

**状态转换条件**：

| 当前状态 | 触发条件 | 下一状态 |
|---------|---------|---------|
| VALIDATING-FULL | 所有校验通过 | FORMATTING |
| VALIDATING-FULL | 部分校验失败，重试次数<3 | FEEDBACK |
| VALIDATING-FULL | 重试次数≥3或偏见检测高危 | HUMAN_REVIEW |
| HUMAN_REVIEW | 人工通过 | FORMATTING |
| HUMAN_REVIEW | 人工拒绝 | ARCHIVED |
| FEEDBACK | 修正后分数提升 | VALIDATING-FULL |
| FEEDBACK | 修正后分数下降，有历史高分版本 | ROLLBACK → VALIDATING-FULL |
| FEEDBACK | 修正后分数下降，无历史高分版本 | HUMAN_REVIEW |

### 与画像资产状态机的衔接

Harness 状态机关注"生成+校验"，画像资产管理（`12-画像资产化管理规范.md`）关注"存储+使用"。两者的状态转换规则如下：

| Harness 终态 | 资产终态 | 转换规则 |
|-------------|---------|---------|
| COMPLETED（总分 ≥ 12） | 自动进入 PUBLISHED | 优秀画像无需人工确认，直接可用 |
| COMPLETED（9 ≤ 总分 < 12） | 自动进入 REVIEWED，由研究员手动确认后转 PUBLISHED | 合格画像留有人工确认环节 |
| HUMAN_REVIEW → ACCEPTED | REVIEWED → 研究员手动转 PUBLISHED | 人工审核通过的画像进入正常流程 |
| HUMAN_REVIEW → REJECTED | DEPRECATED | 人工拒绝的画像标记为废弃 |
| 任何终态（总分 < 9） | DRAFT（等待重新生成或人工修正） | 不及格画像不得进入 REVIEWED |

**自动转换原则**：
- 仅总分 ≥ 12 且偏见检测 PASSED 的画像可自动进入 PUBLISHED
- 偏见检测 FAILED 的画像无论分数高低均强制人工审核
- 所有自动转换记录在 `status_history` 中，`by` 字段为 `"harness_auto"`

---

## 六、异常处理策略

| 异常场景 | 检测方式 | 处理策略 |
|---------|---------|---------|
| **生成超时** | 定时器监控 | 标记为失败，保留已生成部分供人工审阅 |
| **模型API错误** | 异常捕获 | 切换备用模型，记录故障 |
| **Schema校验全部失败** | Validator返回 | 转人工审核，不自动重试 |
| **连续3次修改后分数下降** | 历史版本对比 | 回滚到最高分版本，标记为"最佳努力" |
| **偏见检测高危** | Bias Detector | 强制人工审核，不允许自动通过 |
| **多样性不足** | 批次统计 | 在下一轮生成中增加未覆盖维度的采样权重 |
| **Feedback Loop死循环** | 修改内容哈希对比 | 如果连续两次修改内容相同，强制转人工 |
| **内存/存储溢出** | 资源监控 | 清理历史版本，只保留最新+最高分版本 |

---

## 七、实施路线图

### Phase 1: MVP（最小可行产品）

**目标**：实现核心生成+底线校验，可跑通端到端流程。

**包含模块**：
- [ ] Request Handler（基础解析）
- [ ] Seed Generator（张力检测）
- [ ] Profile Generator（LLM调用+Prompt模板）
- [ ] Schema Validator（结构校验）
- [ ] Logic Validator（核心6条规则）
- [ ] Output Formatter（Markdown输出）

**验收标准**：
- 能生成5个画像，全部通过Schema+Logic校验
- 平均生成时间 < 30秒/画像
- 无结构性错误

### Phase 2: 质量提升

**目标**：加入真实感评分和反馈循环，提升输出质量。

**新增模块**：
- [ ] Authenticity Scorer（规则引擎初评）
- [ ] Feedback Loop（精确修正+重试管理）
- [ ] 分层生成策略（Layer 1先校验）

**验收标准**：
- 平均真实感评分 > 9分
- 自动通过率 > 70%
- 重试后通过率 > 90%

### Phase 3: 偏见免疫

**目标**：防止刻板印象，确保多样性。

**新增模块**：
- [ ] Bias Detector（刻板印象模式库）
- [ ] 多样性统计与报告
- [ ] Human-in-the-loop审核队列

**验收标准**：
- 偏见检测命中率 > 80%（人工标注对比）
- 多样性熵值 > 0.6
- 人工审核率 < 20%

### Phase 4: 高级功能

**目标**：完善人机协同和可观测性。

**新增模块**：
- [ ] 可视化Dashboard（多样性、质量分布、偏见趋势）
- [ ] A/B测试框架（对比不同Prompt/模型的输出质量）
- [ ] 画像库管理（去重、相似度检测、版本控制）
- [ ] 自动化回归测试（每次迭代后跑标准测试集）

---

## 八、验证方案

### 8.1 单元测试

对每个Validator编写独立测试用例：

```
Test: Schema Validator
├── 输入：完整的合法画像 → 期望：全部通过
├── 输入：缺少必填字段 → 期望：标记缺失字段
├── 输入：非法枚举值 → 期望：标记非法值
└── 输入：数组超限 → 期望：标记超限

Test: Logic Validator
├── 输入：矛盾标签无解释 → 期望：RULE-001失败
├── 输入：低收入高消费无解释 → 期望：RULE-002失败
├── 输入：忠诚者+转换原因 → 期望：RULE-004失败
└── 输入：语言样本含营销术语 → 期望：RULE-006失败

Test: Bias Detector
├── 输入：符合刻板印象的画像 → 期望：触发警告
├── 输入：打破刻板印象的画像 → 期望：通过
└── 输入：边界案例 → 期望：合理判断
```

### 8.2 集成测试

端到端测试：

```
Test: 端到端生成
├── 输入：生成5个画像，场景="护肤品"
├── 检查：
│   ├── 全部通过Schema校验
│   ├── 全部通过Logic校验
│   ├── 平均真实感评分 > 9
│   ├── 多样性熵值 > 0.6
│   └── 生成时间 < 150秒
└── 输出：批次报告 + 5个画像文件

Test: Feedback Loop收敛
├── 输入：一个故意设计有缺陷的画像
├── 检查：
│   ├── 第1轮校验：识别问题
│   ├── 第2轮校验：分数提升
│   ├── 第3轮校验：通过或转人工
│   └── 无死循环
```

### 8.3 对抗测试

用已知的高偏见种子测试系统防御能力：

```
Test: 刻板印象防御
├── 种子：退休+节俭+不会用手机+被保健品骗
├── 检查：
│   ├── Bias Detector是否触发警告
│   ├── Logic Validator是否要求解释
│   └── 最终是否转人工审核

Test: 逻辑陷阱
├── 种子：学生+年收入50万+极简主义+每天奢侈品
├── 检查：
│   ├── Logic Validator是否捕获收入-行为不匹配
│   ├── 是否要求合理解释
│   └── 无解释时是否拒绝通过
```

### 8.4 人工盲测（金标准）

```
Test: 真实感盲评
├── 准备：
│   ├── 组A：带Harness生成的10个画像
│   └── 组B：不带Harness（纯Prompt）生成的10个画像
├── 执行：
│   ├── 邀请5位消费者研究员盲评
│   ├── 评分维度：7维度真实感
│   └── 统计显著性检验（t-test）
└── 期望：
    ├── 组A平均分显著高于组B（p < 0.05）
    ├── 组A的逻辑一致性评分提升最明显
    └── 组A的刻板印象评分最低
```

---

## 九、与其他文件的衔接

| 本Harness模块 | 衔接文件 | 衔接点 |
|--------------|---------|--------|
| Seed Generator | `消费者画像.md` | 标签体系源数据 |
| Profile Generator | `05-Prompt模板库.md` | 模板一（画像生成器） |
| Logic Validator | `02-阶段一-画像生成.md` | 标签采样规则、矛盾组合 |
| Authenticity Scorer | `04-阶段三四-交互与验证.md` | 7维度校验清单 |
| Bias Detector | `01-核心理念与架构.md` | 反刻板印象设计原则 |
| Feedback Loop | `06-进阶技巧与应用场景.md` | 社交图谱、记忆衰减等扩展 |

---

## 十、设计原则总结

> **Harness是护栏，不是轨道。**

| 要约束的（底线） | 不约束的（天花板） |
|----------------|------------------|
| 结构完整性 | 创造力与想象力 |
| 逻辑自洽性 | 矛盾张力与复杂性 |
| 偏见与刻板印象 | 人物个性与独特性 |
| 输出格式统一 | 叙事风格与语言多样性 |
| 迭代收敛性 | 探索性的标签组合 |

---

## 附录：风险识别与应对

### A1. LLM输出不稳定风险

| 风险 | 影响 | 发生概率 | 应对策略 |
|------|------|---------|---------|
| **格式漂移** | LLM偶尔不遵守JSON Schema，导致解析失败 | 高（5-10%） | ①重试机制（最多3次）②保留原始输出供调试③降低temperature |
| **标签幻觉** | LLM生成标签体系中不存在的自定义标签 | 中（3-5%） | ①严格枚举校验②Prompt中强调"只能从给定列表中选择"③失败后转人工 |
| **叙事断裂** | 长文本生成中，后半部分与前半部分矛盾 | 中（5%） | ①分层生成（先骨架后血肉）②每轮生成后独立校验③缩短单次生成长度 |

### A2. 校验规则太严导致通过率低

| 阶段 | 建议规则集 | 预期通过率 | 收紧时机 |
|------|-----------|-----------|---------|
| **MVP阶段** | 只启用RULE-001（矛盾解释）+ RULE-006（语言自然度） | 80%+ | 运行2周后 |
| **成熟阶段** | 启用全部6条核心规则 | 70%+ | 运行1个月后 |
| **严格阶段** | 启用全部规则 + Bias检测 | 60%+ | 数据积累3个月后 |

**关键原则**：先让系统"跑起来"收集数据，再逐步收紧规则。过早启用全部规则会导致通过率低、成本高、团队挫败感强。

### A3. 成本不可控风险

| 成本项 | MVP单价 | 月预估（1000画像/月） | 控制策略 |
|--------|--------|---------------------|---------|
| **画像生成** | ¥0.5-2元/个 | ¥500-2000 | ①缓存已通过画像②批量生成时设预算上限③优先使用性价比模型（如Claude Haiku做初筛） |
| **模拟执行** | ¥0.3-1元/次 | ¥300-1000 | ①复用画像减少重复生成②模拟输出缓存（同一画像+同一情境） |
| **审校评分** | ¥0.1-0.3元/次 | ¥100-300 | ①规则引擎优先，LLM辅助只做语义维度②审校结果缓存 |
| **存储** | - | ¥200-500 | ①90天自动归档至冷存储②压缩历史数据 |

**成本熔断机制**：
- 单日LLM调用费用超过预算的80% → 自动限流
- 单月费用超过预算 → 暂停非紧急任务，通知管理员
- 单个画像生成重试3次仍未通过 → 强制转人工，不再消耗LLM token

### A4. 反馈循环死锁风险

| 死锁模式 | 检测方法 | 自动处理 |
|---------|---------|---------|
| **修改无效** | 连续两次FIX后问题相同 | 第3次直接转人工 |
| **分数退化** | 修正后分数连续下降 | 回滚到最高分版本，转人工 |
| **哈希不变** | FIX后内容哈希与上次相同 | 立即转人工 |
| **循环修正** | A→B→A→B 循环 | 检测后强制转人工 |

---

*本方案为架构设计文档，不包含具体代码实现。各模块可根据团队技术栈（Python/Node/Go等）选择合适的方式落地。*
