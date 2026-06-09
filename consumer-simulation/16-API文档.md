# API文档

> **版本**：v1.0  
> **定位**：消费者模拟系统对外暴露的 RESTful API 接口规范  
> **使用说明**：前端界面、第三方系统集成、自动化脚本调用时参考

---

## 一、API设计原则

1. **RESTful风格**：使用标准 HTTP 方法（GET/POST/PUT/DELETE）
2. **JSON格式**：请求和响应统一使用 JSON
3. **版本控制**：URL 中包含版本号 `/api/v1/`
4. **分页**：列表接口支持 `page` 和 `page_size`
5. **幂等性**：生成类接口使用 `Idempotency-Key` 防止重复提交
6. **异步处理**：耗时操作（批量生成）返回任务ID，通过轮询查询结果

---

## 二、基础信息

### 2.1 Base URL

```
生产环境：https://api.consumer-sim.example.com/api/v1
测试环境：https://api-staging.consumer-sim.example.com/api/v1
```

### 2.2 认证方式

```
Header: Authorization: Bearer {api_key}
```

API Key 在管理后台创建，支持按项目/环境隔离。

### 2.3 通用响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100
  },
  "request_id": "req_xxx"
}
```

### 2.4 通用HTTP状态码

| 状态码 | 含义 | 说明 |
|--------|------|------|
| 200 | OK | 请求成功 |
| 201 | Created | 资源创建成功 |
| 202 | Accepted | 异步任务已接受 |
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 认证失败 |
| 403 | Forbidden | 权限不足 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如重复提交） |
| 422 | Unprocessable Entity | 业务逻辑校验失败 |
| 429 | Too Many Requests | 请求过于频繁 |
| 500 | Internal Server Error | 服务器内部错误 |

---

## 三、核心API端点

### 3.1 画像管理

#### 3.1.1 生成画像（批量）

```http
POST /api/v1/personas/batch
```

**请求体**：

```json
{
  "count": 5,
  "scenario": "skincare-new-product",
  "diversity": {
    "min_age_span": 20,
    "gender_balance": true,
    "city_tiers": ["一线", "新一线", "二线"]
  },
  "quality_gate": {
    "min_authenticity_score": 9,
    "max_retry": 3,
    "human_review_threshold": 7
  },
  "callback_url": "https://your-app.example.com/webhook/persona"
}
```

**响应**：

```json
{
  "code": 202,
  "message": "Batch task accepted",
  "data": {
    "task_id": "task_20250608_001",
    "status": "PENDING",
    "estimated_seconds": 120
  },
  "request_id": "req_abc123"
}
```

#### 3.1.2 查询任务状态

```http
GET /api/v1/tasks/{task_id}
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "task_20250608_001",
    "type": "BATCH_PERSONA",
    "status": "COMPLETED",
    "progress": {
      "total": 5,
      "completed": 5,
      "failed": 0,
      "pending_human_review": 0
    },
    "result": {
      "persona_ids": ["persona-001", "persona-002", ...],
      "report_url": "https://.../reports/task_20250608_001.md"
    },
    "created_at": "2026-06-08T14:00:00Z",
    "completed_at": "2026-06-08T14:02:30Z"
  }
}
```

#### 3.1.3 获取画像详情

```http
GET /api/v1/personas/{persona_id}
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "persona_id": "persona-001",
    "version": "1.2.0",
    "status": "PUBLISHED",
    "profile": {
      "layer1_demographics": { ... },
      "layer2_behavior": { ... },
      "layer3_psychology": { ... },
      "layer4_narrative": { ... }
    },
    "metadata": {
      "authenticity_score": 10.5,
      "created_at": "2026-06-01T10:00:00Z",
      "simulation_count": 45
    }
  }
}
```

#### 3.1.4 搜索画像

```http
GET /api/v1/personas/search
```

**查询参数**：

```
?age_group=25-34
&gender=女
&city_tier=新一线
&price_sensitivity=理性比价
&q=焦虑
&sort_by=authenticity_score
&sort_order=desc
&page=1
&page_size=20
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "persona_id": "persona-001",
        "summary": "28岁女，产品经理，新一线...",
        "authenticity_score": 10.5,
        "tags": ["25-34", "女", "新一线", "理性比价"]
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 156
    }
  }
}
```

#### 3.1.5 更新画像状态

```http
PUT /api/v1/personas/{persona_id}/status
```

**请求体**：

```json
{
  "status": "PUBLISHED",
  "reason": "已通过审校，投入使用"
}
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "persona_id": "persona-001",
    "old_status": "REVIEWED",
    "new_status": "PUBLISHED",
    "updated_at": "2026-06-08T15:00:00Z"
  }
}
```

---

### 3.2 模拟执行

#### 3.2.1 执行单条模拟

```http
POST /api/v1/simulations
```

**请求体**：

```json
{
  "persona_id": "persona-001",
  "scenario": {
    "time": "周三晚上11:30",
    "location": "家中",
    "emotion": "疲惫",
    "trigger": "刷到精华油广告",
    "cognitive_load": "低"
  },
  "task": {
    "type": "purchase_decision",
    "product": {
      "name": "植颜精华油",
      "price": 299,
      "selling_points": [
        "以油养肤，熬夜急救",
        "8种天然植物精油",
        "限量首发1000瓶"
      ]
    }
  },
  "output_options": {
    "include_attention": true,
    "include_cognitive_load": true,
    "include_information_gap": false
  }
}
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "simulation_id": "sim_20250608_001",
    "persona_id": "persona-001",
    "basic_outputs": {
      "first_person_response": "又是这种…'熬夜急救'。讲真我第一眼是有点心动的...",
      "emotional_state": {
        "dominant": "焦虑",
        "intensity": 7,
        "trigger_source": "看到'限量1000瓶'",
        "trajectory": "疲惫→心动→焦虑→犹豫"
      },
      "action_taken": {
        "immediate": "手指停在详情页",
        "short_term": "查看已售数量",
        "final_decision": "锁单未付款",
        "confidence": "低"
      },
      "decision_rationale": {
        "surface": "博主推荐，限量怕错过",
        "deep": "今天被领导骂了，需要补偿自己",
        "key_factors": ["KOL依赖", "FOMO", "情绪低落"],
        "hesitation_reason": "299不便宜，花呗还欠着"
      }
    },
    "enhanced_outputs": {
      "attention_allocation": {
        "first_noticed": "发光肌对比图",
        "ignored": "成分表详情"
      },
      "cognitive_load": {
        "initial": "低",
        "peak_moment": "看到价格时",
        "overload_behavior": "依赖默认选项"
      }
    },
    "metadata": {
      "authenticity_score": 10.5,
      "duration_seconds": 8,
      "created_at": "2026-06-08T14:30:00Z"
    }
  }
}
```

#### 3.2.2 批量执行模拟

```http
POST /api/v1/simulations/batch
```

**请求体**：

```json
{
  "persona_ids": ["persona-001", "persona-002", "persona-003"],
  "scenarios": [
    {
      "name": "skincare-new-product",
      "time": "周三晚上11:30",
      "emotion": "疲惫",
      "product": { ... }
    },
    {
      "name": "skincare-weekend",
      "time": "周六下午2点",
      "emotion": "平稳",
      "product": { ... }
    }
  ],
  "quality_gate": {
    "min_authenticity_score": 9
  }
}
```

**响应**：

```json
{
  "code": 202,
  "message": "Batch simulation task accepted",
  "data": {
    "task_id": "task_sim_20250608_001",
    "status": "PENDING",
    "estimated_simulations": 6
  }
}
```

#### 3.2.3 查询模拟记录

```http
GET /api/v1/simulations/{simulation_id}
```

#### 3.2.4 按画像查询模拟历史

```http
GET /api/v1/personas/{persona_id}/simulations?page=1&page_size=20
```

#### 3.2.5 按场景查询模拟记录

```http
GET /api/v1/scenarios/{scenario_name}/simulations?page=1&page_size=20
```

---

### 3.3 批次报告

#### 3.3.1 获取批次报告

```http
GET /api/v1/batches/{task_id}/report
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "task_id": "task_20250608_001",
    "summary": {
      "total": 5,
      "passed": 4,
      "pending_human_review": 1,
      "average_authenticity_score": 10.2
    },
    "diversity_metrics": {
      "age_entropy": 0.85,
      "gender_ratio": "3:2",
      "city_tier_coverage": ["一线", "新一线", "二线"]
    },
    "bias_scan": {
      "stereotype_flags": 1,
      "high_risk_combinations": ["退休+节俭+被诈骗"]
    },
    "personas": [
      {
        "persona_id": "persona-001",
        "score": 10.5,
        "status": "PASSED"
      }
    ],
    "recommendations": [
      "增加二线城市画像",
      "注意避免老年人刻板印象"
    ]
  }
}
```

---

### 3.4 人工审核

#### 3.4.1 获取待审核列表

```http
GET /api/v1/reviews/pending?page=1&page_size=20
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "review_id": "rev_001",
        "type": "PROFILE",
        "content_id": "persona-003",
        "priority": "HIGH",
        "reason": "连续3次FIX未通过",
        "submitted_at": "2026-06-08T14:30:00Z"
      }
    ],
    "pagination": {
      "total": 12
    }
  }
}
```

#### 3.4.2 提交审核结果

```http
POST /api/v1/reviews/{review_id}/submit
```

**请求体**：

```json
{
  "verdict": "APPROVED",
  "comments": "虽然有轻微刻板印象，但在合理范围内，整体真实感足够",
  "modified_fields": {
    "layer3.psychology.tension_combination.narrative_explanation": "补充了更详细的解释"
  }
}
```

**verdict 可选值**：`APPROVED` | `REJECTED` | `NEEDS_FIX`

---

### 3.5 系统管理

#### 3.5.1 健康检查

```http
GET /api/v1/health
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "healthy",
    "timestamp": "2026-06-08T14:30:00Z",
    "version": "1.0.0"
  }
}
```

#### 3.5.2 就绪检查

```http
GET /api/v1/ready
```

**响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ready",
    "checks": {
      "redis": "ok",
      "mongodb": "ok",
      "kafka": "ok"
    }
  }
}
```

#### 3.5.3 Prometheus指标

```http
GET /api/v1/metrics
```

返回 Prometheus 格式的指标数据。

---

## 四、错误码详解

| 错误码 | 名称 | HTTP状态 | 说明 | 处理建议 |
|--------|------|---------|------|---------|
| `0` | `SUCCESS` | 200 | 成功 | — |
| `E001` | `INVALID_REQUEST` | 400 | 请求格式不合法 | 检查请求体必填字段 |
| `E002` | `SEED_GENERATION_FAILED` | 422 | 种子生成失败 | 调整场景参数或约束条件 |
| `E003` | `GENERATION_TIMEOUT` | 504 | LLM生成超时 | 稍后重试，或降低生成复杂度 |
| `E004` | `GENERATION_ERROR` | 500 | LLM API错误 | 联系运维检查LLM服务状态 |
| `E005` | `SCHEMA_VIOLATION` | 422 | 输出结构校验失败 | 检查LLM输出格式是否异常 |
| `E006` | `LOGIC_VIOLATION` | 422 | 逻辑校验失败 | 进入FeedbackLoop自动修正 |
| `E007` | `BIAS_DETECTED` | 422 | 偏见检测高危 | 修改画像描述，打破刻板印象 |
| `E008` | `SCORE_TOO_LOW` | 422 | 真实感评分过低 | 重新生成或人工介入 |
| `E009` | `MAX_RETRIES_EXCEEDED` | 422 | 超过最大重试次数 | 已转人工审核 |
| `E010` | `STORAGE_ERROR` | 500 | 存储写入失败 | 联系运维检查数据库状态 |
| `E011` | `HUMAN_REVIEW_TIMEOUT` | 500 | 人工审核超时 | 系统自动按最佳努力处理 |
| `E100` | `UNAUTHORIZED` | 401 | 认证失败 | 检查API Key是否有效 |
| `E101` | `FORBIDDEN` | 403 | 权限不足 | 检查API Key权限范围 |
| `E102` | `RATE_LIMITED` | 429 | 请求过于频繁 | 降低请求频率或申请提高配额 |
| `E103` | `RESOURCE_NOT_FOUND` | 404 | 资源不存在 | 检查persona_id/simulation_id是否正确 |
| `E104` | `DUPLICATE_REQUEST` | 409 | 重复请求 | 使用新的Idempotency-Key |

---

## 五、调用示例

### 5.1 Python示例

```python
import requests

API_BASE = "https://api.consumer-sim.example.com/api/v1"
API_KEY = "your_api_key"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 1. 批量生成画像
response = requests.post(
    f"{API_BASE}/personas/batch",
    headers=headers,
    json={
        "count": 3,
        "scenario": "skincare-new-product",
        "quality_gate": {
            "min_authenticity_score": 9
        }
    }
)

task_id = response.json()["data"]["task_id"]
print(f"Task created: {task_id}")

# 2. 轮询任务状态
import time
while True:
    resp = requests.get(f"{API_BASE}/tasks/{task_id}", headers=headers)
    status = resp.json()["data"]["status"]
    print(f"Status: {status}")
    
    if status in ["COMPLETED", "FAILED"]:
        break
    time.sleep(5)

# 3. 获取生成的画像
for persona_id in resp.json()["data"]["result"]["persona_ids"]:
    persona_resp = requests.get(
        f"{API_BASE}/personas/{persona_id}",
        headers=headers
    )
    print(persona_resp.json()["data"]["profile"]["layer1_demographics"])

# 4. 执行模拟
sim_resp = requests.post(
    f"{API_BASE}/simulations",
    headers=headers,
    json={
        "persona_id": persona_id,
        "scenario": {
            "time": "周三晚上11:30",
            "location": "家中",
            "emotion": "疲惫",
            "trigger": "刷到精华油广告",
            "cognitive_load": "低"
        },
        "task": {
            "type": "purchase_decision",
            "product": {
                "name": "植颜精华油",
                "price": 299,
                "selling_points": ["以油养肤，熬夜急救"]
            }
        }
    }
)

print(sim_resp.json()["data"]["basic_outputs"]["first_person_response"])
```

### 5.2 cURL示例

```bash
# 生成画像
curl -X POST https://api.consumer-sim.example.com/api/v1/personas/batch \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "count": 2,
    "scenario": "skincare-new-product"
  }'

# 查询任务
curl https://api.consumer-sim.example.com/api/v1/tasks/task_20250608_001 \
  -H "Authorization: Bearer your_api_key"

# 执行模拟
curl -X POST https://api.consumer-sim.example.com/api/v1/simulations \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "persona-001",
    "scenario": {
      "time": "周三晚上11:30",
      "emotion": "疲惫",
      "trigger": "刷到精华油广告"
    },
    "task": {
      "type": "purchase_decision",
      "product": {
        "name": "植颜精华油",
        "price": 299
      }
    }
  }'
```

### 5.3 JavaScript示例

```javascript
const axios = require('axios');

const client = axios.create({
  baseURL: 'https://api.consumer-sim.example.com/api/v1',
  headers: {
    'Authorization': 'Bearer your_api_key',
    'Content-Type': 'application/json'
  }
});

async function generateAndSimulate() {
  // 生成画像
  const batchResp = await client.post('/personas/batch', {
    count: 1,
    scenario: 'skincare-new-product'
  });
  
  const taskId = batchResp.data.data.task_id;
  
  // 轮询等待完成
  let task;
  do {
    await new Promise(r => setTimeout(r, 5000));
    const resp = await client.get(`/tasks/${taskId}`);
    task = resp.data.data;
  } while (task.status === 'IN_PROGRESS');
  
  const personaId = task.result.persona_ids[0];
  
  // 执行模拟
  const simResp = await client.post('/simulations', {
    persona_id: personaId,
    scenario: {
      time: '周三晚上11:30',
      emotion: '疲惫',
      trigger: '刷到精华油广告',
      cognitive_load: '低'
    },
    task: {
      type: 'purchase_decision',
      product: { name: '植颜精华油', price: 299 }
    }
  });
  
  console.log(simResp.data.data.basic_outputs.first_person_response);
}

generateAndSimulate();
```

---

## 六、速率限制

| 接口类型 | 限制 | 说明 |
|---------|------|------|
| 读取类接口（GET） | 1000次/分钟 | 按API Key计数 |
| 写入类接口（POST/PUT） | 100次/分钟 | 按API Key计数 |
| LLM生成接口 | 50次/分钟 | 全局限制 |
| 批量任务提交 | 10次/分钟 | 防止队列堆积 |

**响应头中的速率限制信息**：

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1717849200
```

---

## 七、Webhook事件

系统支持通过 Webhook 推送任务完成事件。

### 7.1 订阅Webhook

在管理后台配置 `callback_url`，系统会在任务完成时推送：

```json
{
  "event_type": "TASK_COMPLETED",
  "task_id": "task_20250608_001",
  "task_type": "BATCH_PERSONA",
  "status": "COMPLETED",
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 0
  },
  "result_url": "https://api.consumer-sim.example.com/api/v1/batches/task_20250608_001/report",
  "timestamp": "2026-06-08T14:02:30Z"
}
```

### 7.2 事件类型

| 事件类型 | 说明 |
|---------|------|
| `TASK_COMPLETED` | 任务完成 |
| `TASK_FAILED` | 任务失败 |
| `HUMAN_REVIEW_REQUIRED` | 需要人工审核 |
| `PERSONA_PUBLISHED` | 画像已发布 |
| `SIMULATION_COMPLETED` | 单条模拟完成 |

### 7.3 Webhook签名验证

```http
X-Webhook-Signature: sha256={hmac_signature}
```

使用你的 API Secret 验证签名：

```python
import hmac
import hashlib

expected = hmac.new(
    api_secret.encode(),
    request_body,
    hashlib.sha256
).hexdigest()

assert hmac.compare_digest(expected, signature)
```

---

*本文档与以下文件配套使用：*
- [`13-实现参考与接口定义.md`](./13-实现参考与接口定义.md)（后端接口的实现细节）
- [`15-运维手册.md`](./15-运维手册.md)（API服务的部署与监控）
- [`14-测试规范.md`](./14-测试规范.md)（API的测试用例）
