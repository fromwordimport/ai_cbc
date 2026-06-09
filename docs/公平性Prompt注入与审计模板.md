# 公平性Prompt注入与审计模板

> **版本**：v1.1  
> **定位**：将公平性规范转化为可直接嵌入Prompt的规则模板和可执行的审计清单  
> **负责人**：小伦（AI伦理、偏见审计与合规负责人）  
> **协同人**：小示（Prompt规则）、小数（统计阈值）  
> **执行原则**：公平性硬规则必须嵌入每一层Prompt，审计每批次必做

---

## 一、Prompt注入规则集

### 1.1 系统指令层注入

在Agent系统指令（System Instruction）中必须附加：

```markdown
## 公平性与偏见防护指令（系统级）

你正在生成真实消费者的画像/模拟真实消费者的行为。

【绝对禁止】
1. 不得让性别、民族、地域、年龄、职业成为任何偏好或行为的"默认解释"
2. 不得使用刻板印象叙事（如"退休老人节俭""Z世代冲动""女性只看颜值"）
3. 不得将受保护属性与负面特质系统性关联

【必须做到】
1. 每个偏好或行为必须有基于个人经历、价值观或情境的个体化解释
2. 鼓励打破刻板印象的组合（如"退休老人+科技极客""男性+注重设计感"）
3. 多样性：确保不同背景的消费者都有真实、非标签化的内在世界

【自检要求】
生成/模拟完成后，请检查：
- [ ] 是否有任何偏好直接由性别/民族/地域/年龄/职业推导而来？
- [ ] 如果去除群体标签，这个人物/行为是否仍然成立？
- [ ] 这个人物的矛盾和张力是否来自个体经历，而非群体标签？

如果以上任何一项答案为"是"，请重新生成该部分。
```

### 1.2 任务指令层注入

在消费者生成任务中附加：

```markdown
## 公平性约束（任务级）

在生成此消费者时，必须遵守以下具体规则：

### 规则1：性别-偏好解耦
- 不得以性别解释任何产品偏好
- 错误示例："作为女性，她更看重外观"
- 正确示例："她从事设计工作，对视觉美感有职业敏感度"

### 规则2：民族-行为中性
- 不得以民族背景解释消费习惯
- 错误示例："作为汉族，她偏好传统品牌"
- 正确示例："她成长于品牌意识较强的家庭环境"

### 规则3：地域-品牌解耦
- 不得以地域解释品牌偏好
- 错误示例："作为三线城市的消费者，她只用国产品牌"
- 正确示例："她所在城市的售后网络以国产品牌为主"

### 规则4：年龄-技术中性
- 不得以年龄解释技术接受度
- 错误示例："65岁的她不会用智能手机"
- 正确示例："她对新技术持谨慎态度，源于一次不愉快的网购经历"

### 规则5：职业-消费档次解耦
- 不得以职业解释消费档次
- 错误示例："作为蓝领工人，她只看价格"
- 正确示例："她目前经济压力较大，因此优先比较价格"

### 规则6：多样性保障
- 批次内必须在年龄、性别、收入、城市、职业、价值观等维度保持多样性
- 禁止生成"模板化"人物（所有标签方向一致）
```

### 1.3 动态示例注入

在Few-Shot示例中，必须包含打破刻板印象的示例：

```markdown
## 公平性示例（Few-Shot）

【正面示例：打破刻板印象】

示例1：
- 35岁女，企业中层，年薪30万
- 表面：精致品质生活，买高端护肤品
- 张力：她其实是极简主义者，护肤品只有3样，但每样都是研究后的最优选择
- 解释：研究生时期经济拮据养成的"少而精"习惯延续至今

示例2：
- 68岁男，退休教师
- 表面：保守传统
- 张力：科技极客，家里全套智能家居，比儿子还先用上AI助手
- 解释：退休后时间充裕，对新技术有强烈好奇心

示例3：
- 24岁男，工厂工人
- 表面：只看价格
- 张力：对咖啡有极致追求，工资一半花在精品咖啡豆上
- 解释：上夜班需要咖啡提神，逐渐发展为对风味的追求

【反面示例：刻板印象（禁止生成）】

❌ 退休+节俭+被保健品骗+不会用手机
❌ Z世代+冲动消费+月光+沉迷短视频
❌ 宝妈+育儿焦虑+成分党+容易被种草
❌ 小镇青年+土味+向往都市+只用拼多多
```

### 1.4 刻板印象模式库（v1.1 扩展至20个）

以下模式库用于关键词匹配和 Embedding 语义相似度扫描，命中任一模式即触发标记：

| 模式ID | 偏见类型 | 模式描述/关键词 | 严重级别 |
|--------|---------|----------------|---------|
| S001 | 年龄-技术 | "老人不会用手机""年纪大了学不会""年轻人更懂科技" | HIGH |
| S002 | 年龄-消费 | "退休节俭""老年人舍不得花钱""年轻人月光" | HIGH |
| S003 | 性别-外观 | "女性更看重外观""男性只看参数""女生不懂技术" | CRITICAL |
| S004 | 性别-决策 | "女性冲动消费""男性理性决策""女人买东西靠感觉" | CRITICAL |
| S005 | 性别-家庭 | "宝妈容易被种草""女性天生顾家""男人不管家务" | CRITICAL |
| S006 | 地域-品牌 | "北方人用海尔""南方人买美的""小镇青年只用拼多多" | HIGH |
| S007 | 地域-品味 | "一线城市才有品味""三四线城市土味""南方人精致北方人糙" | HIGH |
| S008 | 地域-消费力 | "一线城市有钱""县城消费能力低""农村人买不起" | HIGH |
| S009 | 职业-档次 | "蓝领只看价格""白领追求品质""公务员保守" | HIGH |
| S010 | 职业-品味 | "工人不懂设计""程序员只讲参数""艺术家不切实际" | MEDIUM |
| S011 | 民族-消费 | "某民族更节俭""某民族爱面子""汉族传统保守" | CRITICAL |
| S012 | 民族-品牌 | "少数民族偏好某类品牌""汉族更信任国产品牌" | CRITICAL |
| S013 | 婚姻-动机 | "已婚女性只为家庭买""单身只顾自己""结婚后才务实" | HIGH |
| S014 | 婚育-焦虑 | "宝妈一定有育儿焦虑""有娃家庭只关心安全""丁克自私" | HIGH |
| S015 | 收入-品味 | "低收入没品味""高收入追求奢侈""穷人只配用便宜货" | HIGH |
| S016 | 教育-能力 | "学历低不懂科技""高学历才理性""大学生容易被忽悠" | MEDIUM |
| S017 | 身体-消费 | "残障人士不需要美观""胖子不运动""病人只关心功能" | CRITICAL |
| S018 | 南北对立 | "南方人心细""北方人豪爽""南方潮湿所以...""北方干燥所以..." | MEDIUM |
| S019 | 婚育压力 | "大龄未婚焦虑""被催婚所以消费""结婚必须有房有车" | MEDIUM |
| S020 | 职业标签 | "公务员稳定保守""互联网人焦虑""金融从业者虚荣" | MEDIUM |

**扫描规则**：
- 关键词匹配：命中任一关键词即产生标记
- Embedding 相似度：与上述模式描述余弦相似度 > 0.7 即产生标记
- CRITICAL 级别命中 ≥1 个：批次暂停，小伦行使一票否决权
- HIGH 级别命中 ≥3 个：批次标记为 HIGH，问题画像需修正或重新生成

---

## 二、消费者生成自检Prompt

```markdown
## 公平性自检任务

你刚生成了以下消费者画像。请进行公平性专项自检：

{generated_persona}

### 检查清单

#### 检查1：刻板印象扫描
- [ ] 画像中是否包含刻板印象关键词？（如"节俭的老人""冲动的年轻人"）
- [ ] 人物小传是否过度依赖群体标签而非个体经历？

#### 检查2：受保护属性关联
- [ ] 性别是否解释了任何偏好？
- [ ] 年龄是否解释了技术能力？
- [ ] 地域是否解释了品牌偏好？
- [ ] 职业是否解释了消费档次？
- [ ] 民族是否解释了任何行为？

#### 检查3：叙事质量
- [ ] 人物是否有至少一组矛盾张力？
- [ ] 张力是否有基于个人经历的解释（≥30字）？
- [ ] 如果去除所有群体标签，人物是否仍然立体？

#### 检查4：多样性贡献
- [ ] 此画像是否增加了批次的多样性？
- [ ] 是否与已有画像有足够差异？

### 输出格式
```json
{
  "fairness_score": "number (0-10)",
  "stereotype_flags": [
    {
      "type": "string",
      "location": "string (字段路径)",
      "severity": "LOW|MEDIUM|HIGH|CRITICAL",
      "suggestion": "string"
    }
  ],
  "passed": "boolean",
  "improvement_needed": "boolean",
  "corrected_version": "object (如需要修正)"
}
```
```

---

## 三、批次偏见审计检查清单

### 3.1 自动化审计清单

```yaml
batch_bias_audit_checklist:
  # 检查1：刻板印象模式扫描
  check_001_stereotype_scan:
    method: "关键词匹配 + Embedding语义相似度"
    tools: ["keyword_matcher", "embedding_similarity"]
    threshold: 0.7
    pass_criteria: "无CRITICAL级别命中"
    auto_execute: true
    
  # 检查2：统计分布检验
  check_002_distribution_test:
    method: "KS检验（连续变量）+ 卡方检验（分类变量）；小样本用Fisher精确检验"
    benchmark: "真实人口分布数据（见《虚拟消费者公平性规范》附录A）"
    pass_criteria: "p值 ≥ 0.05；连续变量D统计量 < 0.15"
    auto_execute: true
    
    sub_checks:
      - dimension: "年龄"
        test: "KS检验"
        threshold_p: 0.05
        threshold_d: 0.15
      - dimension: "性别"
        test: "卡方检验（性别分布 vs 人口基准）"
        threshold: 0.05
        fallback: "Fisher精确检验（期望频数<5的单元格>20%时）"
      - dimension: "收入"
        test: "KS检验"
        threshold_p: 0.05
        threshold_d: 0.15
      - dimension: "地域"
        test: "卡方检验（城市层级分布 vs 人口基准）"
        threshold: 0.05
        fallback: "Fisher精确检验（期望频数<5的单元格>20%时）"
      - dimension: "职业"
        test: "卡方检验（职业分布 vs 人口基准）"
        threshold: 0.05
        fallback: "Fisher精确检验（期望频数<5的单元格>20%时）"
      - dimension: "民族"
        test: "卡方检验（民族分布 vs 人口基准）"
        threshold: 0.05
        fallback: "Fisher精确检验（期望频数<5的单元格>20%时）"
      
  # 检查3：偏好-属性关联分析
  check_003_preference_association:
    method: "Cramér's V关联强度（v1.1阈值从0.3收紧至0.2）"
    pass_criteria: "Cramér's V < 0.2（弱关联或无关联）；Cramér's V ≥ 0.2 触发 reject_and_regenerate"
    auto_execute: true
    
    sub_checks:
      - association: "性别 vs 价格敏感度"
        max_cramers_v: 0.2
      - association: "性别 vs 品牌偏好"
        max_cramers_v: 0.2
      - association: "性别 vs 功能偏好"
        max_cramers_v: 0.2
      - association: "年龄 vs 功能偏好"
        max_cramers_v: 0.2
      - association: "年龄 vs 技术接受度"
        max_cramers_v: 0.2
      - association: "地域 vs 品牌偏好"
        max_cramers_v: 0.2
      - association: "地域 vs 渠道偏好"
        max_cramers_v: 0.2
      - association: "职业 vs 消费档次"
        max_cramers_v: 0.2
      - association: "职业 vs 品牌偏好"
        max_cramers_v: 0.2
      - association: "民族 vs 品牌偏好"
        max_cramers_v: 0.2
      - association: "婚姻状况 vs 消费动机"
        max_cramers_v: 0.2
      
  # 检查4：叙事简化度检测
  check_004_narrative_quality:
    method: "互信息计算 + LLM语义评估"
    pass_criteria: "互信息 < 阈值 AND LLM评分 ≥ 6/10"
    auto_execute: true
    
  # 检查5：多样性指数
  check_005_diversity_index:
    method: "Shannon熵"
    pass_criteria: "各维度熵值 ≥ 最小阈值"
    auto_execute: true
    
    sub_checks:
      - dimension: "年龄"
        min_entropy: 0.7
      - dimension: "性别"
        min_entropy: 0.9
      - dimension: "收入"
        min_entropy: 0.6
      - dimension: "城市"
        min_entropy: 0.6
      - dimension: "职业"
        min_entropy: 0.5
      - dimension: "价值观"
        min_entropy: 0.6
```

### 3.2 审计执行脚本

```python
class BiasAuditPipeline:
    """偏见审计管线 - 每批次消费者生成后自动执行"""
    
    def run_audit(self, batch: list[Persona], benchmark: pd.DataFrame) -> AuditReport:
        """
        执行完整的偏见审计
        
        Parameters:
            batch: 本次生成的消费者批次
            benchmark: 真实人口基准数据
        
        Returns:
            AuditReport: 审计报告
        """
        results = {}
        
        # 检查1：刻板印象扫描
        results["stereotype_scan"] = self._scan_stereotypes(batch)
        
        # 检查2：统计分布检验
        results["distribution_test"] = self._test_distribution(batch, benchmark)
        
        # 检查3：偏好-属性关联
        results["association_test"] = self._test_associations(batch)
        
        # 检查4：叙事质量
        results["narrative_quality"] = self._assess_narrative_quality(batch)
        
        # 检查5：多样性指数
        results["diversity_index"] = self._compute_diversity(batch)
        
        # 综合判定
        overall_passed = all(r["passed"] for r in results.values())
        
        # 确定风险等级
        if any(r.get("severity") == "CRITICAL" for r in results.values()):
            risk_level = "CRITICAL"
        elif any(r.get("severity") == "HIGH" for r in results.values()):
            risk_level = "HIGH"
        elif any(r.get("severity") == "MEDIUM" for r in results.values()):
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        return AuditReport(
            batch_id=batch.id,
            timestamp=datetime.utcnow(),
            results=results,
            overall_passed=overall_passed,
            risk_level=risk_level,
            requires_action=risk_level in ["HIGH", "CRITICAL"]
        )
    
    def _scan_stereotypes(self, batch: list[Persona]) -> dict:
        """扫描刻板印象"""
        flags = []
        
        for persona in batch:
            # 关键词匹配
            text = persona.to_text()
            for pattern in STEREOTYPE_PATTERNS:
                if pattern.matches(text):
                    flags.append({
                        "persona_id": persona.id,
                        "pattern": pattern.name,
                        "severity": pattern.severity,
                        "matched_text": pattern.get_match(text)
                    })
            
            # 语义相似度
            embedding = self.embedder.encode(text)
            for pattern in STEREOTYPE_PATTERNS:
                similarity = cosine_similarity(embedding, pattern.embedding)
                if similarity > pattern.threshold:
                    flags.append({
                        "persona_id": persona.id,
                        "pattern": pattern.name,
                        "severity": pattern.severity,
                        "similarity": similarity
                    })
        
        critical_count = sum(1 for f in flags if f["severity"] == "CRITICAL")
        
        return {
            "checked": len(batch),
            "flags": flags,
            "flag_rate": len(flags) / len(batch),
            "critical_rate": critical_count / len(batch),
            "passed": critical_count == 0,
            "severity": "CRITICAL" if critical_count > 0 else "LOW"
        }
    
    def _test_associations(self, batch: list[Persona]) -> dict:
        """测试偏好与受保护属性的关联"""
        results = []
        
        # 构建分析数据框
        df = pd.DataFrame([p.to_dict() for p in batch])
        
        # 测试各组关联
        tests = [
            ("gender", "price_sensitivity"),
            ("gender", "brand_preference"),
            ("age_group", "feature_preference"),
            ("city_tier", "channel_preference"),
            ("occupation", "spending_level"),
        ]
        
        for attr_a, attr_b in tests:
            contingency = pd.crosstab(df[attr_a], df[attr_b])
            chi2, p_value, dof, expected = chi2_contingency(contingency)
            
            # Cramér's V
            n = contingency.sum().sum()
            cramers_v = np.sqrt(chi2 / (n * min(contingency.shape) - 1))
            
            results.append({
                "association": f"{attr_a} vs {attr_b}",
                "chi2": chi2,
                "p_value": p_value,
                "cramers_v": cramers_v,
                "passed": p_value >= 0.05 and cramers_v < 0.2
            })
        
        all_passed = all(r["passed"] for r in results)
        
        return {
            "tests": results,
            "passed": all_passed,
            "severity": "HIGH" if not all_passed else "LOW"
        }
```

---

## 四、偏见超标处置决策树

```
偏见审计完成
   │
   ▼
评估总体风险等级
   │
   ├── LOW（全部通过）
   │   → ✅ 批次通过，可进入模拟阶段
   │   → 记录审计日志
   │
   ├── MEDIUM（轻微偏差）
   │   → ⚠️ 批次通过（带警告）
   │   → 标记偏差维度
   │   → 下批次调整采样权重
   │   → 通知小示优化Prompt
   │
   ├── HIGH（显著偏差）
   │   → ❌ 批次暂停
   │   → 问题画像需修正或重新生成
   │   → 小伦审核修正后结果
   │   → 修正通过后方可入库
   │
   └── CRITICAL（严重偏见）
       → 🛑 小伦行使一票否决权
       → 暂停消费者生成流程
       → 全面审查Prompt模板
       → 分析偏见来源
       → 修复后重新生成测试批次
       → 重新审计通过后方可恢复
```

---

## 五、合规声明模板

```markdown
# 合成数据公平性声明

## 批次信息
- 批次ID: {batch_id}
- 生成时间: {timestamp}
- 样本量: {n_personas}
- 生成模型: {llm_model}

## 审计结果
- 审计工具: 自动化偏见审计管线 v1.0
- 审计依据: 《虚拟消费者公平性规范》v1.0

### 关键指标
| 检查项 | 结果 | 状态 |
|--------|------|------|
| 刻板印象扫描 | {n_flags}个标记 | {status} |
| 统计分布检验 | {n_passed}/{n_total}通过 | {status} |
| 偏好关联分析 | Cramér's V最大值={max_v} | {status} |
| 叙事质量 | 平均分={avg_score} | {status} |
| 多样性指数 | 最低熵={min_entropy} | {status} |

### 总体判定
- 风险等级: {LOW/MEDIUM/HIGH/CRITICAL}
- 通过状态: {通过/有条件通过/不通过}
- 审核人: 小伦
- 审核时间: {timestamp}

## 使用声明
本批次虚拟消费者已按《虚拟消费者公平性规范》进行偏见审计。
使用者应注意：
1. 合成数据仅供参考，关键决策应与真实消费者研究交叉验证
2. 如使用过程中发现潜在偏见，请立即通知伦理审计负责人
3. 本批次数据禁止用于任何可能加剧歧视的用途

## 申诉渠道
如对审计结果有异议，请联系：小伦（AI伦理审计负责人）
```

---

## 六、BiasAuditPipeline 与 Harness 集成接口（v1.1 新增）

### 6.1 集成架构

```
Harness Validation Pipeline
    │
    ├── Schema Validator (Layer A)
    ├── Logic Validator (Layer B)
    │
    ▼
┌─────────────────────┐
│   Bias Detector     │  ← Harness 内置模块
│   (Harness Layer C) │
└──────────┬──────────┘
           │
           │ 触发条件：Schema + Logic 校验通过后
           │ 输入：PersonaProfile 列表（JSON）
           │
           ▼
┌─────────────────────────────┐
│   BiasAuditPipeline         │  ← 独立审计管线（小伦负责）
│   - 刻板印象扫描            │
│   - 统计分布检验            │
│   - 偏好-属性关联分析       │
│   - 叙事质量评估            │
│   - 多样性指数计算          │
└──────────┬──────────────────┘
           │
           │ 输出：AuditReport
           ▼
    ┌──────┴──────┐
    ▼             ▼
 通过(LOW)    不通过(HIGH/CRITICAL)
    │             │
    ▼             ▼
 进入         Feedback Loop
 Authenticity  或 reject_and_regenerate
 Scorer
```

### 6.2 输入输出 Schema

**输入：`BiasAuditRequest`**

```json
{
  "batch_id": "batch-20250609-001",
  "study_id": "dishwasher-202506",
  "generated_at": "2026-06-09T14:30:00Z",
  "model": "claude-sonnet-4-6",
  "personas": [
    {
      "persona_id": "persona-001",
      "layer1_demographics": {
        "age": 28,
        "gender": "女",
        "city_tier": "一线",
        "income": "15-25万",
        "occupation": "产品经理",
        "ethnicity": "汉族"
      },
      "layer2_behavior": {
        "price_sensitivity": "中",
        "brand_preference": ["方太", "西门子"],
        "feature_preference": ["全能"],
        "channel_preference": ["京东", "线下体验店"]
      },
      "layer3_psychology": {
        "core_values": ["品质生活", "健康焦虑"],
        "tension_combination": ["高收入", "节俭习惯"],
        "narrative_explanation": "童年家境一般，工作后收入提升但仍保留比价习惯"
      },
      "layer4_scenarios": {
        "persona_text": "完整人物小传文本..."
      }
    }
  ],
  "benchmark_config": {
    "source": "CFPS_2020",
    "target_population": "18-35岁一线城市常住人口",
    "dimensions": ["age", "gender", "city_tier", "income", "occupation", "ethnicity"]
  }
}
```

**输出：`BiasAuditReport`**

```json
{
  "batch_id": "batch-20250609-001",
  "audit_timestamp": "2026-06-09T14:31:00Z",
  "overall_passed": false,
  "risk_level": "HIGH",
  "results": {
    "stereotype_scan": {
      "checked": 150,
      "flags": [
        {
          "persona_id": "persona-003",
          "pattern_id": "GEN-001",
          "pattern_name": "女性颜值导向",
          "severity": "CRITICAL",
          "matched_text": "作为女性，她最看重洗碗机的外观设计",
          "suggestion": "改为基于职业或个人审美的解释"
        }
      ],
      "flag_rate": 0.02,
      "critical_rate": 0.007,
      "passed": false,
      "severity": "CRITICAL"
    },
    "distribution_test": {
      "tests": [
        {"dimension": "age", "method": "KS", "statistic": 0.08, "p_value": 0.12, "passed": true},
        {"dimension": "gender", "method": "chi2", "statistic": 2.1, "p_value": 0.35, "passed": true}
      ],
      "passed": true,
      "severity": "LOW"
    },
    "association_test": {
      "tests": [
        {"association": "gender vs brand_preference", "cramers_v": 0.15, "p_value": 0.08, "passed": true},
        {"association": "age vs feature_preference", "cramers_v": 0.24, "p_value": 0.03, "passed": false}
      ],
      "passed": false,
      "severity": "HIGH"
    },
    "narrative_quality": {
      "avg_score": 7.2,
      "passed": true,
      "severity": "LOW"
    },
    "diversity_index": {
      "dimensions": {
        "age": {"entropy": 0.82, "threshold": 0.7, "passed": true},
        "gender": {"entropy": 0.95, "threshold": 0.9, "passed": true},
        "income": {"entropy": 0.68, "threshold": 0.6, "passed": true}
      },
      "passed": true,
      "severity": "LOW"
    }
  },
  "actions_required": [
    {
      "action": "reject_and_regenerate",
      "target": "persona-003",
      "reason": "CRITICAL级别刻板印象命中：GEN-001 女性颜值导向",
      "owner": "小示"
    },
    {
      "action": "review_prompt",
      "target": "age_vs_feature_preference 关联偏高",
      "reason": "Cramér's V = 0.24，需检查Prompt是否隐含年龄-功能偏好关联",
      "owner": "小示+小伦"
    }
  ]
}
```

### 6.3 触发时机与失败回退策略

**触发时机**：

| 触发点 | 时机 | 调用方 | 说明 |
|--------|------|--------|------|
| 批次生成完成后 | 同步阻塞 | Harness Output Formatter | 每批次全部画像生成完成后立即审计 |
| 新Prompt上线前 | 同步阻塞 | 测试管线 | 测试批次（n=100）必须通过审计 |
| 单画像修正后 | 同步阻塞 | Feedback Loop | 仅对修正画像重新审计 |
| 日/周/月度汇总 | 异步 | 定时任务 | 用于趋势监控，不阻塞生成 |

**失败回退策略**：

```
审计结果
    │
    ├── LOW → 直接进入 Authenticity Scorer
    │
    ├── MEDIUM → 批次通过，记录警告，下批次调整采样权重
    │
    ├── HIGH → 触发 Feedback Loop
    │   ├── 问题画像 ≤ 2 个 → 定向修正（最多重试3次）
    │   ├── 问题画像 3-10 个 → 整批次重采样（保留种子）
    │   └── 问题画像 > 10 个 → 暂停生成，小示审查Prompt
    │
    └── CRITICAL → 小伦一票否决
        ├── 暂停消费者生成流程
        ├── 通知小P、小示、小验
        ├── 48小时内提交根因分析报告
        └── 修复后需通过100人测试批次方可恢复
```

### 6.4 接口规范（供小应实现）

```python
# 服务间接口

class BiasAuditClient:
    """Harness 调用 BiasAuditPipeline 的客户端"""
    
    def audit_batch(self, request: BiasAuditRequest) -> BiasAuditReport:
        """
        同步调用审计管线
        超时：30秒（n=150标准批次）
        失败：返回 AUDIT_FAILED 状态，Harness 应暂停批次通过
        """
        pass
    
    def audit_persona(self, persona: PersonaProfile) -> BiasAuditReport:
        """
        单画像审计（用于 Feedback Loop）
        超时：5秒
        """
        pass

# 事件总线（异步通知）
@dataclass
class BiasAuditCompletedEvent:
    batch_id: str
    risk_level: str
    overall_passed: bool
    critical_flags: List[StereotypeFlag]
    timestamp: datetime
```

### 6.5 职责分工

| 模块 | 负责人 | 说明 |
|------|--------|------|
| BiasAuditPipeline 算法实现 | 小数 + 小伦 | 统计检验、模式扫描、多样性计算 |
| BiasAuditPipeline 服务部署 | 小应 + 小端 | API服务、事件总线、与Harness集成 |
| Prompt公平性规则嵌入 | 小示 | 将规则注入 consumer-simulation/05-Prompt模板库.md |
| 模式库维护 | 小伦 | 每月review，新增模式需小P审批 |
| 基准数据接入 | 小端 | 从公开数据源下载、脱敏、导入审计管线 |

---

*本文档由小伦维护，公平性规则为强制标准，无例外。*
