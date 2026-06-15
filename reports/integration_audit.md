# AI_CBC 数据管道与集成审查报告

> **审查人**: 小端
> **日期**: 2026-06-11

---

## 一、数据管道一致性

### 1.1 PersonaProfile 传递链路

追踪了 `core/models/persona.py` → `api/schemas.py`(PersonaDetail/PersonaSummary) → `tools/subsystems.py` → `tools/pipeline.py` 的完整传递。字段名与数据字典完全一致。

**但发现一处重要 Bug** — `api/schemas.py:85-96` (PersonaSummary.from_profile)：
- `life_stage` 错误映射到 `profile.layer1_demographics.city`
- `city_tier` 错误映射到 `profile.layer4_scenarios.daily_routine[:20]`
- 正确映射应为：`life_stage` → `profile.segment`，`city_tier` → `profile.layer1_demographics.city`

### 1.2 CBCRawDataset 格式验证

对照数据字典 Section 五，15个字段全部匹配。metadata (study_id, n_respondents, n_choice_sets, n_alternatives, attributes) 和 choice_records 及其子字段全部一致。

### 1.3 AnalysisResult 格式验证

| 数据字典 | 实现 | 位置 |
|---------|------|------|
| `result_id` | `analysis_id` | Section 七 / `analysis/models.py:230` |
| `convergence.ess_min` | `convergence.ess_bulk_min` | Section 7.1 / `analysis/models.py:57` |
| `created_at` | `completed_at` | Section 七 / `analysis/models.py:240` |

---

## 二、工具调用协议

设计文档与 `protocol.py` 实现完全一致：ToolSpec、ToolCallRequest、ToolCallResult、ToolRegistry、5种状态码、超时/重试策略、参数校验、OpenAI schema生成全部实现。

4个核心数据流工具（persona_to_questionnaire_context、responses_to_raw_dataset、analysis_result_to_report_context、validate_data_flow）全部正确实现于 `pipeline.py`。

---

## 三、前后端类型对齐（核心发现）

### 3.1 确认小前报告的4处不匹配

| # | 接口 | 前端字段 | 后端字段 | 前端位置 | 后端位置 |
|---|------|---------|---------|---------|---------|
| 1 | **SimulateResponsesResponse** | `simulated_count` | `simulated` | `api.ts:89` | `schemas.py:458` |
| 2 | **RawDatasetExportResponse** | `download_url` (文件下载) | `choice_records` (内联数据) | `api.ts:99` | `schemas.py:471` |
| 3 | **GeneratePersonasResponse** | `generated_count` / `persona_ids` | `generated` / `personas` | `api.ts:149-150` | `schemas.py:59,61` |
| 4 | **ConverseResponse** | `answer` | `consumer_response` | `api.ts:286` | `schemas.py:228` |

**影响**：全部会导致对应功能完全中断。

### 3.2 审查过程额外发现

| # | 问题 | 严重度 |
|---|------|-------|
| 5 | SimulateResponsesRequest.mode: `'deterministic'\|'stochastic'` vs `'rule'\|'llm'` | P1 |
| 6 | ConverseRequest.context: `Array<{role,content,emotion}>` vs `dict` | P1 |
| 7 | ChoiceSet/ChoiceAlternative: `set_id`/`alt_id` vs `choice_set_id`/`alt_index` | P1 |
| 8 | QuestionnaireDetail: `design_params` 嵌套 vs 扁平字段 | P1 |
| 9 | GenerateQuestionnaireResponse: 前端有status/n_attributes 后端有questionnaire_id/a_efficiency | P1 |
| 10 | SegmentComparisonResponse: `comparisons` vs `per_attribute` | P2 |
| 11-14 | 其他4处命名不一致 | P2 |

---

## 四、E2E集成测试

- **文件**：`tests/test_e2e_full_pipeline.py`（1347行，8类，21方法）
- **覆盖**：Study创建→问卷生成→画像生成→模拟作答→HB分析→WTP→市场模拟 + 数据字典验证 + Effects Coding验证 + 错误传播 + 序列化
- **运行状态**：因 `aicbc` 模块未安装无法运行（需 `uv pip install -e .`）
- **测试设计质量**：优秀

---

## 五、运行时 Bug

`src/aicbc/analysis/routes.py:105-106`：

```python
ess_bulk_min=hb_result.ess_min,   # BUG: HBResult 没有 ess_min 属性
ess_tail_min=hb_result.ess_min,   # BUG: 同上
```

`HBResult`（hb_engine.py:36-47）的属性是 `ess_bulk_min` 和 `ess_tail_min`，此处会抛出 `AttributeError`。

---

## 六、优先级汇总

| 优先级 | 数量 | 关键问题 |
|-------|------|---------|
| **P0** | 6 | 4处前后端字段不匹配 + PersonaSummary映射错误 + routes.py AttributeError |
| **P1** | 6 | mode值域、context类型、命名不一致、嵌套vs扁平、缺失字段 |
| **P2** | 6 | 缺失字段补充、命名统一、文档对齐 |

建议首先修复 P0-1 到 P0-6 这6个阻塞性问题，然后运行 E2E 测试进行全链路验证。
