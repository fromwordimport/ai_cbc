# 洗碗机CBC实验设计方案

> **版本**：v1.0  
> **定位**：定义洗碗机产品的CBC联合分析实验设计，包括属性/水平设定、实验设计算法、与画像系统的联动  
> **负责人**：小联（联合分析领域专家）  
> **配套文档**：《项目成功标准书》、《消费者画像.md》

---

## 一、产品属性与水平设计

### 1.1 属性筛选原则

| 原则 | 说明 | 应用 |
|------|------|------|
| **相关性** | 属性必须是消费者实际关心的决策维度 | 价格、容量、安装方式是核心决策因素 |
| **可感知差异** | 水平之间必须有可感知的差异 | 价格间隔≥¥1000，容量间隔≥4套 |
| **独立性** | 属性间避免高度相关 | 价格与能耗等级弱相关，保留 |
| **可操作性** | 企业可以实际提供这些水平 | 所有水平均为市场已有或可实现 |

### 1.2 属性与水平定义

```yaml
attributes:
  price:
    name: "价格"
    type: "price"
    levels:
      - value: 2999
        label: "¥2,999"
        positioning: "入门级"
      - value: 3999
        label: "¥3,999"
        positioning: "主流价位"
      - value: 4999
        label: "¥4,999"
        positioning: "中高端"
      - value: 5999
        label: "¥5,999"
        positioning: "旗舰级"
    importance_expected: "高（预计TOP1或TOP2）"

  capacity:
    name: "容量"
    type: "categorical"
    levels:
      - value: "6套"
        label: "6套（1-2人）"
        target: "单身/情侣"
      - value: "10套"
        label: "10套（3-4人）"
        target: "小家庭"
      - value: "13套"
        label: "13套（5人以上）"
        target: "大家庭"
    importance_expected: "中-高"

  installation:
    name: "安装方式"
    type: "categorical"
    levels:
      - value: "台式"
        label: "台式（免安装）"
        advantage: "灵活、租房友好"
      - value: "嵌入式"
        label: "嵌入式"
        advantage: "省空间、美观"
      - value: "水槽式"
        label: "水槽式"
        advantage: "替换水槽、不占地"
    importance_expected: "中（细分群体差异大）"

  features:
    name: "核心功能"
    type: "categorical"
    levels:
      - value: "基础"
        label: "标准洗+热风烘干"
        description: "满足基本洗碗需求"
      - value: "智能"
        label: "智能洗+烘干+72℃高温除菌"
        description: "智能识别脏污程度"
      - value: "全能"
        label: "AI智能洗+烘干+UV除菌+智能投放"
        description: "全自动、最省心"
    importance_expected: "中"

  brand:
    name: "品牌"
    type: "categorical"
    levels:
      - value: "美的"
        label: "美的"
        positioning: "国民品牌、性价比"
      - value: "西门子"
        label: "西门子"
        positioning: "德系精工、高端"
      - value: "方太"
        label: "方太"
        positioning: "厨电专家、本土化"
      - value: "小米"
        label: "小米"
        positioning: "智能生态、年轻"
    importance_expected: "中（品牌忠诚度群体差异大）"

  energy:
    name: "能耗等级"
    type: "categorical"
    levels:
      - value: "二级"
        label: "二级能效"
        annual_cost: "约¥180/年"
      - value: "一级"
        label: "一级能效"
        annual_cost: "约¥120/年"
      - value: "超一级"
        label: "超一级能效"
        annual_cost: "约¥80/年"
    importance_expected: "低-中（环保意识群体差异）"
```

### 1.3 禁止组合

```yaml
prohibited_combinations:
  # 逻辑不合理组合
  - rule: "高端品牌+最低价格"
    combination:
      brand: "西门子"
      price: 2999
    reason: "西门子定位高端，2999不符合品牌定位"
    
  - rule: "大容量+台式"
    combination:
      capacity: "13套"
      installation: "台式"
    reason: "台式洗碗机物理空间有限，无法容纳13套"
    
  - rule: "旗舰功能+最低价格"
    combination:
      features: "全能"
      price: 2999
    reason: "成本不支持"
    
  - rule: "超一级能效+最低价格"
    combination:
      energy: "超一级"
      price: 2999
    reason: "技术成本不支持"
```

---

## 二、实验设计

### 2.1 设计参数

```yaml
experimental_design:
  method: "D-efficient设计"  # 推荐方法
  
  parameters:
    n_choice_sets: 12          # 每人12道题
    n_alternatives_per_set: 3   # 每题3个选项
    include_none_option: true   # 包含"都不选"
    n_respondents: 240         # 总样本量（每群体80人，支撑群体级HB）
    
  design_constraints:
    min_d_efficiency: 0.80     # D-efficiency最低要求（prohibition约束下0.85偏乐观）
    level_balance: true        # 各水平出现次数均衡
    positional_balance: true   # 各位置（A/B/C）均衡
    no_repeat_alternatives: true  # 同一选择集中不出现重复配置
    
  prohibitions:
    - "西门子+2999"
    - "13套+台式"
    - "全能+2999"
    - "超一级+2999"
```

### 2.2 样本量计算

```
总参数数 = 价格(1连续) + 容量(2) + 安装(2) + 功能(2) + 品牌(3) + 能耗(2) = 12个参数
（含none option效用参数时为13个，此处按核心属性参数估算）

最小样本量公式：
n_respondents × n_choice_sets ≥ n_params × 5
n × 12 ≥ 12 × 5
n ≥ 60/12 = 5人（理论最小）

实际推荐：
- 基础估计：n ≥ 100
- 细分分析：每群体 n ≥ 80（支撑群体级HB的个体异质性估计）
- 本方案：3群体 × 80人 = 240人
- 总选择观察数：240 × 12 = 2880个选择
```

### 2.3 分组设计

| 群体 | 人数 | 专属情境 | 个性化调整 |
|------|------|---------|-----------|
| **精致白领** | 80人 | 忙碌工作日晚餐后的场景 | 强调省时、品质、空间紧凑 |
| **新手宝妈** | 80人 | 宝宝辅食后清洁场景 | 强调除菌、安全、大容量 |
| **Z世代租客** | 80人 | 合租小厨房场景 | 强调免安装、低价、颜值 |

---

## 三、与画像系统的联动设计

### 3.1 群体-画像映射

```yaml
segment_persona_mapping:
  精致白领:
    seed_constraints:
      age: "25-30"
      city_tier: "一线/新一线"
      income: "15-50万"
      life_stage: "初入职场单身/恋爱/新婚无孩"
      core_values: ["精致品质", "便捷高效"]
    
    preference_biases:
      price_sensitivity: "中低"           # 愿意为品质付费
      capacity_preference: "6-10套"      # 小家庭
      installation_preference: "台式/嵌入式"  # 灵活或美观
      feature_preference: "智能/全能"     # 愿意为智能付费
      brand_preference: "小米/西门子"     # 智能生态或德系品质
      energy_preference: "一级/超一级"    # 环保意识
      
    scenario_context: |
      你刚下班到家，做了顿简单的晚餐。
      外面在下雨，你不想出门。
      厨房不大，但你希望生活品质不打折。
      你正在看洗碗机...

  新手宝妈:
    seed_constraints:
      age: "28-35"
      city_tier: "一线/新一线"
      income: "15-40万"
      life_stage: "已婚有子女(0-6岁)"
      core_anxiety: ["育儿焦虑", "健康焦虑"]
    
    preference_biases:
      price_sensitivity: "中"             # 有预算但追求性价比
      capacity_preference: "10-13套"     # 大容量需求
      installation_preference: "嵌入式"   # 新房装修
      feature_preference: "全能"          # 除菌是刚需
      brand_preference: "方太/西门子"     # 信任专业品牌
      energy_preference: "一级"           # 长期考虑
      
    scenario_context: |
      宝宝的辅食碗、奶瓶、餐具堆了一水槽。
      你担心手洗洗不干净，有细菌残留。
      家里正准备装修厨房，可以预留嵌入式空间。
      婆婆说洗碗机费水费电，但你还是想说服她...

  Z世代租客:
    seed_constraints:
      age: "22-28"
      city_tier: "一线/新一线"
      income: "8-20万"
      life_stage: "独居/合租"
      living_type: "租房"
      core_values: ["实用至上", "颜值即正义"]
    
    preference_biases:
      price_sensitivity: "高"             # 预算敏感
      capacity_preference: "6套"          # 独居够用即可
      installation_preference: "台式"     # 免安装、搬家可带走
      feature_preference: "基础"          # 够用就行
      brand_preference: "小米/美的"       # 性价比或智能生态
      energy_preference: "二级"           # 不太关注
      
    scenario_context: |
      你和室友合租，厨房很小。
      你们经常做饭，但谁都不想洗碗。
      房东不让改造厨房，不能装嵌入式。
      你刷小红书看到台式洗碗机，有点心动...
```

### 3.2 画像驱动的属性发现

```python
# 伪代码：从画像自动调整属性水平

def adapt_attributes_for_segment(segment_config, base_attributes):
    """
    根据细分群体的画像特征，调整CBC属性水平
    """
    adapted = deepcopy(base_attributes)
    
    if segment_config.name == "Z世代租客":
        # 价格敏感度极高 → 增加低价选项
        adapted["price"]["levels"] = [
            {"value": 1999, "label": "¥1,999", "positioning": "超入门"},
            {"value": 2999, "label": "¥2,999", "positioning": "入门"},
            {"value": 3999, "label": "¥3,999", "positioning": "主流"},
        ]
        # 租房场景 → 去掉嵌入式选项
        adapted["installation"]["levels"] = [
            {"value": "台式", "label": "台式（免安装）"},
            {"value": "水槽式", "label": "水槽式"},
        ]
        
    elif segment_config.name == "新手宝妈":
        # 除菌刚需 → 功能水平增加描述
        adapted["features"]["levels"][1]["description"] += "（宝宝餐具专用除菌）"
        adapted["features"]["levels"][2]["description"] += "（UV紫外线+高温双重除菌）"
        
    elif segment_config.name == "精致白领":
        # 空间敏感 → 增加水槽式（不占地）
        adapted["installation"]["levels"].append(
            {"value": "水槽式", "label": "水槽式（替换水槽）", "advantage": "不额外占地"}
        )
    
    return adapted
```

---

## 四、数据收集与预处理规范

### 4.1 数据收集格式

```json
{
  "metadata": {
    "study_id": "dishwasher-202506",
    "product": "洗碗机",
    "n_segments": 3,
    "n_personas_per_segment": 50,
    "n_choice_sets": 12,
    "design_method": "D-efficient"
  },
  
  "choice_records": [
    {
      "respondent_id": "persona-001",
      "segment": "精致白领",
      "choice_set_id": 1,
      "alternatives": [
        {
          "alt_id": "A",
          "chosen": false,
          "attributes": {
            "price": 3999,
            "capacity": "6套",
            "installation": "台式",
            "features": "智能",
            "brand": "小米",
            "energy": "一级"
          }
        },
        {
          "alt_id": "B",
          "chosen": true,
          "attributes": {
            "price": 4999,
            "capacity": "10套",
            "installation": "嵌入式",
            "features": "全能",
            "brand": "方太",
            "energy": "超一级"
          }
        },
        {
          "alt_id": "C",
          "chosen": false,
          "attributes": {
            "price": 2999,
            "capacity": "6套",
            "installation": "台式",
            "features": "基础",
            "brand": "美的",
            "energy": "二级"
          }
        }
      ],
      "none_chosen": false,
      "decision_rationale": "选B因为..."
    }
  ]
}
```

### 4.2 编码方案

```yaml
encoding:
  method: "effects_coding"  # 效应编码，参数和为0
  
  categorical_attributes:
    price:
      type: "price"
      levels: [2999, 3999, 4999, 5999]
      encoding: "continuous"  # 价格作为连续变量
      
    capacity:
      type: "categorical"
      levels: ["6套", "10套", "13套"]
      n_params: 2  # 3水平 → 2个参数
      
    installation:
      type: "categorical"
      levels: ["台式", "嵌入式", "水槽式"]
      n_params: 2
      
    features:
      type: "categorical"
      levels: ["基础", "智能", "全能"]
      n_params: 2
      
    brand:
      type: "categorical"
      levels: ["美的", "西门子", "方太", "小米"]
      n_params: 3  # 4水平 → 3个参数
      
    energy:
      type: "categorical"
      levels: ["二级", "一级", "超一级"]
      n_params: 2
      
  total_parameters: 1 + 2 + 2 + 2 + 3 + 2 = 12
  # 价格(1连续) + 容量(2) + 安装(2) + 功能(2) + 品牌(3) + 能耗(2)
```

---

## 五、预期结果与解读框架

### 5.1 预期发现（假设）

| 发现 | 预期 | 业务含义 |
|------|------|---------|
| 属性重要性排序 | 价格 > 容量 > 品牌 > 功能 > 安装 > 能耗 | 价格是决定性因素 |
| 精致白领 | 品牌重要性较高，愿意为智能功能付费 | 可推中高端智能款 |
| 新手宝妈 | 容量和除菌功能最重要 | 大容量+全能款是核心 |
| Z世代租客 | 价格敏感度极高，偏好台式 | 入门台式款是突破口 |
| WTP(容量) | 6套→10套，WTP≈¥800 | 升级容量有溢价空间 |

### 5.2 输出报告结构

```markdown
# 洗碗机CBC联合分析报告

## 1. 执行摘要
- 样本量：240虚拟消费者（3群体×80人）
- 模型：Hierarchical Bayes
- 关键发现：{top_3_insights}

## 2. 属性重要性分析
[属性重要性条形图]
| 排名 | 属性 | 重要性 | 群体差异 |

## 3. 效用值分析
[各属性水平的效用值]
| 属性 | 水平 | 效用值 | 解读 |

## 4. 群体细分对比
[三个群体的偏好雷达图]
| 群体 | TOP3属性 | 最优配置 | 价格承受力 |

## 5. 支付意愿（WTP）
| 属性升级 | WTP均值 | WTP区间 | 群体差异 |

## 6. 市场份额模拟
[不同配置组合的份额预测]
| 配置 | 预测份额 | 目标群体 |

## 7. 建议
- 产品配置建议
- 定价策略建议
- 目标群体建议
```

---

*本文档由小联维护，实验设计参数可根据预测试结果调整。*
