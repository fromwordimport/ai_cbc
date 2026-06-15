# BiasAuditor 实现方案
> 小伦 | 2026-06-11

## 审前摘要

当前 `BiasAuditor` (281行) 仅实现5条关键词规则，规范要求4步审计管线 + 5项检查均未完整实现。`ConsumerGeneratorAgent` 未集成 `BiasAuditor`，FAILED 画像无条件入库。本方案给出 P0-001 和 P0-002 的可编码实现方案。

---

## P0-001: 4步审计管线

### 总体架构

不改动 `BiasAuditor` 的调用接口（`audit()` 和 `audit_batch()` 签名不变），在其内部扩展为4步管线。每一步作为独立私有方法实现，可单独测试。

新增文件：
- `src/aicbc/core/scoring/bias_auditor.py` — 在现有文件上扩展（约281行→约600行）
- `src/aicbc/core/scoring/stereotype_patterns.py` — 24模式库常量定义
- 无全新文件，仅在 scorer 目录内扩展

依赖：`scipy` 已在 `pyproject.toml` 中（`>=1.17.1`），无需新增。

---

### Step 1: 刻板印象模式扫描 (Stereotype Pattern Scan)

**职责**：检测单个画像中是否出现受保护属性与行为/偏好的刻板印象关联。

**输入**：`PersonaProfile`（单个）
**输出**：`list[BiasFinding]`，每条包含 `rule_id`、`category`、`severity`（HIGH/CRITICAL）、`description`

**实现方案**：

**1a. 关键词匹配（保留并扩展）**：
- 现有5条规则保留，从硬编码字典迁移至 `stereotype_patterns.py` 常量
- 新增19条规则，覆盖六大类别（年龄4 + 性别4 + 地域4 + 职业4 + 婚育4 + 教育/社会经济4，去重后与现有规则合并）——具体24个模式清单见 `docs/虚拟消费者公平性规范.md` 附录B
- 每个模式包含字段：
  ```python
  @dataclass
  class StereotypePattern:
      pattern_id: str          # e.g. "AGE-TECH-001"
      category: str            # "age" | "gender" | "region" | "occupation" | "marriage" | "education"
      severity: str            # "HIGH" | "CRITICAL"
      keywords: list[str]      # 中文关键词列表
      description_template: str  # 格式化描述模板
      protected_attr: str      # e.g. "age", "gender"
      associated_behavior: str  # e.g. "technology_acceptance"
  ```
- 匹配逻辑：遍历所有模式，将 `keywords` 与画像全字段文本（Layer1-4 + language_samples）做子串匹配
- 命中任意关键词即生成 `BiasFinding`

**1b. Embedding 语义相似度（新增，可降级）**：
- 实现为可选步骤，通过 `BiasAuditSettings.enable_embedding_scan: bool = False` 控制
- 启用时：调用 `AnthropicSettings` 中配置的 `model_audit`（`claude-haiku-4-5`）或 OpenAI embedding API
- 将每个模式的关键词渲染为"模式描述句"，计算与画像各层文本的 cosine similarity
- 阈值：≥0.7 生成 Finding（severity=HIGH）；≥0.85 生成 Finding（severity=CRITICAL）
- 降级策略：若 embedding API 不可用，自动回退至纯关键词模式，日志 WARNING

**代码位置**：
- 方法名：`_check_stereotype_patterns(self, persona: PersonaProfile) -> list[BiasFinding]`
- 替代现有 `_check_gender_stereotypes`、`_check_region_income_stereotypes`、`_check_occupation_income_anomaly`、`_check_language_bias_terms`——这4个方法内容迁移到 Step 1 的模式库中，作为首批模式加载

---

### Step 2: 统计分布检验 (Statistical Distribution Test)

**职责**：检验批次画像的人口统计分布是否与真实人口基准存在显著偏差。

**输入**：`list[PersonaProfile]`（全批次）、`PopulationBaseline`（可选，默认使用内置中国人口基准）
**输出**：`BatchStatisticalReport` 数据类，含各维度的检验结果

**实现方案**：

**2a. KS 检验（连续/有序变量）**：
- 适用维度：年龄（数值化映射）、收入（有序档位映射）
- 方法：`scipy.stats.ks_2samp(persona_values, baseline_values)`
- 阈值：`D_statistic < 0.15` 且 `p >= BIAS_KS_P_THRESHOLD`（0.05）→ PASS
- 年龄映射表：`{"18-24岁": 21, "25-34岁": 29, "35-44岁": 39, "45-54岁": 49, "55岁以上": 60}`
- 收入映射表：`{"3万元以下": 1, "3-8万元": 2, "8-15万元": 3, "15-30万元": 4, "30-50万元": 5, "50-100万元": 6, "100万元以上": 7}`
- 生成 Finding：D > 0.15 → severity=HIGH；p < 0.05 但 D < 0.15 → severity=MEDIUM

**2b. 卡方独立性检验 / Fisher 精确检验（分类变量）**：
- 适用维度：性别（男/女）、城市层级（一二三四线及以下）、职业大类、民族
- 方法：`scipy.stats.chi2_contingency(contingency_table)`
- 小样本修正：期望频数 < 5 的单元格占比 > 20% 时，改用 `scipy.stats.fisher_exact`（2x2表）或扩展 Fisher（RxC表，通过模拟实现）
- 阈值：`p >= 0.05` → PASS
- 基准数据：`PopulationBaseline` 类，初始用硬编码第七次人口普查常数（见规范附录A），后续可从 YAML/JSON 文件加载
- 生成 Finding：p < 0.01 → CRITICAL；0.01 ≤ p < 0.05 → HIGH

**代码位置**：
- 新私有方法：`_run_statistical_tests(self, personas: list[PersonaProfile]) -> list[BiasFinding]`
- 辅助类：`PopulationBaseline` 数据类（含 `to_distribution(dimension: str)` 方法）
- 基准常量文件：`src/aicbc/core/scoring/population_baseline.py`（约100行，硬编码七普数据）

---

### Step 3: 偏好-属性关联分析 (Preference-Attribute Association Analysis)

**职责**：检测受保护属性与消费偏好之间是否存在系统性关联（Cramér's V 效应量）。

**输入**：`list[PersonaProfile]`（全批次）
**输出**：`list[BiasFinding]` + `AssociationMatrix` 数据类

**实现方案**：
- 对每对 (受保护属性, 偏好字段) 构建列联表
- 受保护属性：gender, city_tier, age_group, occupation_category, education, marital_status
- 偏好字段（从 PersonaProfile 提取并离散化）：
  - `price_sensitivity`（原始即类别）
  - `decision_style`（原始即类别）
  - `brand_loyalty`（原始即类别）
  - `purchase_channels`（多值，取主要渠道）
  - `core_values`（多值，取前2个）
- 对每个列联表计算：`scipy.stats.chi2_contingency` → Cramér's V = `sqrt(chi2 / (n * min(r-1, c-1)))`
- 阈值：Cramér's V ≥ 0.2 → HIGH（触发 reject_and_regenerate）；Cramér's V < 0.2 但 ≥ 0.1 → MEDIUM（警告）
- 注意：规范 v1.1 明确"效应量优先"，Cramér's V ≥ 0.2 即触发处置，无论 p 值

**代码位置**：
- 新私有方法：`_association_analysis(self, personas: list[PersonaProfile]) -> tuple[list[BiasFinding], AssociationMatrix]`
- 辅助函数：`_build_contingency_table(attr_values, pref_values) -> np.ndarray`
- 辅助函数：`_cramers_v(contingency_table) -> float`

---

### Step 4: 叙事简化度检测 (Narrative Simplification Detection)

**职责**：检测画像叙事是否过度简化——即人物"小传"文本与标签描述之间存在非自然的强对应。

**输入**：`PersonaProfile`（单个）
**输出**：`list[BiasFinding]`

**实现方案**：
- 从画像提取两类文本：
  - "叙事文本"：`layer4_scenarios.daily_routine` + `purchase_trigger` + `stress_response` + `social_behavior` + `language_samples` 拼接
  - "标签文本"：所有结构化字段值拼接（`age, gender, income, occupation, price_sensitivity, decision_style, core_values, secret_motivation` 等）
- 分词：使用 jieba（需添加依赖 `jieba>=0.42.1`）或简单字符级 bigram（零依赖方案）
- 计算互信息：将叙事文本和标签文本分别构建词/字频分布，计算 `MI(X, Y) = sum(P(x,y) * log(P(x,y) / (P(x) * P(y))))`
- 归一化：除以 `min(H(X), H(Y))` 得到归一化互信息 NMI
- 阈值：NMI > 0.3（自然语言字段）或 > 0.5（结构化标签字段）→ MEDIUM（叙事过于简化，缺乏真实人物的丰富性与偶然性）

**降级方案**（若互信息实现复杂度过高）：
- 简易版：检测叙事文本与标签描述之间的字面重叠率（Jaccard similarity of character bigrams）
- 若重叠率 > 0.6 → MEDIUM
- 标记为 `method="jaccard_fallback"`，待后续升级为完整 NMI

**代码位置**：
- 新私有方法：`_check_narrative_simplification(self, persona: PersonaProfile) -> list[BiasFinding]`
- 辅助函数：`_mutual_information(text1_tokens, text2_tokens) -> float`
- 辅助函数：`_tokenize_chinese(text) -> list[str]`

---

### 补充：多样性指数 (Diversity Index — Shannon Entropy)

**职责**：检验批次画像在关键维度上的多样性是否达标。

**输入**：`list[PersonaProfile]`（全批次）
**输出**：`list[BiasFinding]` + `DiversityReport` 数据类

**实现方案**：
- 对每个维度计算频数分布 → Shannon 熵 `H = -sum(p_i * log2(p_i))` → 归一化熵 `H_norm = H / log2(n_categories)`
- 维度和最小阈值（来自规范规则6）：
  - 年龄：≥4个年龄段, H_norm ≥ 0.7
  - 性别：比例40%-60%
  - 收入：≥3个层级, H_norm ≥ 0.6
  - 城市：≥3个城市层级
  - 职业：≥5个类别, H_norm ≥ 0.5
  - 价值观：≥3种核心
- 任一维度不达标 → 生成 Finding（severity=HIGH），指明不足维度
- 所有维度达标 → 通过

**代码位置**：
- 新私有方法：`_check_diversity(self, personas: list[PersonaProfile]) -> list[BiasFinding]`（替代现有 `_check_demographic_diversity`）

---

### audit_batch() 集成

修改 `audit_batch()` 方法，将4步串入：

```python
def audit_batch(self, personas: list[PersonaProfile]) -> dict[str, Any]:
    all_findings: list[BiasFinding] = []

    # Step 1: Per-persona stereotype scan
    for p in personas:
        all_findings.extend(self._check_stereotype_patterns(p))

    # Step 2: Batch statistical tests
    all_findings.extend(self._run_statistical_tests(personas))

    # Step 3: Association analysis
    assoc_findings, assoc_matrix = self._association_analysis(personas)
    all_findings.extend(assoc_findings)

    # Step 4: Per-persona narrative simplification
    for p in personas:
        all_findings.extend(self._check_narrative_simplification(p))

    # Diversity
    all_findings.extend(self._check_diversity(personas))

    # ... existing aggregation logic ...
```

审计报告结构（新增 `BiasAuditReport` 数据类）：
```python
@dataclass
class BiasAuditReport:
    batch_id: str
    timestamp: datetime
    total_audited: int
    passed: int
    failed: int
    pass_rate: float
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL
    total_findings: int
    findings_by_step: dict[str, int]  # step名 → 发现数
    findings_by_category: dict[str, int]
    high_severity_count: int
    critical_severity_count: int
    statistical_report: BatchStatisticalReport | None
    association_matrix: AssociationMatrix | None
    diversity_report: DiversityReport | None
    disposition: str  # PASS | FLAGGED | CORRECT_AND_PASS | HALT
    auditor: str  # "小伦"
```

---

## P0-002: reject_and_regenerate

### 触发条件

单个画像触发 `reject_and_regenerate` 的条件（任一条满足即触发）：

| 条件 | 来源 | 严重度 |
|------|------|--------|
| 任一 `BiasFinding.severity == "CRITICAL"` | Step 1 关键词命中 CRITICAL 模式 | 立即拒绝 |
| 任一 `BiasFinding.severity == "HIGH"` 且同一个画像≥2条 | Step 1 | 拒绝 |
| 叙事简化度 NMI > 0.5 | Step 4 | 拒绝（标记性，可降级为修正后重审） |
| `bias_audit_status == "FAILED"` | audit() 聚合判定 | 拒绝 |

批次级暂停条件（`reject_and_regenerate` 升级为整批次暂停）：

| 条件 | 动作 |
|------|------|
| 同一批次累计 ≥3 个画像被拒 | 暂停整批次，通知小示审查 Prompt |
| 单画像连续重试 3 次仍 FAILED | 跳过该画像（记录为 SKIPPED），继续批次 |
| Cramér's V ≥ 0.2（Step 3 批次级） | 暂停，标记关联维度 |
| p < 0.01（Step 2 批次级） | 暂停，审查生成分布 |

---

### ConsumerGeneratorAgent 集成

**集成点1：`__init__` 中实例化并注册 BiasAuditor**

在 `ConsumerGeneratorAgent.__init__` 中：
```python
from aicbc.core.scoring.bias_auditor import BiasAuditor

self._bias_auditor = BiasAuditor()

self.register_tool(
    "audit_bias",
    self._bias_auditor.audit,
    ToolSpec(
        name="audit_bias",
        description="审计单个消费者画像是否存在偏见/刻板印象",
        parameters={"persona": "PersonaProfile"},
        permission_tags=["audit"],
    ),
)
```

`_allowed_tool_tags` 需新增 `"audit"`：
```python
super().__init__(
    ...,
    allowed_tool_tags=["generation", "scoring", "audit"],  # 新增 audit
)
```

**集成点2：`_evaluate()` 中调用偏见审计**

在 `_evaluate()` 方法末尾追加：
```python
def _evaluate(self, profile: PersonaProfile) -> dict[str, Any]:
    # ... 现有真实性评估逻辑 ...

    # 新增：偏见审计
    bias_result = self._bias_auditor.audit(profile)
    profile.bias_audit_status = bias_result.status

    bias_info = {
        "bias_status": bias_result.status,
        "bias_findings": [
            {"rule_id": f.rule_id, "category": f.category,
             "severity": f.severity, "description": f.description}
            for f in bias_result.findings
        ],
        "bias_high_count": bias_result.high_severity_count,
    }
    evaluation.update(bias_info)
    return evaluation
```

**集成点3：`_should_correct()` 中增加偏见触发条件**

在 `_should_correct()` 方法中追加：
```python
def _should_correct(self, evaluation: dict[str, Any]) -> tuple[bool, str]:
    # ... 现有真实性检查 ...

    # 新增：偏见触发重生成
    bias_status = evaluation.get("bias_status", "PENDING")
    if bias_status == "FAILED":
        bias_findings = evaluation.get("bias_findings", [])
        # 检查是否有 CRITICAL
        critical_findings = [f for f in bias_findings if f["severity"] == "CRITICAL"]
        if critical_findings:
            return True, f"偏见审计CRITICAL: {critical_findings[0]['description']}"

        high_findings = [f for f in bias_findings if f["severity"] == "high"]
        if len(high_findings) >= 2:
            return True, f"偏见审计发现{len(high_findings)}项HIGH级问题"

        # 单条HIGH也触发修正（严格模式）
        if len(high_findings) >= 1:
            return True, f"偏见审计发现HIGH级问题: {high_findings[0]['description']}"

    return False, ""
```

**集成点4：`_build_correction_feedback()` 中注入偏见反例**

在现有 `_build_correction_feedback()` 的 feedback 文本中追加偏见发现信息：
```python
def _build_correction_feedback(self, reason, evaluation):
    parts = [f"上次生成存在问题：{reason}"]
    if "bias_findings" in evaluation:
        findings_desc = "; ".join(
            f["description"] for f in evaluation["bias_findings"]
            if f["severity"] in ("high", "CRITICAL")
        )
        if findings_desc:
            parts.append(f"偏见问题：{findings_desc}")
            parts.append("请避免以上刻板印象关联，确保消费者特征基于个人经历而非群体标签。")
    # ... 其余逻辑 ...
```

**集成点5：`generate_batch()` 中批次级审计**

在 `generate_batch()` 方法末尾（所有画像生成完成后）追加批次级审计：
```python
def generate_batch(self, study_id, count, ...) -> ...:
    # ... 现有生成循环 ...

    # 新增：批次级审计
    batch_bias_result = self._bias_auditor.audit_batch(profiles)
    summary["bias_audit"] = {
        "passed": batch_bias_result["passed"],
        "failed": batch_bias_result["failed"],
        "pass_rate": batch_bias_result["pass_rate"],
        "total_findings": batch_bias_result["total_findings"],
        "high_severity": batch_bias_result["high_severity_findings"],
    }

    # 批次暂停条件检查
    if batch_bias_result["failed"] >= 3:
        self._log.warning(
            "batch_bias_threshold_exceeded",
            failed=batch_bias_result["failed"],
            message="整批次偏见失败数≥3，建议暂停并审查Prompt模板"
        )
        summary["bias_audit"]["batch_paused"] = True
        summary["bias_audit"]["action"] = "REVIEW_PROMPT"
```

---

### API 路由阻断 (personas.py)

**当前问题**：`store.save(profile)` 在第131行无条件执行，即使 bias 检测 FAILED。

**修改点**：在 `personas.py` 的批量生成循环中，将 store.save 移到 bias 检测的条件判断之后：

```python
# 第128-131行修改为：
bias_result = bias_auditor.audit(profile)
profile.bias_audit_status = bias_result.status

# P0-002: FAILED 画像不入库
if bias_result.status == "FAILED":
    log.warning(
        "persona_rejected_bias",
        persona_id=persona_id,
        finding_count=len(bias_result.findings),
        high_count=bias_result.high_severity_count,
    )
    errors.append(GenerationErrorDetail(
        index=i,
        error=f"偏见审计未通过(状态: {bias_result.status})。"
              f"发现{len(bias_result.findings)}项偏见，"
              f"其中{', '.join(f.category for f in bias_result.findings)}。"
              f"请通过 ConsumerGeneratorAgent 重新生成（Agent 内置自修正）。",
    ))
    continue  # 跳过入库，进入下一次循环

store.save(profile)
personas.append(PersonaSummary.from_profile(profile))
```

**批次级暂停通知**：在批量生成循环结束后（第153行 return 前）追加：
```python
# 批次级偏见审计
failed_bias_count = sum(1 for e in errors if "偏见审计" in (e.error or ""))
if failed_bias_count >= 3:
    log.warning(
        "batch_bias_critical",
        failed_count=failed_bias_count,
        total_requested=request.count,
        message="批次偏见失败数≥3，强烈建议暂停该研究，审查Prompt模板后重新生成",
    )
    # 在响应中附加警告标志
    response.bias_warning = (
        f"批次偏见失败率 {failed_bias_count}/{request.count} 超过阈值，"
        f"建议暂停研究 {request.study_id} 并审查 Prompt 模板"
    )
```

需要在 `BatchGenerateResponse` schema 中新增可选字段 `bias_warning: str | None = None`。

---

### 完整流程图

```
ProfileGenerator.generate()
        │
        ▼
ConsumerGeneratorAgent.execute()
        │
        ▼
_evaluate() → AuthenticityScorer.score() + BiasAuditor.audit()
        │
        ├── authenticity_score >= 9 AND bias_status == "PASSED"
        │       └── 通过，返回 profile
        │
        ├── authenticity_score < 9 OR bias_status == "FAILED"
        │       └── _should_correct() → True
        │               │
        │               ▼
        │       correction_count < max_corrections(3)?
        │           ├── Yes → 重新 execute(feedback=偏见反馈)
        │           └── No  → 标记 SKIPPED，返回当前 profile（status=FAILED）
        │
        ▼
API Route (personas.py)
        │
        ├── bias_audit_status == "PASSED" → store.save(profile) ✅
        ├── bias_audit_status == "FAILED" → continue (跳过入库) ❌
        │
        ▼
批次结束 → audit_batch() → 检查暂停条件
```

---

## 工作量估算

| 编号 | 任务 | 子任务 | 估时(人日) |
|------|------|--------|-----------|
| **P0-001** | **4步审计管线** | | **11.5** |
| | Step 1: 刻板印象模式扫描 | 24模式库常量定义 + 关键词匹配 | 1.5 |
| | | Embedding 语义相似度（可选，含降级逻辑） | 2.0 |
| | Step 2: 统计分布检验 | KS检验 + 卡方/Fisher精确检验 | 1.5 |
| | | PopulationBaseline 基准数据类 + 七普常量 | 1.0 |
| | Step 3: 偏好-属性关联分析 | 列联表构建 + Cramér's V 计算 | 1.0 |
| | Step 4: 叙事简化度检测 | jieba分词/字bigram + 互信息/Jaccard | 2.0 |
| | 多样性指数 | Shannon熵 + 维度覆盖检查 | 0.5 |
| | 审计报告数据结构 | BiasAuditReport dataclass | 0.5 |
| | 单元测试 | 每步独立测试（含 edge case） | 2.0 |
| | | | |
| **P0-002** | **reject_and_regenerate** | | **5.5** |
| | Agent 集成 | BiasAuditor 注册为 tool + _evaluate 修改 | 0.5 |
| | | _should_correct 偏见触发 | 0.5 |
| | | _build_correction_feedback 偏见注入 | 0.5 |
| | | generate_batch 批次级审计 | 0.5 |
| | API 阻断 | store.save 条件化 + 批次暂停通知 | 0.5 |
| | Schema 更新 | BatchGenerateResponse 新增 bias_warning 字段 | 0.5 |
| | 集成测试 | Agent + API 端到端测试 | 2.0 |
| | | | |
| | **合计** | | **17.0** |

**备注**：
- P0-003 已由小P通过 `sanitize_text` 修复，不在本方案范围内。
- 以上估时假设开发者已熟悉代码库。若需学习期，各 +20%。
- Step 1 的 Embedding 语义相似度标记为"可降级"，若第一阶段仅实现关键词匹配可节省 2 人日。
- jieba 分词若改用零依赖字级 bigram 可节省 0.5 人日。
- 建议的实现顺序：P0-001 Step1→Step2→多样性→Step3→Step4，P0-002 可与 P0-001 并行推进（不同文件）。

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/aicbc/core/scoring/bias_auditor.py` | 扩展 | 281→~600行，4步管线 |
| `src/aicbc/core/scoring/stereotype_patterns.py` | **新建** | 24模式库常量 |
| `src/aicbc/core/scoring/population_baseline.py` | **新建** | 人口基准数据 |
| `src/aicbc/agents/consumer_generator.py` | 修改 | 集成 BiasAuditor (__init__, _evaluate, _should_correct, _build_correction_feedback, generate_batch) |
| `src/aicbc/api/routes/personas.py` | 修改 | store.save 条件化 + 批次暂停通知 |
| `src/aicbc/api/schemas.py` | 修改 | BatchGenerateResponse 新增 bias_warning |
| `src/aicbc/core/models/persona.py` | 不变 | bias_audit_status 字段已存在 |
| `src/aicbc/config/settings.py` | 修改 | BiasAuditSettings 新增 enable_embedding_scan 等字段 |
| `tests/test_bias_audit_batch.py` | 扩展 | 新增4步管线测试 |
| `tests/test_cost_fuse_integration.py` | 不变 | — |
| `pyproject.toml` | 可选修改 | 如需 jieba 依赖 |

---

*审查人：小伦 | 日期：2026-06-11*
