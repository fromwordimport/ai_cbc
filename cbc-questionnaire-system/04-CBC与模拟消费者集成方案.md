# CBC问卷与模拟消费者集成方案

> **版本**：v1.0  
> **定位**：定义CBC问卷生成系统与现有消费者模拟Agent的集成接口、数据流与协作流程  
> **配套文档**：`01-CBC系统架构与解决方案.md`、`02-CBC问卷生成输入规范.md`

---

## 一、集成架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        消费者模拟系统                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  画像生成Agent │  │  行为模拟Agent │  │   CBC问卷生成Agent   │  │
│  │  (已有)        │  │  (已有)        │  │   【新增】           │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                      │              │
│         ▼                 ▼                      ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     数据存储层                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │  │
│  │  │ 画像库    │  │ 模拟记录库│  │   CBC问卷库         │   │  │
│  │  │ Personas │  │ Simulations│  │   Questionnaires    │   │  │
│  │  └──────────┘  └──────────┘  └──────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              模拟消费者Agent（填写CBC问卷）               │  │
│  │                                                          │  │
│  │  输入：画像 + 情境 + CBC问卷 → 输出：逐题选择 + 理由      │  │
│  │                                                          │  │
│  │  • persona-001：28岁女产品经理，疲惫深夜刷手机...        │  │
│  │  • 情境：618大促，预算4000，想换手机...                  │  │
│  │  • 问卷：16道选择题，每题3个选项...                      │  │
│  │  • 输出：选了A，因为...                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              联合分析引擎（结果分析）                      │  │
│  │                                                          │  │
│  │  • 个体层面：每个模拟消费者的效用函数                     │  │
│  │  • 群体层面：属性重要性排序 + 市场份额模拟                │  │
│  │  • 细分层面：不同画像群体的偏好差异                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、核心集成流程

### 2.1 完整数据流

```
Phase 1: 问卷生成
─────────────────
业务输入 → CBC问卷Agent → 生成问卷（选择集 + 情境）
                              ↓
                     存入 CBC问卷库

Phase 2: 模拟消费者分配
───────────────────────
画像库 → 筛选目标画像 → 为每个画像绑定问卷 + 个性化情境
                              ↓
                     创建模拟任务队列

Phase 3: 模拟填写
─────────────────
模拟消费者Agent ← 读取画像 + 情境 + 问卷
                              ↓
                     逐题模拟决策过程
                              ↓
                     输出：选择结果 + 决策理由
                              ↓
                     存入 模拟回答库

Phase 4: 结果分析
─────────────────
模拟回答库 → 联合分析引擎 → 效用值 + 重要性 + 市场份额
                              ↓
                     生成洞察报告
```

### 2.2 时序图

```
┌────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐
│ 用户   │    │ CBC问卷Agent │    │ 画像库       │    │ 模拟消费者Agent│    │ 分析引擎  │
└───┬────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └────┬─────┘
    │                │                   │                   │                │
    │ 1.提交产品属性+研究目标              │                   │                │
    │────────────────>│                   │                   │                │
    │                │                   │                   │                │
    │                │ 2.查询目标画像信息   │                   │                │
    │                │──────────────────>│                   │                │
    │                │                   │                   │                │
    │                │ 3.返回画像列表      │                   │                │
    │                │<──────────────────│                   │                │
    │                │                   │                   │                │
    │                │ 4.生成CBC问卷（选择集）                │                │
    │                │──────────────────────────────────────>│                │
    │                │                   │                   │                │
    │ 5.返回问卷ID    │                   │                   │                │
    │<────────────────│                   │                   │                │
    │                │                   │                   │                │
    │ 6.启动模拟任务  │                   │                   │                │
    │────────────────>│                   │                   │                │
    │                │                   │                   │                │
    │                │ 7.分派任务：画像+问卷+情境               │                │
    │                │──────────────────────────────────────>│                │
    │                │                   │                   │                │
    │                │                   │                   │ 8.逐题模拟决策  │
    │                │                   │                   │───┐            │
    │                │                   │                   │   │            │
    │                │                   │                   │<──┘            │
    │                │                   │                   │                │
    │                │ 9.返回模拟回答     │                   │                │
    │                │>──────────────────────────────────────│                │
    │                │                   │                   │                │
    │                │ 10.存储回答       │                   │                │
    │                │──────────────────────────────────────────────────────>│
    │                │                   │                   │                │
    │ 11.任务完成通知 │                   │                   │                │
    │<────────────────│                   │                   │                │
    │                │                   │                   │                │
    │ 12.请求分析报告 │                   │                   │                │
    │──────────────────────────────────────────────────────────────────────>│
    │                │                   │                   │                │
    │ 13.返回洞察报告 │                   │                   │                │
    │<──────────────────────────────────────────────────────────────────────│
    │                │                   │                   │                │
```

---

## 三、API接口定义

### 3.1 生成CBC问卷并绑定画像

```http
POST /api/v1/cbc/questionnaires
```

**请求体**：

```json
{
  "product_category": "smartphone",
  "attributes": [ ... ],
  "levels": { ... },
  "research_objective": "评估新品市场接受度",
  "target_personas": ["persona-001", "persona-002", "persona-003"],
  "persona_adaptation": {
    "strategy": "per_segment"
  },
  "decision_context": {
    "auto_generate_from_persona": true
  },
  "design_parameters": {
    "choice_sets": 12,
    "alternatives_per_set": 3,
    "include_none": true
  }
}
```

**响应**：

```json
{
  "code": 201,
  "message": "CBC questionnaire created",
  "data": {
    "questionnaire_id": "cbc-20250608-001",
    "status": "READY",
    "segments": [
      {
        "segment_id": "seg-001",
        "persona_ids": ["persona-001"],
        "questionnaire_version": "v1",
        "choice_sets_count": 12,
        "d_efficiency": 0.92,
        "context": "你的手机已经用了3年...（从persona-001自动生成）"
      },
      {
        "segment_id": "seg-002",
        "persona_ids": ["persona-002"],
        "questionnaire_version": "v2",
        "choice_sets_count": 12,
        "d_efficiency": 0.89,
        "context": "你最近升职加薪了...（从persona-002自动生成）"
      }
    ]
  }
}
```

---

### 3.2 获取特定画像的CBC问卷

```http
GET /api/v1/cbc/questionnaires/{questionnaire_id}/for-persona/{persona_id}
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "questionnaire_id": "cbc-20250608-001",
    "segment_id": "seg-001",
    "persona_id": "persona-001",
    "decision_context": {
      "description": "你的手机已经用了3年，电池续航明显下降...",
      "time": "周三晚上11点",
      "location": "家中沙发上",
      "emotion": "疲惫但有点焦虑",
      "trigger": "刷到618手机预售广告"
    },
    "choice_sets": [
      {
        "set_id": 1,
        "question_text": "假设你正在618大促期间选购手机，以下三个选项中你会选择哪个？",
        "alternatives": [
          {
            "alt_id": "A",
            "attributes": {
              "brand": {"value": "huawei", "label": "华为"},
              "price": {"value": 3999, "label": "¥3,999"},
              "storage": {"value": "256gb", "label": "256GB"},
              "battery": {"value": 5000, "label": "5000mAh"},
              "charging": {"value": 66, "label": "66W快充"}
            }
          },
          {
            "alt_id": "B",
            "attributes": {
              "brand": {"value": "xiaomi", "label": "小米"},
              "price": {"value": 2999, "label": "¥2,999"},
              "storage": {"value": "128gb", "label": "128GB"},
              "battery": {"value": 5500, "label": "5500mAh"},
              "charging": {"value": 120, "label": "120W快充"}
            }
          },
          {
            "alt_id": "C",
            "attributes": {
              "brand": {"value": "apple", "label": "苹果"},
              "price": {"value": 5999, "label": "¥5,999"},
              "storage": {"value": "256gb", "label": "256GB"},
              "battery": {"value": 4500, "label": "4500mAh"},
              "charging": {"value": 33, "label": "33W快充"}
            }
          }
        ],
        "none_option": {
          "enabled": true,
          "label": "以上都不选"
        }
      }
      // ... 更多选择集
    ]
  }
}
```

---

### 3.3 提交模拟消费者回答

```http
POST /api/v1/cbc/simulations
```

**请求体**：

```json
{
  "questionnaire_id": "cbc-20250608-001",
  "persona_id": "persona-001",
  "simulation_type": "cbc_choice",
  "scenario_context": {
    "time": "周三晚上11点",
    "location": "家中沙发上",
    "emotion": "疲惫但有点焦虑",
    "cognitive_load": "低"
  },
  "responses": [
    {
      "set_id": 1,
      "chosen_alternative": "B",
      "none_chosen": false,
      "decision_rationale": {
        "surface_reason": "小米这个配置性价比很高，120W快充很吸引人",
        "deep_reason": "最近被领导批评了压力大，想买点东西安慰自己，但又不想花太多钱",
        "key_factors": ["价格", "充电功率"],
        "hesitation": "犹豫了一下华为的牌子更响，但贵1000块"
      },
      "attention_allocation": {
        "first_noticed": "120W快充",
        "most_considered": "价格 vs 充电功率",
        "ignored": "电池容量"
      },
      "emotional_state": {
        "before": "疲惫",
        "during": "心动",
        "after": "有点纠结但倾向B"
      },
      "confidence": 7
    }
    // ... 更多选择集的回答
  ]
}
```

**响应**：

```json
{
  "code": 201,
  "message": "CBC simulation completed",
  "data": {
    "simulation_id": "sim-cbc-20250608-001",
    "questionnaire_id": "cbc-20250608-001",
    "persona_id": "persona-001",
    "completion_status": "COMPLETED",
    "responses_count": 12,
    "authenticity_score": 10.5,
    "estimated_utilities": {
      "brand": {
        "huawei": 0.45,
        "xiaomi": 0.32,
        "apple": 0.23
      },
      "price": {
        "2999": 0.68,
        "3999": 0.35,
        "5999": -0.42
      }
      // ...
    }
  }
}
```

---

### 3.3.b 问卷系统 → 分析系统 标准数据交换格式

3.3节定义了**模拟消费者 → 问卷系统**的提交格式。本节定义**问卷系统 → 分析系统**的数据交换标准，确保原始回答数据能够被联合分析引擎正确解析和处理。

#### 一、数据流架构

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  模拟消费者Agent  │ ──→ │   问卷系统        │ ──→ │   分析系统        │
│                 │ POST │  (存储原始回答)   │ EXPORT│  (联合分析引擎)   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                              │                          │
                              ▼                          ▼
                        ┌───────────┐              ┌───────────┐
                        │ 回答记录库 │              │ 效用值/WTP │
                        │ (Raw DB)  │              │ 市场份额  │
                        └───────────┘              └───────────┘
```

**关键原则**：
- 问卷系统存储**原始回答**（含完整上下文），分析系统接收**标准结构化数据**
- 交换格式与具体问卷设计解耦，分析系统不关心题目是如何生成的
- 支持增量导出（新增回答自动追加）

---

#### 二、原始回答存储格式（问卷系统内部）

问卷系统存储的每条回答记录应包含以下字段：

```json
{
  "record_id": "resp-cbc-20250608-001-001",
  "questionnaire_id": "cbc-20250608-001",
  "segment_id": "seg-001",
  "simulation_id": "sim-cbc-20250608-001",
  "persona_id": "persona-001",
  "submitted_at": "2026-06-08T14:30:00Z",
  "raw_choice_data": {
    "choice_sets": [
      {
        "set_id": 1,
        "set_index": 0,
        "alternatives": [
          {
            "alt_id": "A",
            "alt_index": 0,
            "attributes": {
              "brand": "huawei",
              "price": 3999,
              "storage": "256gb",
              "battery": 5000,
              "charging": 66
            }
          },
          {
            "alt_id": "B",
            "alt_index": 1,
            "attributes": {
              "brand": "xiaomi",
              "price": 2999,
              "storage": "128gb",
              "battery": 5500,
              "charging": 120
            }
          },
          {
            "alt_id": "C",
            "alt_index": 2,
            "attributes": {
              "brand": "apple",
              "price": 5999,
              "storage": "256gb",
              "battery": 4500,
              "charging": 33
            }
          }
        ],
        "none_option_enabled": true,
        "chosen": {
          "alt_id": "B",
          "alt_index": 1,
          "none_chosen": false
        }
      }
    ]
  },
  "qualitative_data": {
    "decision_rationale": { ... },
    "attention_allocation": { ... },
    "emotional_state": { ... },
    "confidence": 7
  },
  "context_data": {
    "decision_context": { ... },
    "scenario_context": { ... }
  },
  "system_metadata": {
    "generation_duration_ms": 8500,
    "model_version": "claude-sonnet-4-6",
    "prompt_tokens": 2048,
    "completion_tokens": 512
  }
}
```

**存储要点**：
- `raw_choice_data` 必须保存每道题的**完整选项配置**（不仅仅是ID），因为分析系统需要知道每个选项的属性值才能构建设计矩阵
- 使用 `alt_index`（从0开始的整数索引）而非仅 `alt_id`，便于分析系统构建数值矩阵
- `none_option_enabled` 标记该题是否提供了"都不选"，影响模型设定

---

#### 三、数据导出接口（问卷系统 → 分析系统）

```http
GET /api/v1/cbc/questionnaires/{questionnaire_id}/export
```

**查询参数**：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `format` | string | 否 | `json` | 导出格式：`json` / `csv` / `parquet` |
| `include_qualitative` | boolean | 否 | `false` | 是否包含质性数据 |
| `persona_filter` | array | 否 | - | 按画像ID过滤 |
| `segment_filter` | array | 否 | - | 按细分群体过滤 |
| `since` | datetime | 否 | - | 只导出该时间之后的新增数据 |
| `encoding_scheme` | enum | 否 | `effects` | 设计矩阵编码方式 |

**编码方式枚举**：

| 编码方式 | 说明 | 分析系统支持 |
|---------|------|-------------|
| `raw` | 原始值（不编码） | 需要分析系统自行处理 |
| `dummy` | 虚拟变量编码（0/1） | 通用 |
| `effects` | 效果编码（默认） | 推荐，参数和为0 |
| `orthogonal` | 正交多项式编码 | 连续/有序变量 |

**响应（JSON格式）**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "export_id": "exp-20250608-001",
    "questionnaire_id": "cbc-20250608-001",
    "generated_at": "2026-06-08T15:00:00Z",
    "record_count": 50,
    "format": "json",
    "encoding_scheme": "effects",
    "schema_version": "1.0",
    "dataset": {
      "metadata": {
        "attributes": [
          {"id": "brand", "name": "品牌", "type": "categorical", "levels": ["huawei", "xiaomi", "apple"]},
          {"id": "price", "name": "价格", "type": "price", "levels": [2999, 3999, 5999]},
          {"id": "storage", "name": "存储容量", "type": "categorical", "levels": ["128gb", "256gb"]},
          {"id": "battery", "name": "电池容量", "type": "continuous", "unit": "mAh"},
          {"id": "charging", "name": "充电功率", "type": "continuous", "unit": "W"}
        ],
        "design_parameters": {
          "num_sets": 12,
          "alts_per_set": 3,
          "none_option": true
        }
      },
      "choice_records": [
        {
          "respondent_id": "persona-001",
          "respondent_index": 0,
          "segment_id": "seg-001",
          "choice_set_id": 1,
          "choice_set_index": 0,
          "alternatives": [
            {
              "alt_index": 0,
              "chosen": false,
              "attribute_values": {
                "brand": "huawei",
                "price": 3999,
                "storage": "256gb",
                "battery": 5000,
                "charging": 66
              },
              "encoded_vector": [1, 0, 3999, 1, 0, 5000, 66]
            },
            {
              "alt_index": 1,
              "chosen": true,
              "attribute_values": {
                "brand": "xiaomi",
                "price": 2999,
                "storage": "128gb",
                "battery": 5500,
                "charging": 120
              },
              "encoded_vector": [0, 1, 2999, 0, 0, 5500, 120]
            },
            {
              "alt_index": 2,
              "chosen": false,
              "attribute_values": {
                "brand": "apple",
                "price": 5999,
                "storage": "256gb",
                "battery": 4500,
                "charging": 33
              },
              "encoded_vector": [-1, -1, 5999, 1, 0, 4500, 33]
            }
          ],
          "none_chosen": false
        }
      ],
      "respondent_attributes": {
        "persona-001": {
          "age_group": "25-34",
          "gender": "女",
          "income_tier": "15-30万",
          "city_tier": "新一线",
          "price_sensitivity": "理性比价"
        }
      }
    }
  }
}
```

---

#### 四、标准交换Schema详解

##### 4.1 顶层结构

```typescript
interface CBCRawDataset {
  metadata: DatasetMetadata;           // 问卷元数据（属性定义、设计参数）
  choice_records: ChoiceRecord[];      // 选择记录（核心数据）
  respondent_attributes?: RespondentMap; // 受访者画像属性（可选，用于细分分析）
}
```

##### 4.2 元数据（DatasetMetadata）

```typescript
interface DatasetMetadata {
  attributes: AttributeMeta[];         // 属性定义列表
  design_parameters: DesignParameters; // 实验设计参数
}

interface AttributeMeta {
  id: string;                          // 属性标识（如 "brand"）
  name: string;                        // 属性显示名称（如 "品牌"）
  type: "categorical" | "continuous" | "ordinal" | "price";
  levels?: LevelMeta[];                // 分类/有序属性的水平定义
  unit?: string;                       // 连续变量的单位（如 "mAh", "W"）
}

interface LevelMeta {
  value: any;                          // 水平值（如 "huawei" 或 3999）
  label: string;                       // 水平显示标签（如 "华为"）
  index: number;                       // 水平索引（0-based，用于编码）
}

interface DesignParameters {
  num_sets: number;                    // 选择集数量
  alts_per_set: number;                // 每集选项数
  none_option: boolean;                // 是否包含"都不选"
}
```

**关键约束**：
- `attributes` 的顺序决定了 `encoded_vector` 中各元素的顺序
- 分析系统必须根据 `type` 选择正确的编码方式
- `levels` 中的 `index` 必须连续且从0开始

##### 4.3 选择记录（ChoiceRecord）

```typescript
interface ChoiceRecord {
  respondent_id: string;               // 受访者/画像唯一标识
  respondent_index: number;            // 受访者索引（0-based，用于矩阵行标识）
  segment_id?: string;                 // 所属细分群体（可选）
  choice_set_id: number;               // 选择集ID（问卷内唯一）
  choice_set_index: number;            // 选择集索引（0-based，用于模型分组）
  alternatives: AlternativeRecord[];   // 该选择集中的所有选项
  none_chosen: boolean;                // 是否选择了"都不选"
}

interface AlternativeRecord {
  alt_index: number;                   // 选项在选择集中的索引（0-based）
  chosen: boolean;                     // 是否被选中
  attribute_values: Record<string, any>; // 原始属性值 {attr_id: value}
  encoded_vector: number[];            // 编码后的设计向量
}
```

**编码向量 `encoded_vector` 的构建规则（Effects Coding）**：

```
假设属性顺序为：[brand(3水平), price(连续), storage(2水平), battery(连续), charging(连续)]

编码向量长度 = (3-1) + 1 + (2-1) + 1 + 1 = 7

示例：
- brand="huawei" (index 0) → [1, 0]
- brand="xiaomi" (index 1) → [0, 1]
- brand="apple"  (index 2) → [-1, -1]
- price=3999 → [3999]
- storage="256gb" (index 1) → [1]  (假设128gb=0, 256gb=1，效果编码下只有1个参数)
  等等，2水平的effects coding应该是：
  - level 0: [1]
  - level 1: [-1]
  
  更正：2个水平用effects coding只需要1个变量
  - index 0 → [1]
  - index 1 → [-1]

- battery=5000 → [5000]
- charging=66 → [66]

最终 encoded_vector = [1, 0, 3999, 1, 5000, 66]  // 品牌2维 + 价格1维 + 存储1维 + 电池1维 + 充电1维 = 6维
```

> **注意**：`encoded_vector` 的维度必须一致，且顺序与 `metadata.attributes` 严格对应。

##### 4.4 受访者画像属性（RespondentMap）

```typescript
interface RespondentMap {
  [respondent_id: string]: RespondentAttributes;
}

interface RespondentAttributes {
  // 以下字段与 consumer-simulation 系统的画像字段对齐
  age_group?: string;
  gender?: string;
  income_tier?: string;
  city_tier?: string;
  price_sensitivity?: string;
  brand_loyalty?: string;
  decision_style?: string;
  [key: string]: any;                  // 允许扩展其他画像字段
}
```

---

#### 五、CSV/Parquet 格式规范

当 `format=csv` 时，数据以**长格式（Long Format）**导出，每行代表一个"受访者-选择集-选项"组合：

```csv
respondent_id,respondent_index,segment_id,choice_set_id,choice_set_index,alt_index,chosen,brand,price,storage,battery,charging,none_chosen
persona-001,0,seg-001,1,0,0,0,huawei,3999,256gb,5000,66,0
persona-001,0,seg-001,1,0,1,1,xiaomi,2999,128gb,5500,120,0
persona-001,0,seg-001,1,0,2,0,apple,5999,256gb,4500,33,0
persona-001,0,seg-001,2,1,0,0,apple,3999,128gb,5000,120,0
persona-001,0,seg-001,2,1,1,0,huawei,5999,256gb,4500,33,0
persona-001,0,seg-001,2,1,2,1,xiaomi,2999,256gb,5500,66,0
...
```

**长格式优势**：
- 直接兼容 statsmodels、biogeme、mlogit 等统计包
- 易于用 pandas / R 读取
- 支持变长的选择集（某些题3个选项，某些题4个）

---

#### 六、增量导出机制

```http
GET /api/v1/cbc/questionnaires/{questionnaire_id}/export?since=2026-06-08T10:00:00Z
```

**场景**：
- 批量模拟任务分批完成，分析系统需要增量更新结果
- 真人调研中，数据随时间积累，需要持续分析

**响应额外字段**：

```json
{
  "data": {
    "incremental": true,
    "since": "2026-06-08T10:00:00Z",
    "new_record_count": 15,
    "total_record_count": 65
  }
}
```

---

#### 七、分析系统接收数据后的处理流程

```
分析系统接收标准交换数据
      │
      ▼
┌─────────────────────────────┐
│ 1. Schema校验               │
│    - 属性定义完整性          │
│    - 编码向量维度一致性      │
│    - 选择集索引连续性        │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 2. 构建长格式数据表          │
│    - respondent_id           │
│    - choice_set_id           │
│    - alt_id                  │
│    - chosen (0/1)            │
│    - X1, X2, ... Xp (编码值) │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 3. 模型拟合                  │
│    - 条件Logit (CL)          │
│    - 混合Logit (MXL)         │
│    - Hierarchical Bayes (HB) │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 4. 输出结果                  │
│    - 部分效用值              │
│    - 属性重要性              │
│    - 标准误                  │
│    - WTP                     │
└─────────────────────────────┘
```

---

#### 八、数据交换的校验规则

| # | 校验项 | 规则 | 失败处理 |
|---|--------|------|---------|
| 1 | 属性定义完整性 | metadata.attributes 非空 | 返回错误，拒绝分析 |
| 2 | 编码向量维度 | 所有 encoded_vector 长度一致 | 返回错误，指出不一致位置 |
| 3 | 选择集完整性 | 每个 respondent 的选择集数量一致 | 允许缺失，但需标记 |
| 4 | 水平值有效性 | attribute_values 的值必须在 levels 中 | 返回警告，跳过无效记录 |
| 5 | 每题必有一选 | 每个 choice_set 中至少一个 chosen=true | 返回警告，标记异常记录 |
| 6 | 样本量充足 | record_count ≥ num_params × 5 | 返回警告，建议增加样本 |

---

### 3.4 批量执行模拟

```http
POST /api/v1/cbc/simulations/batch
```

**请求体**：

```json
{
  "questionnaire_id": "cbc-20250608-001",
  "persona_ids": ["persona-001", "persona-002", "persona-003"],
  "parallel": true,
  "max_workers": 5
}
```

**响应**：

```json
{
  "code": 202,
  "message": "Batch simulation task accepted",
  "data": {
    "task_id": "task-cbc-20250608-001",
    "status": "IN_PROGRESS",
    "total_simulations": 3,
    "completed": 0,
    "estimated_seconds": 180
  }
}
```

---

### 3.5 获取联合分析结果

```http
GET /api/v1/cbc/questionnaires/{questionnaire_id}/results
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "questionnaire_id": "cbc-20250608-001",
    "sample_size": 50,
    "aggregate_results": {
      "attribute_importance": {
        "price": 42.5,
        "brand": 23.8,
        "charging": 15.2,
        "storage": 12.3,
        "battery": 6.2
      },
      "part_worth_utilities": {
        "brand": {
          "huawei": 0.82,
          "xiaomi": 0.45,
          "apple": 1.15,
          "oppo": 0.38
        },
        "price": {
          "2999": 1.52,
          "3999": 0.68,
          "4999": -0.35,
          "5999": -1.85
        }
        // ...
      },
      "willingness_to_pay": {
        "charging_120w_vs_33w": 680,
        "storage_512gb_vs_128gb": 520,
        "brand_apple_vs_xiaomi": 1200
      }
    },
    "segment_results": [
      {
        "segment_id": "seg-001",
        "persona_ids": ["persona-001", "persona-004", "persona-007"],
        "segment_label": "价格敏感型",
        "attribute_importance": {
          "price": 55.2,
          "brand": 15.3,
          "charging": 12.8,
          "storage": 10.5,
          "battery": 6.2
        }
      }
      // ...
    ],
    "market_simulation": {
      "scenarios": [
        {
          "scenario_name": "新品配置A",
          "profile": {"brand": "huawei", "price": 4999, "storage": "512gb", "battery": 5500, "charging": 120},
          "predicted_share": 28.5
        },
        {
          "scenario_name": "竞品配置B",
          "profile": {"brand": "xiaomi", "price": 3999, "storage": "256gb", "battery": 5000, "charging": 66},
          "predicted_share": 35.2
        }
      ]
    }
  }
}
```

---

## 四、模拟消费者Agent的Prompt设计

### 4.1 核心Prompt结构

```markdown
# 角色设定
你是一位真实的消费者，以下是你的生活背景：

{persona_profile}  # 完整四层画像

# 当前情境
{decision_context}  # 个性化情境描述

# 任务说明
你现在正在{渠道}上{购物目的}。

我会向你展示若干个手机配置选项（每题3个），请你：
1. 仔细阅读每个选项
2. 根据你的真实偏好做出选择
3. 解释你的选择理由（表面原因 + 深层心理原因）
4. 描述你的决策过程（先看什么、犹豫什么、忽略什么）

# 决策规则
- 你的选择必须符合你的人物画像和当前情境
- 如果你处于"疲惫/低认知资源"状态，可以适当降低分析深度
- 如果你处于"焦虑"状态，可能对限时促销更敏感
- 不要做出"完美理性人"的选择，要体现你的真实矛盾

# 输出格式
对于每一题，请按以下格式输出：

## 第X题
**选择**：A / B / C / 都不选

**选择理由**：
- 表面原因：...
- 深层原因：...

**决策过程**：
- 第一眼注意到：...
- 重点比较了：...
- 犹豫之处：...
- 最终决定因素：...

**情绪变化**：
- 看题前：...
- 比较时：...
- 决定后：...

**信心度**：1-10分
```

### 4.2 情境注入模板

```markdown
# 情境生成逻辑（auto_generate_from_persona: true）

## 输入：画像数据

### Layer 1（基础骨架）
- 年龄：{age}
- 收入：{income}
- 城市：{city}

### Layer 2（行为签名）
- 价格敏感度：{price_sensitivity}
- 决策周期：{decision_cycle}
- 购买渠道：{channel_preference}
- 信息处理风格：{info_processing_style}

### Layer 3（心理引擎）
- 核心焦虑：{core_anxiety}
- 矛盾张力：{tension}

### Layer 4（场景反应）
- 大促期间反应：{promo_reaction}
- 压力大时反应：{stress_reaction}

## 输出生成规则

1. **时间情境**：根据购买时间偏好 + 当前情绪
   - 价格敏感 + 疲惫 → "深夜刷手机，被促销信息吸引"
   - 理性比价 + 周末 → "周六下午，做了功课后理性比较"

2. **预算框架**：根据收入 + 价格敏感度
   - 高收入 + 理性比价 → "预算充足，但追求性价比"
   - 低收入 + 促销敏感 → "预算有限，等了很久的大促"

3. **情绪基线**：根据核心焦虑 + 近期事件
   - 同辈压力 → "看到同事换了新手机，有点心动"
   - 职业倦怠 → "工作压力大，想买点东西犒劳自己"

4. **决策约束**：根据决策风格
   - 参数党 → "已经看了3天测评，心里有数"
   - 口碑党 → "看了很多用户评价，还在纠结"
   - KOL依赖 → "关注的博主推荐了这款"
```

---

## 五、结果分析引擎

### 5.1 个体层面分析（每个模拟消费者）

```python
# 伪代码：个体效用估计
class IndividualUtilityEstimator:
    """
    基于模拟消费者的选择序列，估计其个体层面的效用函数
    """
    
    def estimate(self, responses: list[ChoiceResponse]) -> IndividualUtilities:
        """
        使用条件Logit模型或Mixed Logit模型估计个体效用
        """
        # 1. 构建选择数据矩阵
        choice_data = self.build_choice_data(responses)
        
        # 2. 拟合条件Logit模型
        model = ConditionalLogit()
        model.fit(choice_data)
        
        # 3. 提取部分效用值（Part-worth utilities）
        part_worths = model.extract_part_worths()
        
        # 4. 计算属性重要性
        importance = self.calculate_importance(part_worths)
        
        # 5. 计算支付意愿（WTP）
        wtp = self.calculate_wtp(part_worths)
        
        return IndividualUtilities(
            part_worths=part_worths,
            importance=importance,
            wtp=wtp,
            model_fit=model.summary()
        )
```

### 5.2 群体层面分析

```python
class AggregateAnalyzer:
    """
    聚合所有模拟消费者的结果，生成群体层面的洞察
    """
    
    def analyze(self, individual_results: list[IndividualUtilities]) -> AggregateResults:
        # 1. 平均属性重要性
        avg_importance = self.average_importance(individual_results)
        
        # 2. 效用分布分析
        utility_distribution = self.analyze_utility_distribution(individual_results)
        
        # 3. 人群细分（基于偏好相似性聚类）
        segments = self.segment_by_preferences(individual_results)
        
        # 4. 市场份额模拟
        market_sim = self.simulate_market_share(
            product_profiles=[...],
            individual_utilities=individual_results
        )
        
        return AggregateResults(
            average_importance=avg_importance,
            utility_distribution=utility_distribution,
            segments=segments,
            market_simulation=market_sim
        )
```

### 5.3 与画像的交叉分析

```python
class PersonaCrossAnalyzer:
    """
    将CBC结果与消费者画像特征进行交叉分析
    """
    
    def cross_analyze(self, 
                      cbc_results: list[IndividualUtilities],
                      personas: list[Profile]) -> CrossAnalysis:
        
        # 1. 收入 vs 价格敏感度
        income_price_corr = self.correlate(
            x=[p.income for p in personas],
            y=[r.importance['price'] for r in cbc_results]
        )
        
        # 2. 品牌忠诚度 vs 品牌效用
        brand_loyalty_corr = self.correlate(
            x=[p.brand_loyalty for p in personas],
            y=[r.part_worths['brand'] for r in cbc_results]
        )
        
        # 3. 焦虑类型 vs 决策模式
        anxiety_decision_pattern = self.cross_tabulate(
            rows=[p.core_anxiety for p in personas],
            cols=[r.decision_pattern for r in cbc_results]
        )
        
        return CrossAnalysis(
            income_price_sensitivity=income_price_corr,
            brand_loyalty_brand_utility=brand_loyalty_corr,
            anxiety_decision_patterns=anxiety_decision_pattern
        )
```

---

## 六、使用示例：从画像到洞察的完整流程

### Step 1: 生成画像

```python
# 使用现有系统生成50个消费者画像
personas = generate_personas(
    count=50,
    scenario="smartphone_purchase",
    diversity_requirements={
        "age_span": [18, 55],
        "income_tiers": ["3-8万", "8-15万", "15-30万", "30-50万"],
        "city_tiers": ["一线", "新一线", "二线"]
    }
)
```

### Step 2: 生成CBC问卷

```python
# 生成与画像联动的CBC问卷
questionnaire = create_cbc_questionnaire(
    product_category="smartphone",
    attributes={
        "brand": ["华为", "小米", "苹果", "OPPO"],
        "price": [2999, 3999, 4999, 5999],
        "storage": ["128GB", "256GB", "512GB"],
        "battery": [4500, 5000, 5500],
        "charging": [33, 66, 120]
    },
    research_objective="评估新品概念，确定最优定价",
    target_personas=[p.id for p in personas],
    persona_adaptation="per_segment",
    auto_context=True
)
```

### Step 3: 模拟消费者填写

```python
# 批量执行模拟
results = batch_simulate_cbc(
    questionnaire_id=questionnaire.id,
    persona_ids=[p.id for p in personas],
    parallel=True
)
```

### Step 4: 分析结果

```python
# 获取洞察报告
report = analyze_cbc_results(
    questionnaire_id=questionnaire.id,
    analysis_types=[
        "attribute_importance",
        "willingness_to_pay",
        "market_simulation",
        "persona_cross_analysis"
    ]
)

# 输出示例洞察
print(report.insights)
# → "价格是最重要的属性（重要性42.5%），但高价位消费者更关注品牌"
# → "120W快充的支付意愿为680元，但仅在30-50万收入群体中显著"
# → "华为新品配置A预计可获得28.5%的市场份额"
```

---

## 七、常见集成问题与解决方案

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 模拟消费者总是选最便宜 | 画像价格敏感度与情境不匹配 | 检查画像收入与价格水平的对应关系 |
| 所有模拟消费者选择一致 | 画像多样性不足或情境过于具体 | 增加画像多样性，或放宽情境约束 |
| 选择集出现不合理组合 | 禁止组合设置不完整 | 补充 prohibited_combinations |
| 模型估计不收敛 | 选择集数量不足或属性过多 | 增加选择集数量或减少属性 |
| 模拟消费者"理性过头" | Prompt缺乏矛盾张力引导 | 在Prompt中强调"不要完美理性" |
| 不同画像结果差异不大 | 水平范围未根据画像调整 | 启用 persona_adaptation.level_adjustment |

---

*本文档与以下文件配套使用：*
- `01-CBC系统架构与解决方案.md`（整体方案）
- `02-CBC问卷生成输入规范.md`（输入字段定义）
- `03-CBC实验设计算法说明.md`（D-optimal等算法实现）
