# CBC 数据分析系统 — API接口设计

> **版本**：v1.0
> **定位**：定义联合分析统计建模的API接口规范，供Agent调用和前端集成
> **负责人**：小数（数据/建模科学家）+ 小端（后端/工具集成工程师）
> **前置文档**：`01-CBC数据分析系统架构.md`、`03-模型实现指南.md`、`docs/数据字典.md`

---

## 一、API总览

### 1.1 接口清单

| 方法 | 路径 | 功能 | 异步 |
|------|------|------|------|
| POST | `/studies/{study_id}/analyze` | 执行联合分析（HB/MNL） | 是 |
| GET | `/studies/{study_id}/analysis/{analysis_id}` | 获取分析结果 | 否 |
| GET | `/studies/{study_id}/analysis/{analysis_id}/convergence` | 获取收敛诊断 | 否 |
| GET | `/studies/{study_id}/analysis/{analysis_id}/importance` | 获取属性重要性 | 否 |
| GET | `/studies/{study_id}/analysis/{analysis_id}/wtp` | 获取支付意愿 | 否 |
| POST | `/studies/{study_id}/analysis/{analysis_id}/simulate-market` | 市场模拟 | 否 |
| GET | `/studies/{study_id}/analysis/{analysis_id}/segment-comparison` | 群体差异检验 | 否 |

### 1.2 数据流

```
问卷子系统 ──→ CBCRawDataset ──→ 分析API ──→ AnalysisResult
     │                                    │
     └── 实验设计参数 ────────────────────┘
```

---

## 二、核心接口详解

### 2.1 执行联合分析

**POST** `/studies/{study_id}/analyze`

触发统计模型拟合，返回任务ID供轮询。

**Request Body**:

```json
{
  "model_type": "hb",
  "n_draws": 1000,
  "n_tune": 1000,
  "n_chains": 4,
  "target_accept": 0.9,
  "prior_config": {
    "mu_mu": 0,
    "mu_sigma": 10
  }
}
```

**Response** (202 Accepted):

```json
{
  "analysis_id": "ar-dishwasher-202506-001",
  "study_id": "dishwasher-202506",
  "status": "PENDING",
  "model_type": "hb",
  "queued_at": "2026-06-10T14:30:00Z",
  "estimated_duration_seconds": 300
}
```

**Status Flow**:

```
PENDING → RUNNING → COMPLETED
              ↓
           FAILED (返回错误详情)
```

### 2.2 获取分析结果

**GET** `/studies/{study_id}/analysis/{analysis_id}`

**Response** (200 OK, status=COMPLETED):

```json
{
  "analysis_id": "ar-dishwasher-202506-001",
  "study_id": "dishwasher-202506",
  "status": "COMPLETED",
  "model_type": "hb",
  "convergence": {
    "rhat_max": 1.04,
    "ess_min": 1200,
    "converged": true,
    "reliable_ess": true
  },
  "population_params": {
    "mu": {
      "price": -0.0035,
      "capacity_0": 0.52,
      "capacity_1": 0.31,
      "installation_0": 0.28,
      "installation_1": -0.15,
      "features_0": 0.45,
      "features_1": 0.22,
      "brand_0": 0.38,
      "brand_1": 0.15,
      "brand_2": -0.12,
      "energy_0": 0.18,
      "energy_1": 0.08
    },
    "sigma": {
      "price": 0.0012,
      "capacity_0": 0.45,
      ...
    }
  },
  "individual_utilities": {
    "persona-dw-001": {
      "price": -0.0042,
      "capacity_0": 0.65,
      ...
    },
    ...
  },
  "importance": {
    "price": 0.425,
    "capacity": 0.198,
    "installation": 0.152,
    "features": 0.128,
    "brand": 0.068,
    "energy": 0.029
  },
  "wtp": {
    "capacity": {
      "10套 vs 6套": 850,
      "13套 vs 6套": 1200
    },
    "installation": {
      "嵌入式 vs 台式": 600,
      "水槽式 vs 台式": 400
    },
    ...
  },
  "processing_time_seconds": 285,
  "completed_at": "2026-06-10T14:35:00Z"
}
```

### 2.3 获取收敛诊断

**GET** `/studies/{study_id}/analysis/{analysis_id}/convergence`

**Response**:

```json
{
  "rhat_max": 1.04,
  "rhat_by_param": {
    "mu[price]": 1.01,
    "mu[capacity_0]": 1.02,
    ...
  },
  "ess_bulk_min": 1200,
  "ess_tail_min": 980,
  "ess_by_param": {
    "mu[price]": 1500,
    ...
  },
  "converged": true,
  "reliable_ess": true,
  "divergences": 0,
  "tree_depth_max": 10
}
```

### 2.4 获取属性重要性

**GET** `/studies/{study_id}/analysis/{analysis_id}/importance`

**Response**:

```json
{
  "overall": {
    "price": {"mean": 0.425, "std": 0.083, "ci_95": [0.382, 0.468]},
    "capacity": {"mean": 0.198, "std": 0.052, "ci_95": [0.156, 0.240]},
    "installation": {"mean": 0.152, "std": 0.041, "ci_95": [0.118, 0.186]},
    "features": {"mean": 0.128, "std": 0.038, "ci_95": [0.096, 0.160]},
    "brand": {"mean": 0.068, "std": 0.029, "ci_95": [0.045, 0.091]},
    "energy": {"mean": 0.029, "std": 0.015, "ci_95": [0.018, 0.040]}
  },
  "by_segment": {
    "精致白领": {"price": 0.38, "capacity": 0.22, ...},
    "新手宝妈": {"price": 0.35, "capacity": 0.25, ...},
    "Z世代租客": {"price": 0.55, "capacity": 0.15, ...}
  }
}
```

### 2.5 获取支付意愿

**GET** `/studies/{study_id}/analysis/{analysis_id}/wtp`

**Response**:

```json
{
  "wtp_values": {
    "capacity": {
      "comparisons": [
        {
          "from_level": "6套",
          "to_level": "10套",
          "wtp_mean": 850,
          "wtp_median": 820,
          "wtp_std": 320,
          "ci_95": [450, 1250],
          "n_valid": 238
        },
        {
          "from_level": "6套",
          "to_level": "13套",
          "wtp_mean": 1200,
          "wtp_median": 1150,
          "wtp_std": 450,
          "ci_95": [650, 1750],
          "n_valid": 238
        }
      ]
    },
    "installation": {
      "comparisons": [...]
    }
  },
  "price_coefficient_summary": {
    "mean": -0.0035,
    "median": -0.0033,
    "std": 0.0012,
    "negative_rate": 1.0,
    "n_positive_outliers": 0
  }
}
```

### 2.6 市场模拟

**POST** `/studies/{study_id}/analysis/{analysis_id}/simulate-market`

**Request Body**:

```json
{
  "scenarios": [
    {
      "name": "我的产品",
      "price": 3999,
      "capacity": "10套",
      "installation": "嵌入式",
      "features": "智能",
      "brand": "美的",
      "energy": "一级"
    },
    {
      "name": "竞品A",
      "price": 4999,
      "capacity": "13套",
      "installation": "嵌入式",
      "features": "全能",
      "brand": "西门子",
      "energy": "超一级"
    },
    {
      "name": "竞品B",
      "price": 2999,
      "capacity": "6套",
      "installation": "台式",
      "features": "基础",
      "brand": "小米",
      "energy": "二级"
    }
  ],
  "rule": "logit",
  "include_none": true,
  "segment_filter": null
}
```

**Response**:

```json
{
  "scenarios": [
    {"name": "我的产品", "predicted_share": 0.385, "share_ci_95": [0.342, 0.428]},
    {"name": "竞品A", "predicted_share": 0.312, "share_ci_95": [0.273, 0.351]},
    {"name": "竞品B", "predicted_share": 0.198, "share_ci_95": [0.165, 0.231]},
    {"name": "none", "predicted_share": 0.105, "share_ci_95": [0.082, 0.128]}
  ],
  "by_segment": {
    "精致白领": [
      {"name": "我的产品", "predicted_share": 0.42},
      ...
    ]
  }
}
```

### 2.7 群体差异检验

**GET** `/studies/{study_id}/analysis/{analysis_id}/segment-comparison`

**Query Parameters**:
- `segment_a`: 群体A名称
- `segment_b`: 群体B名称
- `test_type`: `hotelling` | `welch` | `permutation`

**Response**:

```json
{
  "segment_a": "精致白领",
  "segment_b": "Z世代租客",
  "n_a": 80,
  "n_b": 80,
  "overall_test": {
    "method": "Hotelling's T²",
    "statistic": 45.23,
    "p_value": 0.0001,
    "significant": true
  },
  "per_attribute": [
    {
      "attribute": "price",
      "method": "Welch's t-test",
      "t_statistic": -3.52,
      "p_value": 0.0006,
      "significant": true,
      "cohens_d": -0.56,
      "effect_size": "medium",
      "mean_a": -0.0028,
      "mean_b": -0.0045
    },
    {
      "attribute": "brand",
      "method": "Welch's t-test",
      "t_statistic": 1.23,
      "p_value": 0.22,
      "significant": false,
      "cohens_d": 0.18,
      "effect_size": "negligible",
      "mean_a": 0.42,
      "mean_b": 0.38
    }
  ],
  "interpretation": "两群体在价格敏感度上存在显著差异（p<0.001, d=-0.56），Z世代租客对价格更敏感。品牌偏好无显著差异。"
}
```

---

## 三、错误处理

### 3.1 标准错误格式

```json
{
  "error_code": "ANALYSIS_001",
  "message": "模型未收敛",
  "detail": {
    "rhat_max": 1.35,
    "suggestion": "增加n_tune至2000或检查数据质量"
  }
}
```

### 3.2 错误码表

| 错误码 | 场景 | HTTP状态 |
|--------|------|---------|
| ANALYSIS_001 | 模型未收敛 | 422 |
| ANALYSIS_002 | 样本量不足 | 422 |
| ANALYSIS_003 | 价格系数为正 | 422 |
| ANALYSIS_004 | 数据格式错误 | 400 |
| ANALYSIS_005 | 分析任务不存在 | 404 |
| ANALYSIS_006 | 分析仍在运行中 | 409 |

---

## 四、与上游系统的集成

### 4.1 从问卷子系统获取数据

```python
# 分析服务内部调用问卷子系统的export接口
dataset = await questionnaire_client.export_dataset(study_id)
# 返回 CBCRawDataset 格式
```

### 4.2 与数据字典的映射

| API字段 | 数据字典实体 | 字段 |
|---------|-------------|------|
| `analysis_id` | AnalysisResult | `result_id` |
| `convergence` | AnalysisResult | `convergence` |
| `population_params` | AnalysisResult | `population_params` |
| `individual_utilities` | AnalysisResult | `individual_utilities` |
| `importance` | AnalysisResult | `importance` |
| `wtp` | AnalysisResult | `wtp` |

---

## 五、性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| MNL拟合 | < 5秒 | 1000人样本 |
| HB拟合 | < 5分钟 | 240人×12题，4链×1000采样 |
| 市场模拟 | < 1秒 | 5个产品情景 |
| 群体差异检验 | < 2秒 | 两组各80人 |
| API响应（GET） | < 200ms | 已完成的分析结果 |

---

*本文档由小数和小端维护，API变更需双方确认。*
