# AI_CBC 禁止组合（Prohibited Pairs）功能实现计划

## 现状分析

### 后端算法引擎已就绪
- `models.py` — `ProhibitedPair` / `Condition` 模型已定义，`CBCStudy` 已包含 `prohibited_pairs` 字段
- `d_optimal.py` — `d_optimal_design()` 和 `generate_d_optimal_questionnaire()` 接受 `prohibited_pairs`，生成候选集时自动过滤禁止组合
- `generator.py` — `create_study()` 和 `generate_questionnaire()` 已传递 `prohibited_pairs`
- `validators.py` — `validate_prohibited_pairs()` 已存在，检查生成的问卷是否违反禁止组合

### 缺失部分
- **API Schema** — `StudyDesignResponse` / `UpdateStudyDesignRequest` 没有包含 `prohibited_pairs`
- **API 端点** — `GET/PUT /studies/{study_id}/design` 没有处理 `prohibited_pairs`
- **前端类型** — 没有 `ProhibitedPair` / `ProhibitedCondition` 类型
- **前端页面** — `AttributeDesign.tsx` 没有禁止组合配置 UI
- **Mock 后端** — `dev_server_with_mocks.py` 没有 `prohibited_pairs` 相关逻辑

## 开发阶段

### Stage 1 — 后端 API 扩展（小端）
**目标**: 让 design 端点支持 prohibited_pairs 的读写

**API 契约**:
```json
// GET /api/v1/studies/{study_id}/design 响应
{
  "study_id": "demo-study-001",
  "attributes": [...],
  "prohibited_pairs": [
    {
      "conditions": [
        { "attribute_id": "brand", "level_value": "brand_a" },
        { "attribute_id": "price", "level_value": "2999" }
      ]
    }
  ]
}

// PUT /api/v1/studies/{study_id}/design 请求
{
  "attributes": [...],
  "prohibited_pairs": [
    {
      "conditions": [
        { "attribute_id": "brand", "level_value": "brand_a" },
        { "attribute_id": "price", "level_value": "2999" }
      ]
    }
  ]
}
```

**任务**:
1. 在 `schemas.py` 更新 `StudyDesignResponse` 和 `UpdateStudyDesignRequest`，添加 `prohibited_pairs: list[dict[str, Any]]`
2. 在 `questionnaires.py` 的 `GET /studies/{study_id}/design` 中返回 `study.prohibited_pairs`（序列化）
3. 在 `PUT /studies/{study_id}/design` 中解析 `request.prohibited_pairs`，验证后更新 `study.prohibited_pairs`
4. 验证：每个 prohibited pair 至少有2个条件，attribute_id 必须存在于当前属性中，level_value 必须存在于对应属性的水平中
5. 在 `dev_server_with_mocks.py` 中更新 `GET/PUT /studies/{study_id}/design`，支持 mock 的 prohibited_pairs 读写

**输入文件**:
- `src/aicbc/api/schemas.py`
- `src/aicbc/api/routes/questionnaires.py`
- `scripts/dev_server_with_mocks.py`

**输出文件**:
- 修改后的上述文件

### Stage 2 — 前端类型与页面增强（小前）
**目标**: 添加禁止组合配置 UI

**任务**:
1. 在 `types/api.ts` 添加新类型：
   ```typescript
   interface ProhibitedCondition {
     attribute_id: string
     level_value: string
   }
   interface ProhibitedPair {
     conditions: ProhibitedCondition[]
   }
   ```
   更新 `StudyDesignResponse` 和 `StudyDetail` 添加 `prohibited_pairs`
2. 在 `services/api.ts` 更新 `getStudyDesign` / `updateStudyDesign` 类型签名
3. 在 `AttributeDesign.tsx` 添加禁止组合配置区域：
   - 新增状态 `prohibitedPairs: ProhibitedPair[]`
   - 新增 UI 区域：「禁止组合」卡片
   - 添加条件选择器：两个级联 Select（先选属性 → 再选水平）
   - 添加「添加禁止组合」按钮，将选中的条件组合加入列表
   - 已添加的禁止组合以列表/Tag 形式展示，支持删除
   - 验证：至少2个条件、不同属性、水平值有效
   - 保存时连同 `prohibited_pairs` 一起提交
4. 在 `QuestionnaireConfig.tsx` 或问卷预览中，如果存在禁止组合，显示提示信息

**UI 布局建议**:
在属性与水平列表下方，保存按钮上方，添加一个 Collapse Panel 或独立 Card：
```
┌─────────────────────────────────────┐
│ 禁止组合                              │
│ ─────────────────────────────────── │
│ 条件1: [属性选择▼] [水平选择▼]        │
│ 条件2: [属性选择▼] [水平选择▼]        │
│      [+ 添加禁止组合]                 │
│                                       │
│ 已禁止:                               │
│  ❌ 品牌=品牌A 且 价格=2999元        │
│  ❌ 容量=8套 且 安装方式=台式        │
└─────────────────────────────────────┘
```

**输入文件**:
- `frontend/src/types/api.ts`
- `frontend/src/services/api.ts`
- `frontend/src/pages/AttributeDesign.tsx`

**输出文件**:
- 修改后的上述文件

## 验收标准
- [ ] `GET /api/v1/studies/{study_id}/design` 返回包含 `prohibited_pairs` 的完整响应
- [ ] `PUT /api/v1/studies/{study_id}/design` 成功保存 `prohibited_pairs` 并返回最新数据
- [ ] 前端页面可以添加、查看、删除禁止组合
- [ ] 禁止组合条件必须来自已配置的属性与水平，无效的 attribute_id / level_value 被拒绝
- [ ] 生成问卷时，D-optimal 算法自动过滤包含禁止组合的产品配置
- [ ] Mock 后端支持 prohibited_pairs 的读写
