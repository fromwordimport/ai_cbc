# CBC问卷生成 — 输入信息规范

> **版本**：v1.0  
> **定位**：详细定义CBC问卷生成系统的输入字段、数据类型、校验规则  
> **配套文档**：`01-CBC系统架构与解决方案.md`

---

## 一、输入信息总览

```
┌─────────────────────────────────────────────────────────────┐
│                     输入信息层级                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: 核心骨架（必填 — 缺少则无法生成）                  │
│  → 产品属性列表 + 属性水平 + 研究目的                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: 设计参数（可选 — 不填使用默认值）                  │
│  → 实验设计参数 + 约束条件 + 呈现参数                        │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: 画像联动（可选 — 不填使用通用假设）                │
│  → 目标人群画像 + 情境描述 + 个性化适配                      │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: 高级特性（可选 — 不填关闭该功能）                  │
│  → 自适应设计 + 多版本测试 + 固定基准                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、Layer 1: 核心骨架（必填）

### 2.1 产品属性列表（attributes）

**字段定义**：

| 字段路径 | 类型 | 必填 | 说明 | 示例 |
|---------|------|------|------|------|
| `attributes` | array | **是** | 产品属性列表 | - |
| `attributes[].id` | string | **是** | 属性唯一标识 | `"brand"` |
| `attributes[].name` | string | **是** | 属性显示名称 | `"品牌"` |
| `attributes[].description` | string | 否 | 属性说明 | `"手机制造商品牌"` |
| `attributes[].type` | enum | 否 | 属性类型 | `"categorical"` |

**属性类型枚举值**：

| 类型值 | 说明 | 统计分析影响 |
|--------|------|-------------|
| `categorical` | 分类变量（默认） | 每个水平独立估计效用 |
| `ordinal` | 有序分类变量 | 可假设单调趋势 |
| `continuous` | 连续变量 | 可用线性参数模型 |
| `price` | 价格变量 | 特殊处理，可计算WTP |

**校验规则**：
- `attributes` 数组长度必须在 `[2, 8]` 范围内（推荐 3-6）
- 每个属性的 `id` 必须唯一
- `id` 只能包含字母、数字、下划线、连字符

**错误示例**：
```json
// ❌ 错误：属性数量过多
{"attributes": [/* 10个属性 */]}

// ❌ 错误：id不唯一
{"attributes": [{"id": "price", ...}, {"id": "price", ...}]}

// ✅ 正确
{"attributes": [
  {"id": "brand", "name": "品牌", "type": "categorical"},
  {"id": "price", "name": "价格", "type": "price"}
]}
```

---

### 2.2 属性水平（levels）

**字段定义**：

| 字段路径 | 类型 | 必填 | 说明 | 示例 |
|---------|------|------|------|------|
| `levels` | object | **是** | 每个属性的水平定义 | - |
| `levels.{attribute_id}` | array | **是** | 某属性的所有水平 | `["华为", "小米"]` |
| `levels.{attribute_id}[].value` | any | **是** | 水平值 | `"华为"` / `2999` |
| `levels.{attribute_id}[].label` | string | 否 | 水平显示标签 | `"华为（国产旗舰）"` |

**校验规则**：
- 每个属性必须有至少 `2` 个水平
- 每个属性最多 `6` 个水平（推荐 2-4）
- 水平值在属性内必须唯一
- `levels` 的键必须对应 `attributes` 中的 `id`

**错误示例**：
```json
// ❌ 错误：某属性只有一个水平
{"levels": {"brand": ["华为"]}}

// ❌ 错误：水平值重复
{"levels": {"price": [2999, 2999, 3999]}}

// ❌ 错误：levels键与attributes不匹配
{
  "attributes": [{"id": "brand"}],
  "levels": {"color": ["红", "蓝"]}
}
```

**最佳实践**：
```json
{
  "levels": {
    "brand": [
      {"value": "huawei", "label": "华为"},
      {"value": "xiaomi", "label": "小米"},
      {"value": "apple", "label": "苹果"}
    ],
    "price": [
      {"value": 2999, "label": "¥2,999"},
      {"value": 3999, "label": "¥3,999"},
      {"value": 5999, "label": "¥5,999"}
    ]
  }
}
```

---

### 2.3 研究目的（research_objective）

**字段定义**：

| 字段路径 | 类型 | 必填 | 说明 | 示例 |
|---------|------|------|------|------|
| `research_objective` | string | **是** | 研究目的描述 | `"评估新品市场接受度"` |
| `key_questions` | array | 否 | 具体研究问题 | `["价格敏感度", "品牌偏好"]` |

**校验规则**：
- `research_objective` 长度 ≥ 10 字符
- `key_questions` 每项长度 ≥ 5 字符

**设计影响**：

| 研究目的关键词 | 系统自动调整 |
|--------------|-------------|
| "定价" / "价格敏感度" | 价格属性水平更精细，增加价格水平数量 |
| "品牌" / "竞品" | 品牌属性优先级提升，增加品牌数量 |
| "新品" / "概念" | 增加固定产品选项，用于对比 |
| "细分" / "人群" | 提示需要画像联动，建议分组 |
| "份额" / "市场" | 强制包含"都不选"选项 |

---

## 三、Layer 2: 设计参数（可选）

### 3.1 实验设计参数（design_parameters）

| 字段路径 | 类型 | 必填 | 默认值 | 取值范围 | 说明 |
|---------|------|------|--------|---------|------|
| `design_parameters.choice_sets` | integer | 否 | 自动计算 | [4, 30] | 选择集数量 |
| `design_parameters.alternatives_per_set` | integer | 否 | 3 | [2, 5] | 每集产品选项数 |
| `design_parameters.include_none` | boolean | 否 | true | - | 是否包含"都不选" |
| `design_parameters.none_label` | string | 否 | "以上都不选" | - | "都不选"显示文字 |
| `design_parameters.design_method` | enum | 否 | `"d_optimal"` | 见下表 | 实验设计方法 |

**实验设计方法枚举**：

| 方法 | 适用场景 | 说明 |
|------|---------|------|
| `random` | 快速测试 | 完全随机生成，效率最低 |
| `orthogonal` | 属性独立性强 | 传统正交设计 |
| `d_optimal` | 通用推荐 | D最优设计，统计效率最高（默认） |
| `adaptive` | 大样本在线研究 | 自适应 Bayesian 设计 |
| `balanced_overlap` | 小样本研究 | 平衡重叠设计，属性水平分布均匀 |

**选择集数量自动计算规则**：

```
总参数数 = Σ(各属性水平数 - 1) + 1  // +1 为截距项
最小选择集数 = ceil(总参数数 × 5 / 预期样本量)
默认选择集数 = max(最小选择集数, 8, 属性数量 × 2)
上限约束 = min(默认选择集数, 20)  // 移动端限制
```

**示例**：
- 4个属性，各3个水平 → 总参数 = (3-1)×4 + 1 = 9
- 预期样本量 100 → 最小选择集 = ceil(9 × 5 / 100) = 1 → 取默认下限 8

---

### 3.2 约束条件（constraints）

#### 3.2.1 禁止组合（prohibited_combinations）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `constraints.prohibited_combinations` | array | 否 | `[]` | 禁止的属性水平组合 |

**格式**：
```json
{
  "constraints": {
    "prohibited_combinations": [
      {
        "description": "苹果不可能2999",
        "conditions": {
          "brand": ["apple"],
          "price": [2999]
        }
      },
      {
        "description": "低配版不能有顶配快充",
        "conditions": {
          "price": [2999],
          "charging": [120]
        }
      }
    ]
  }
}
```

**校验规则**：
- 每个禁止组合必须包含至少 2 个属性的条件
- 条件中的值必须是对应属性的有效水平

#### 3.2.2 必须包含组合（required_combinations）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `constraints.required_combinations` | array | 否 | `[]` | 必须出现的配置 |

**格式**：
```json
{
  "constraints": {
    "required_combinations": [
      {
        "description": "新品配置必须测试",
        "profile": {
          "brand": "huawei",
          "price": 4999,
          "storage": "512gb",
          "battery": 5500,
          "charging": 120
        },
        "min_appearances": 3,
        "max_appearances": 5
      }
    ]
  }
}
```

**校验规则**：
- `profile` 中的属性值必须有效
- `min_appearances` ≤ `max_appearances`
- `min_appearances` × 必须包含组合数 ≤ 总选择集数 × 每集选项数

---

### 3.3 固定基准选项（fixed_alternative）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `fixed_alternative.enabled` | boolean | 否 | false | 是否启用 |
| `fixed_alternative.profile` | object | 条件必填 | - | 固定产品配置 |
| `fixed_alternative.label` | string | 否 | "当前产品" | 显示标签 |
| `fixed_alternative.position` | enum | 否 | `"random"` | 在选择集中的位置 |

**position 枚举**：
- `random` — 每集随机位置（默认，减少顺序偏差）
- `first` — 始终第一个
- `last` — 始终最后一个
- `fixed` — 固定位置（需指定 `fixed_position_index`）

**示例**：
```json
{
  "fixed_alternative": {
    "enabled": true,
    "profile": {
      "brand": "huawei",
      "price": 3999,
      "storage": "256gb",
      "battery": 5000,
      "charging": 66
    },
    "label": "您目前使用的手机",
    "position": "random"
  }
}
```

---

## 四、Layer 3: 画像联动（可选）

### 4.1 目标消费者画像（target_personas）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `target_personas` | array | 否 | `[]` | 画像ID列表 |
| `persona_adaptation.strategy` | enum | 否 | `"none"` | 画像适配策略 |

**适配策略枚举**：

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| `none` | 不使用画像适配 | 通用问卷 |
| `attribute_filter` | 根据画像筛选属性 | 只保留画像关心的属性 |
| `level_adjustment` | 调整水平范围 | 根据画像收入/偏好调整 |
| `per_segment` | 为每组画像生成独立问卷 | 不同人群不同问卷 |
| `context_enrichment` | 丰富情境描述 | 使用画像的场景反应 |

**示例**：
```json
{
  "target_personas": ["persona-001", "persona-003"],
  "persona_adaptation": {
    "strategy": "per_segment",
    "level_adjustment_rules": {
      "price": {
        "source": "layer1.socioeconomic.personal_annual_income",
        "mapping": {
          "3-8万": [1999, 2999, 3999],
          "15-30万": [3999, 5999, 7999],
          "30-50万": [5999, 7999, 9999]
        }
      }
    }
  }
}
```

---

### 4.2 决策情境（decision_context）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `decision_context.description` | string | 否 | 通用情境 | 决策场景描述 |
| `decision_context.time` | string | 否 | - | 时间情境 |
| `decision_context.location` | string | 否 | - | 地点情境 |
| `decision_context.emotion` | string | 否 | - | 情绪状态 |
| `decision_context.trigger` | string | 否 | - | 触发事件 |
| `decision_context.auto_generate_from_persona` | boolean | 否 | false | 从画像自动生成 |

**示例**：
```json
{
  "decision_context": {
    "description": "你的手机已经用了3年，电池续航明显下降。618大促期间，你打算换一部新手机。",
    "time": "周六下午，618大促期间",
    "location": "家中沙发上刷京东",
    "emotion": "期待但又有点选择困难",
    "trigger": "看到618预售开启的推送",
    "auto_generate_from_persona": true
  }
}
```

**auto_generate_from_persona 为 true 时的生成逻辑**：
1. 从画像的 `layer4.scene_reactions` 中提取购买相关场景
2. 从画像的 `layer2.purchase_behavior` 中提取渠道、时间偏好
3. 从画像的 `layer3.psychology` 中提取情绪触发点
4. 组合生成个性化情境描述

---

## 五、Layer 4: 高级特性（可选）

### 5.1 自适应设计参数（adaptive）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `adaptive.enabled` | boolean | 否 | false | 是否启用自适应 |
| `adaptive.method` | enum | 否 | `"bayesian_update"` | 自适应算法 |
| `adaptive.adapt_after` | integer | 否 | 4 | 第几题后开始自适应 |
| `adaptive.focus_attributes` | array | 否 | `[]` | 重点关注属性 |

**自适应方法枚举**：

| 方法 | 说明 |
|------|------|
| `bayesian_update` | 贝叶斯更新先验分布 |
| `utility_balance` | 效用平衡设计 |
| `efficiency_gain` | 效率增益最大化 |

**示例**：
```json
{
  "adaptive": {
    "enabled": true,
    "method": "bayesian_update",
    "adapt_after": 4,
    "focus_attributes": ["price", "brand"]
  }
}
```

---

### 5.2 多版本测试（versioning）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `versioning.enabled` | boolean | 否 | false | 是否生成多版本 |
| `versioning.count` | integer | 否 | 1 | 版本数量 |
| `versioning.diversity_metric` | enum | 否 | `"d_efficiency"` | 版本间差异度量 |

**示例**：
```json
{
  "versioning": {
    "enabled": true,
    "count": 4,
    "diversity_metric": "d_efficiency"
  }
}
```

---

### 5.3 呈现参数（presentation）

| 字段路径 | 类型 | 必填 | 默认值 | 说明 |
|---------|------|------|--------|------|
| `presentation.format` | enum | 否 | `"desktop"` | 输出格式 |
| `presentation.language` | string | 否 | `"zh-CN"` | 语言 |
| `presentation.brand_display` | enum | 否 | `"name_only"` | 品牌展示方式 |
| `presentation.price_display` | enum | 否 | `"absolute"` | 价格展示方式 |
| `presentation.show_attribute_labels` | boolean | 否 | true | 是否显示属性标签 |
| `presentation.randomize_attribute_order` | boolean | 否 | false | 是否随机属性顺序 |

**format 枚举**：
- `desktop` — PC端表格布局
- `mobile` — 移动端卡片布局
- `conversation` — 对话式（供模拟消费者Agent使用）
- `json` — 纯数据结构输出

**brand_display 枚举**：
- `name_only` — 仅显示品牌名称
- `logo_and_name` — Logo + 名称
- `blind` — 盲测（隐藏品牌，用字母代替）

**price_display 枚举**：
- `absolute` — 绝对价格（¥2999）
- `relative` — 相对价格（比基准高/低¥1000）
- `range` — 价格区间

---

## 六、完整输入示例

### 6.1 最小输入（MVP）

```json
{
  "product_category": "smartphone",
  "attributes": [
    {"id": "brand", "name": "品牌"},
    {"id": "price", "name": "价格"},
    {"id": "storage", "name": "存储容量"}
  ],
  "levels": {
    "brand": [{"value": "huawei", "label": "华为"}, {"value": "xiaomi", "label": "小米"}],
    "price": [{"value": 2999, "label": "¥2,999"}, {"value": 3999, "label": "¥3,999"}],
    "storage": [{"value": "128gb", "label": "128GB"}, {"value": "256gb", "label": "256GB"}]
  },
  "research_objective": "了解消费者对手机品牌和价格的偏好"
}
```

### 6.2 标准输入

```json
{
  "product_category": "smartphone",
  "attributes": [
    {"id": "brand", "name": "品牌", "type": "categorical"},
    {"id": "price", "name": "价格", "type": "price"},
    {"id": "storage", "name": "存储容量", "type": "categorical"},
    {"id": "battery", "name": "电池容量", "type": "continuous"},
    {"id": "charging", "name": "充电功率", "type": "continuous"}
  ],
  "levels": {
    "brand": [
      {"value": "huawei", "label": "华为"},
      {"value": "xiaomi", "label": "小米"},
      {"value": "apple", "label": "苹果"}
    ],
    "price": [
      {"value": 2999, "label": "¥2,999"},
      {"value": 3999, "label": "¥3,999"},
      {"value": 5999, "label": "¥5,999"}
    ],
    "storage": [
      {"value": "128gb", "label": "128GB"},
      {"value": "256gb", "label": "256GB"},
      {"value": "512gb", "label": "512GB"}
    ],
    "battery": [
      {"value": 4500, "label": "4500mAh"},
      {"value": 5000, "label": "5000mAh"},
      {"value": 5500, "label": "5500mAh"}
    ],
    "charging": [
      {"value": 33, "label": "33W"},
      {"value": 66, "label": "66W"},
      {"value": 120, "label": "120W"}
    ]
  },
  "research_objective": "评估新品智能手机概念的市场接受度，确定最优定价策略",
  "key_questions": [
    "消费者对各属性的相对重视程度",
    "120W快充的溢价空间",
    "品牌溢价的相对大小"
  ],
  "design_parameters": {
    "choice_sets": 12,
    "alternatives_per_set": 3,
    "include_none": true,
    "design_method": "d_optimal"
  },
  "constraints": {
    "prohibited_combinations": [
      {
        "description": "苹果不可能2999",
        "conditions": {"brand": ["apple"], "price": [2999]}
      }
    ]
  }
}
```

### 6.3 完整研究级输入（与画像联动）

```json
{
  "product_category": "smartphone",
  "attributes": [
    {"id": "brand", "name": "品牌", "type": "categorical"},
    {"id": "price", "name": "价格", "type": "price"},
    {"id": "storage", "name": "存储容量", "type": "categorical"},
    {"id": "battery", "name": "电池容量", "type": "continuous"},
    {"id": "charging", "name": "充电功率", "type": "continuous"}
  ],
  "levels": {
    "brand": [
      {"value": "huawei", "label": "华为"},
      {"value": "xiaomi", "label": "小米"},
      {"value": "apple", "label": "苹果"},
      {"value": "oppo", "label": "OPPO"}
    ],
    "price": [
      {"value": 2999, "label": "¥2,999"},
      {"value": 3999, "label": "¥3,999"},
      {"value": 4999, "label": "¥4,999"},
      {"value": 5999, "label": "¥5,999"}
    ],
    "storage": [
      {"value": "128gb", "label": "128GB"},
      {"value": "256gb", "label": "256GB"},
      {"value": "512gb", "label": "512GB"}
    ],
    "battery": [
      {"value": 4500, "label": "4500mAh"},
      {"value": 5000, "label": "5000mAh"},
      {"value": 5500, "label": "5500mAh"}
    ],
    "charging": [
      {"value": 33, "label": "33W"},
      {"value": 66, "label": "66W"},
      {"value": 120, "label": "120W"}
    ]
  },
  "research_objective": "评估新品智能手机概念的市场接受度，确定最优定价策略，预测市场份额",
  "key_questions": [
    "消费者对各属性的相对重视程度",
    "120W快充的溢价空间",
    "品牌溢价的相对大小",
    "存储容量升级的意愿价格弹性",
    "新品配置的最优组合"
  ],
  "target_personas": ["persona-001", "persona-003", "persona-005"],
  "persona_adaptation": {
    "strategy": "per_segment",
    "level_adjustment_rules": {
      "price": {
        "source": "layer1.socioeconomic.personal_annual_income",
        "mapping": {
          "3-8万": [1999, 2999, 3999],
          "8-15万": [2999, 3999, 4999],
          "15-30万": [3999, 4999, 5999],
          "30-50万": [4999, 5999, 7999]
        }
      }
    }
  },
  "decision_context": {
    "description": "你的手机已经用了3年，电池续航明显下降，存储空间也经常不足。你打算在618期间换一部新手机。",
    "auto_generate_from_persona": true
  },
  "design_parameters": {
    "choice_sets": 16,
    "alternatives_per_set": 3,
    "include_none": true,
    "none_label": "以上都不选，我会考虑其他品牌",
    "design_method": "d_optimal"
  },
  "fixed_alternative": {
    "enabled": true,
    "profile": {
      "brand": "huawei",
      "price": 3999,
      "storage": "256gb",
      "battery": 5000,
      "charging": 66
    },
    "label": "您目前使用的手机",
    "position": "random"
  },
  "constraints": {
    "prohibited_combinations": [
      {
        "description": "苹果不可能2999",
        "conditions": {"brand": ["apple"], "price": [2999]}
      },
      {
        "description": "低配版不能有顶配快充",
        "conditions": {"price": [2999], "charging": [120]}
      }
    ],
    "required_combinations": [
      {
        "description": "新品配置必须测试",
        "profile": {
          "brand": "huawei",
          "price": 4999,
          "storage": "512gb",
          "battery": 5500,
          "charging": 120
        },
        "min_appearances": 3
      }
    ]
  },
  "adaptive": {
    "enabled": false
  },
  "versioning": {
    "enabled": true,
    "count": 4
  },
  "presentation": {
    "format": "mobile",
    "language": "zh-CN",
    "brand_display": "logo_and_name",
    "price_display": "absolute",
    "show_attribute_labels": true,
    "randomize_attribute_order": false
  }
}
```

---

## 七、校验规则汇总

### 7.1 必填字段校验

| # | 校验项 | 规则 | 错误码 |
|---|--------|------|--------|
| 1 | `product_category` | 非空字符串 | `CBC-E001` |
| 2 | `attributes` | 数组，长度 2-8 | `CBC-E002` |
| 3 | `attributes[].id` | 非空，唯一，合法标识符 | `CBC-E003` |
| 4 | `attributes[].name` | 非空字符串 | `CBC-E004` |
| 5 | `levels` | 非空对象 | `CBC-E005` |
| 6 | `levels`键 | 必须与 `attributes[].id` 匹配 | `CBC-E006` |
| 7 | `levels[属性]` | 数组，长度 2-6 | `CBC-E007` |
| 8 | `levels[属性]`元素 | 值在属性内唯一 | `CBC-E008` |
| 9 | `research_objective` | 长度 ≥ 10 | `CBC-E009` |

### 7.2 逻辑一致性校验

| # | 校验项 | 规则 | 错误码 |
|---|--------|------|--------|
| 10 | 禁止组合 | 至少涉及2个属性 | `CBC-E010` |
| 11 | 禁止组合值 | 必须是有效水平 | `CBC-E011` |
| 12 | 必须包含组合 | 所有属性值有效 | `CBC-E012` |
| 13 | 固定选项 | 如启用则 profile 必填 | `CBC-E013` |
| 14 | 固定选项值 | 必须是有效水平 | `CBC-E014` |
| 15 | 选择集数量 | 必须足够容纳必须组合 | `CBC-E015` |
| 16 | 设计效率 | D-efficiency ≥ 0.85（目标），≥ 0.80 可接受 | `CBC-W001` |

### 7.3 画像联动校验

| # | 校验项 | 规则 | 错误码 |
|---|--------|------|--------|
| 17 | 画像ID | 必须在画像库中存在 | `CBC-E016` |
| 18 | 收入水平映射 | 必须覆盖所有画像的收入档位 | `CBC-W002` |
| 19 | 情境生成 | 画像必须有 Layer 4 场景数据 | `CBC-W003` |

---

*本文档与以下文件配套使用：*
- `01-CBC系统架构与解决方案.md`（整体方案与必填/可选说明）
- `03-CBC实验设计算法说明.md`（D-optimal、正交设计等算法）
- `04-CBC与模拟消费者集成方案.md`（模拟消费者Agent填写问卷的接口）
