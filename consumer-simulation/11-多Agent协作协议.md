# 多Agent协作协议

> **版本**：v1.0  
> **定位**：定义消费者模拟系统中多个AI Agent之间的协作流程、通信格式与状态管理机制  
> **使用说明**：工程化部署时，按此协议实现Agent间的消息传递和流程编排

---

## 一、Agent角色定义

系统中存在4类核心Agent，各司其职：

| Agent | 代号 | 职责 | 输入 | 输出 |
|-------|------|------|------|------|
| **画像生成Agent** | `GEN` | 基于种子生成消费者画像 | 种子 + 标签体系 + Prompt模板 | 结构化画像（JSON） |
| **情境模拟Agent** | `SIM` | 基于画像和情境模拟消费者行为 | 画像 + 情境 + 任务 | 模拟记录（JSON） |
| **审校Agent** | `REV` | 校验画像/模拟输出的质量 | 待审内容 + 校验规则 | 审校报告（通过/问题列表/分数） |
| **反馈修正Agent** | `FIX` | 根据审校意见生成修改指令 | 审校报告 + 原始内容 | 修改指令（精确到字段） |

---

## 二、消息格式协议

所有Agent间通信采用统一的消息信封格式：

```json
{
  "message_id": "msg_{uuid}",
  "timestamp": "2026-06-08T14:30:00Z",
  "sender": "GEN",
  "receiver": "REV",
  "message_type": "PROFILE_GENERATED",
  "correlation_id": "task_{batch_id}_{seq}",
  "payload": {},
  "metadata": {
    "retry_count": 0,
    "ttl_seconds": 300,
    "priority": "normal"
  }
}
```

### 2.1 消息类型（MessageType）

```
# 画像生成流程
PROFILE_GENERATED      → GEN → REV    # 画像生成完成，提交审校
PROFILE_REVIEWED       → REV → GEN    # 画像审校完成
PROFILE_FIX_REQUEST    → REV → FIX    # 画像需要修正
PROFILE_FIX_APPLIED    → FIX → GEN    # 修正指令已应用
PROFILE_ACCEPTED       → REV → ORCH   # 画像审校通过

# 情境模拟流程
SIMULATION_GENERATED   → SIM → REV    # 模拟记录生成完成
SIMULATION_REVIEWED    → REV → SIM    # 模拟记录审校完成
SIMULATION_FIX_REQUEST → REV → FIX    # 模拟记录需要修正
SIMULATION_FIX_APPLIED → FIX → SIM    # 修正指令已应用
SIMULATION_ACCEPTED    → REV → ORCH   # 模拟记录审校通过

# 异常流程
AGENT_TIMEOUT          → ANY → ORCH   # Agent执行超时
AGENT_ERROR            → ANY → ORCH   # Agent执行错误
HUMAN_REVIEW_REQUIRED  → REV → ORCH   # 需要人工介入
```

### 2.2 各消息类型的Payload定义

#### PROFILE_GENERATED

```json
{
  "persona_id": "persona-001",
  "layer1_demographics": {},
  "layer2_behavior": {},
  "layer3_psychology": {},
  "layer4_narrative": {},
  "language_samples": [],
  "raw_output": "{原始LLM输出}"
}
```

#### PROFILE_REVIEWED

```json
{
  "persona_id": "persona-001",
  "verdict": "PASS",  // PASS | NEEDS_FIX | REJECT
  "score": 10.5,
  "issues": [
    {
      "rule_id": "RULE-001",
      "severity": "MAJOR",  // CRITICAL | MAJOR | MINOR
      "field_path": "layer3.psychology.tension_combination",
      "description": "矛盾标签缺少叙事解释",
      "expected": "至少50字的内心独白式解释"
    }
  ],
  "recommendations": ["补充矛盾张力的心理解释"]
}
```

#### PROFILE_FIX_REQUEST

```json
{
  "persona_id": "persona-001",
  "original_content": "{原始画像JSON}",
  "issues": [
    {
      "rule_id": "RULE-001",
      "field_path": "layer3.psychology.tension_combination.narrative_explanation",
      "description": "矛盾标签缺少叙事解释",
      "context": "高收入+极简主义+对促销高度敏感"
    }
  ],
  "preserve_constraints": [
    "seed_combination",
    "tension_labels",
    "passed_fields"
  ]
}
```

#### PROFILE_FIX_APPLIED

```json
{
  "persona_id": "persona-001",
  "modified_fields": [
    {
      "field_path": "layer3.psychology.tension_combination.narrative_explanation",
      "old_value": "",
      "new_value": "成长于节俭家庭..."
    }
  ],
  "preserved_fields": ["seed", "tension_labels"],
  "fix_strategy": "targeted"  // targeted | full_regeneration
}
```

#### SIMULATION_GENERATED

```json
{
  "simulation_id": "sim_20250608_001",
  "persona_id": "persona-001",
  "scenario": "skincare-new-product",
  "basic_outputs": {
    "first_person_response": "...",
    "emotional_state": {},
    "action_taken": {},
    "decision_rationale": {}
  },
  "enhanced_outputs": {},
  "metadata": {
    "duration_seconds": 332,
    "turn_count": 12
  }
}
```

---

## 三、协作流程

### 3.1 画像生成流程（GEN → REV → FIX 循环）

```
┌─────────┐    PROFILE_GENERATED     ┌─────────┐
│   GEN   │ ────────────────────────→│   REV   │
│ (生成)  │                          │ (审校)  │
└─────────┘                          └────┬────┘
     ↑                                    │
     │    PROFILE_FIX_APPLIED            │ PROFILE_REVIEWED
     │    (修正后重新提交)                │    verdict=PASS
     │                                    │
     │    ┌─────────┐                    │
     └────│   FIX   │←───────────────────┘
          │ (修正)  │  PROFILE_FIX_REQUEST
          └────┬────┘
               │
               └─→ 审校不通过且重试<3次
               └─→ 审校不通过且重试≥3次 → HUMAN_REVIEW_REQUIRED
```

**流程规则**：
1. GEN 生成画像后，必须提交 REV 审校
2. REV 返回 `PASS` → 流程结束，画像入库
3. REV 返回 `NEEDS_FIX` → 发送 FIX Request 给 FIX Agent
4. FIX 生成修改指令 → 回传 GEN 执行修正
5. GEN 修正后重新提交 REV 审校
6. 最多重试 3 次，超过则转人工审核
7. REV 返回 `REJECT` → 直接转人工审核

### 3.2 情境模拟流程（SIM → REV → FIX 循环）

```
┌─────────┐    SIMULATION_GENERATED   ┌─────────┐
│   SIM   │ ────────────────────────→│   REV   │
│ (模拟)  │                          │ (审校)  │
└─────────┘                          └────┬────┘
     ↑                                    │
     │    SIMULATION_FIX_APPLIED         │ SIMULATION_REVIEWED
     │    (修正后重新提交)                │    verdict=PASS
     │                                    │
     │    ┌─────────┐                    │
     └────│   FIX   │←───────────────────┘
          │ (修正)  │  SIMULATION_FIX_REQUEST
          └────┬────┘
               │
               └─→ 审校不通过且重试<3次
               └─→ 审校不通过且重试≥3次 → HUMAN_REVIEW_REQUIRED
```

**与画像流程的区别**：
- SIM 的修正通常是"局部重写"而非"结构修改"
- SIM 的审校更关注"真实感"而非"结构完整性"
- SIM 可以接受"不完美但真实"的输出（分数 9+ 即可通过）

### 3.3 批量并行流程

```
【批量生成画像】

ORCH (编排器)
  │
  ├──→ GEN-1 生成画像A ──→ REV-1 审校 ──→ [PASS/NEEDS_FIX]
  ├──→ GEN-2 生成画像B ──→ REV-2 审校 ──→ [PASS/NEEDS_FIX]
  ├──→ GEN-3 生成画像C ──→ REV-3 审校 ──→ [PASS/NEEDS_FIX]
  │
  └── 等待全部完成后 ──→ 生成批次报告

【批量执行模拟】

ORCH
  │
  ├──→ SIM-1 模拟画像A场景1 ──→ REV-1 审校
  ├──→ SIM-2 模拟画像A场景2 ──→ REV-2 审校
  ├──→ SIM-3 模拟画像B场景1 ──→ REV-3 审校
  ├──→ SIM-4 模拟画像B场景2 ──→ REV-4 审校
  ├──→ SIM-5 模拟画像C场景1 ──→ REV-5 审校
  └──→ SIM-6 模拟画像C场景2 ──→ REV-6 审校
```

**并行规则**：
- 画像生成可以全并行（彼此无依赖）
- 同一画像的多个场景模拟可以并行
- 同一画像的第二轮模拟依赖第一轮的历史记忆
- 审校Agent可以独立并行（无状态）

---

## 四、状态管理

### 4.1 全局任务状态（Task State）

```json
{
  "task_id": "task_20250608_001",
  "status": "IN_PROGRESS",  // PENDING | IN_PROGRESS | COMPLETED | FAILED | HUMAN_REVIEW
  "type": "BATCH_GENERATION",  // BATCH_GENERATION | BATCH_SIMULATION
  "created_at": "2026-06-08T14:00:00Z",
  "updated_at": "2026-06-08T14:30:00Z",
  "progress": {
    "total": 5,
    "completed": 3,
    "failed": 0,
    "pending_human_review": 1,
    "in_progress": 1
  },
  "subtasks": [
    {
      "subtask_id": "st_001",
      "type": "PROFILE_GENERATION",
      "status": "COMPLETED",
      "persona_id": "persona-001",
      "agent_assignments": [
        {"agent": "GEN", "status": "COMPLETED", "output": "..."},
        {"agent": "REV", "status": "COMPLETED", "output": "..."}
      ]
    }
  ]
}
```

### 4.2 画像生命周期状态（Persona Lifecycle）

```
[CREATED] ──→ GEN 生成
    │
    ▼
[UNDER_REVIEW] ──→ REV 审校中
    │
    ├──→ [PASSED] ──→ 入库，可参与模拟
    │
    ├──→ [NEEDS_FIX] ──→ FIX 修正 ──→ [FIXED] ──→ 重新审校
    │
    └──→ [REJECTED] ──→ [HUMAN_REVIEW] ──→ [APPROVED/ARCHIVED]
```

### 4.3 模拟记录生命周期状态（Simulation Lifecycle）

```
[CREATED] ──→ SIM 生成
    │
    ▼
[UNDER_REVIEW] ──→ REV 审校中
    │
    ├──→ [PASSED] ──→ 入库，可用于分析
    │
    ├──→ [NEEDS_FIX] ──→ FIX 修正 ──→ [FIXED] ──→ 重新审校
    │
    └──→ [REJECTED] ──→ [HUMAN_REVIEW] ──→ [APPROVED/ARCHIVED]
```

---

## 五、上下文传递机制

### 5.1 画像上下文（Persona Context）

画像一旦生成并通过审校，其完整信息需要在所有后续Agent间传递：

```json
{
  "persona_context": {
    "persona_id": "persona-001",
    "version": "1.0",
    "layer1": {},  // 基础骨架
    "layer2": {},  // 行为签名
    "layer3": {},  // 心理引擎（含秘密动机）
    "layer4": {},  // 场景反应库
    "narrative": {},  // 人物小传
    "language_samples": [],  // 语言样本
    "generation_metadata": {
      "seed": {},
      "generated_at": "2026-06-08T14:00:00Z",
      "authenticity_score": 10.5
    }
  }
}
```

**传递规则**：
- SIM Agent 接收完整的 `layer1-4` + `secret_motivation`
- REV Agent 接收完整画像用于一致性校验
- FIX Agent 接收完整画像用于生成修改指令（需保留核心特征）
- 画像上下文不可修改（immutable），修正生成新版本

### 5.2 模拟历史上下文（Simulation History）

多轮模拟时，历史记录需要传递给 SIM Agent：

```json
{
  "simulation_history": [
    {
      "simulation_id": "sim_20250608_001",
      "scenario": "skincare-new-product",
      "basic_outputs": {
        "first_person_response": "...",
        "action_taken": {"final_decision": "加入购物车"}
      },
      "metadata": {
        "authenticity_score": 10.5,
        "created_at": "2026-06-08T14:30:00Z"
      }
    }
  ],
  "memory_rules": {
    "recent_purchases": ["上周买了A品牌踩雷"],
    "brand_experiences": {"XX品牌": "去年过敏拉黑"},
    "pending_decisions": ["购物车里3件风衣等降价"]
  }
}
```

**传递规则**：
- 每次新模拟前，自动附加最近 3-5 次模拟记录
- 历史记录按时间倒序排列（最新的在前）
- 超过 30 天的历史记录只保留摘要（自动压缩）

### 5.3 审校上下文（Review Context）

REV Agent 需要知道之前的审校历史，避免重复提出相同问题：

```json
{
  "review_history": [
    {
      "review_id": "rev_001",
      "timestamp": "2026-06-08T14:05:00Z",
      "verdict": "NEEDS_FIX",
      "issues": [
        {"rule_id": "RULE-001", "field": "tension_explanation", "resolved": true}
      ]
    }
  ]
}
```

---

## 六、错误处理与降级策略

### 6.1 Agent超时处理

```
超时阈值：
- GEN 生成画像：120秒
- SIM 执行模拟：60秒
- REV 审校：30秒
- FIX 生成修改指令：30秒

超时处理：
1. 第一次超时 → 重试1次（相同Agent）
2. 第二次超时 → 切换备用模型（如 Claude → GPT-4）
3. 第三次超时 → 标记任务为 FAILED，通知 ORCH
4. ORCH 决定：跳过该子任务 / 整体失败 / 转人工
```

### 6.2 Agent错误处理

| 错误类型 | 处理策略 |
|---------|---------|
| **模型API错误**（429/500/503） | 指数退避重试，最多3次 |
| **输出格式错误**（JSON解析失败） | 要求Agent重新输出，附加格式约束 |
| **内容安全拦截**（敏感内容） | 标记为 REJECTED，转人工审核 |
| **逻辑一致性错误**（自我矛盾） | 发送给 FIX Agent，要求修正矛盾点 |
| **上下文丢失**（历史记忆缺失） | 重新加载上下文，重试该步骤 |

### 6.3 审校循环死锁检测

```
死锁检测规则：
1. 如果连续两次 FIX 后的输出被 REV 标记为相同问题 → 可能进入死循环
2. 如果 FIX 后的分数连续下降 → 修正策略失效
3. 如果修正内容哈希值连续两次相同 → FIX 没有实际修改

处理策略：
- 检测到死锁 → 强制转人工审核
- 记录死锁模式 → 用于优化 FIX Agent 的 Prompt
```

---

## 七、人机协作接口

### 7.1 人工审核触发条件

```
自动触发人工审核：
1. REV 返回 REJECT（审校不通过）
2. 连续 3 次 FIX 后仍未通过
3. Bias Detector 标记为高危（刻板印象严重）
4. Authenticity Score < 7分
5. 系统检测到死锁

人工审核输入：
- 原始输出内容
- REV 的审校报告
- FIX 的历史修改记录
- 生成所用的 Prompt 和参数

人工审核输出：
- verdict: APPROVED | REJECTED | NEEDS_FIX
- comments: 人工审校意见
- action: 如果 NEEDS_FIX，提供具体修改建议
```

### 7.2 人工审核队列与 SLA

**优先级定义**：

| 优先级 | 触发条件 | 响应 SLA | 超时处理 |
|--------|---------|---------|---------|
| HIGH | 偏见检测高危 / authenticity_score < 7 | 2 小时 | 升级至小伦+小P，超时自动拒绝 |
| MEDIUM | 连续 3 次 FIX 未通过 / 分数退化 | 8 小时 | 保留队列，升级通知 |
| LOW | 总分 7-8 分（需审查但非紧急） | 24 小时 | 超时自动通过（仅限总分 ≥ 9 者） |

**队列健康监控**：
- 每 4 小时检查队列积压量，积压 > 10 条触发告警
- 队列深度硬上限 50 条，触发后暂停新画像生成

**审核队列数据结构**：

```json
{
  "review_queue": {
    "queue_name": "human_review_pending",
    "items": [
      {
        "item_id": "hr_001",
        "type": "PROFILE",  // PROFILE | SIMULATION
        "content_id": "persona-003",
        "priority": "HIGH",
        "submitted_at": "2026-06-08T14:30:00Z",
        "deadline": "2026-06-08T18:30:00Z",
        "review_reason": "连续3次FIX未通过",
        "review_materials": {
          "original": "...",
          "review_report": "...",
          "fix_history": "..."
        }
      }
    ]
  }
}
```

---

## 八、性能与扩展性

### 8.1 Agent并发度

| Agent | 是否可并行 | 最大并发度 | 瓶颈 |
|-------|-----------|-----------|------|
| GEN | 是（彼此独立） | 受限于LLM API配额 | API rate limit |
| SIM | 是（同一画像的不同场景） | 受限于LLM API配额 | API rate limit |
| REV | 是（无状态） | 高 | API rate limit |
| FIX | 是（无状态） | 高 | API rate limit |

### 8.2 消息队列配置

```yaml
message_queue:
  type: "Kafka"  # 或 RabbitMQ / Redis Stream
  topics:
    - name: "profile_generation"
      partitions: 10
      replication: 3
    - name: "profile_review"
      partitions: 10
      replication: 3
    - name: "simulation_generation"
      partitions: 20
      replication: 3
    - name: "simulation_review"
      partitions: 20
      replication: 3
    - name: "fix_requests"
      partitions: 10
      replication: 3
    - name: "human_review"
      partitions: 5
      replication: 3
  
  consumer_groups:
    - name: "gen_consumers"
      consumers: 5
      auto_offset_reset: "earliest"
    - name: "rev_consumers"
      consumers: 10
      auto_offset_reset: "earliest"
```

---

## 九、实现 checklist

```markdown
□ 消息队列部署（Kafka/RabbitMQ）
□ ORCH 编排器实现（状态机管理）
□ GEN Agent 封装（LLM调用 + Prompt管理）
□ SIM Agent 封装（LLM调用 + 上下文注入）
□ REV Agent 封装（规则引擎 + LLM辅助评分）
□ FIX Agent 封装（修改指令生成）
□ 全局状态存储（Redis/MongoDB）
□ 人工审核UI（队列展示 + 审校操作）
□ 监控告警（Agent超时/错误率/队列堆积）
□ 日志追踪（correlation_id 全链路）
```

---

*本协议与以下文件配套使用：*
- [`07-Harness架构设计方案.md`](./07-Harness架构设计方案.md)（Harness模块与Agent的映射关系）
- [`10-完整案例演示.md`](./10-完整案例演示.md)（协作流程的实际运行示例）
- [`13-实现参考与接口定义.md`](./13-实现参考与接口定义.md)（接口的伪代码实现）
