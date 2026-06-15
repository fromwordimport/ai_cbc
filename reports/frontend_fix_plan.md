> **版本**：v1.0  
> **定位**：前端 P0/P1 缺口修复方案  
> **维护者**：小前  
> **关联文档**：`reports/frontend_gap.md`（审查报告）

---

# 前端 P0/P1 缺口修复方案

**审查范围**：`frontend/src/`（React + React Router v6 + Ant Design + ECharts）  
**发现时间**：2026-06-12  
**基准后端 schema**：`frontend/src/types/api.ts`（已由小P对齐后端）

---

## 一、发现汇总

| ID | 严重度 | 位置 | 症状 | 根因 |
|----|--------|------|------|------|
| GAP-001 | P0 | `router.tsx` | PersonaManager"详情"按钮点击 404 | 路由 `/personas/:id` 未注册 |
| GAP-002 | P0 (后端) | 后端 | 无 `GET /studies/{id}/analyses` 端点 | 后端未实现；前端3个组件受波及 |
| GAP-003 | P0 | `SegmentComparison.tsx:114` | 分析ID Select `options={[]}` 永远不可选 | 硬编码空数组，且关联 GAP-002 |
| GAP-004 | P0 | `router.tsx` + 两个页面 | QuestionnairePreview / ResponseSimulator 的 studyId 始终为 undefined | 路由参数名为 `:id`，组件解构为 `studyId` -- React Router 按名称匹配，不匹配 |
| GAP-005 | P1 | `MarketSimulator.tsx:308-326` | 分析ID Select 无 option（空 `<Select>` children） | 同 GAP-002/GAP-003，注释写"for now user types or runs fresh"但 Select 不支持自由输入 |
| GAP-006 | P1 | `SegmentComparison.tsx:39-44` | 用原始 `fetch()` 替代已有 `getSegmentComparison()` 的 `api.ts` service | 不走统一拦截器(API-Key/错误处理) |
| GAP-007 | P1 | `InterviewLab.tsx:41-44` | 同上，用原始 `fetch()` 替代已有 `converse()` | 同上 |

### 已确认无需修改

所有组件使用的字段名（`generated`, `simulated`, `n_total_records`, `personas`, `studies` 等）与 `types/api.ts` 一致。**无旧字段引用残留。**

---

## 二、逐项修复方案

### GAP-001 — 路由 `/personas/:id` 未注册

**文件**：`frontend/src/router.tsx`（新建路由）+ 新建 `frontend/src/pages/PersonaDetail.tsx`

**方案**：

1. 新建 `PersonaDetail.tsx` 组件：
   - 用 `useParams<{ id: string }>()` 获取 `persona_id`
   - `useEffect` 调用 `getPersona(id)` 获取数据（已存在于 `api.ts:217`）
   - 展示四层画像（`PersonaFullDetail` 字段）：`layer1_demographics`, `layer2_behavior`, `layer3_psychology`, `layer4_scenarios`
   - 展示真实性评分、偏见审计状态、语言样本
   - 使用 Ant Design `Descriptions` + `Card` + `Collapse`

2. 在 `router.tsx` 的 `children` 数组中新增：
   ```tsx
   { path: 'personas/:id', element: <PersonaDetail /> },
   ```
   注意：必须在 `{ path: 'personas', element: <PersonaManager /> }` 之前注册，因为 React Router v6 优先匹配精确路径。实际做法：将两个路由都保留（`personas` 精确匹配列表页，`personas/:id` 匹配详情页）。

**工作量**：约 1.5h（新建组件 1h + 路由注册 0.5h）

---

### GAP-002 — 后端缺少 GET /studies/{id}/analyses

**本质**：后端问题，前端无法自行修复。

**前端临时方案**（后端就绪前的 workaround）：

1. 在 `api.ts` 新增 `listAnalyses` 函数（准备好调用链路，后端就绪后只需上线）：
   ```ts
   export const listAnalyses = async (studyId: string) => {
     const { data } = await api.get(`/studies/${studyId}/analyses`)
     return data
   }
   ```

2. 类型定义在 `types/api.ts` 新增：
   ```ts
   export interface AnalysisSummary {
     analysis_id: string
     study_id: string
     status: string
     model_type: string
     completed_at: string | null
   }
   export interface AnalysisListResponse {
     analyses: AnalysisSummary[]
   }
   ```

3. 在受波及组件（SegmentComparison, MarketSimulator）中，当用户选择 study 后，调用 `listAnalyses` 填充 analysisId Select。

**注意**：在后端实现该端点前，这两个 Select 维持不可用是预期行为。如果有人需要紧急使用，可改用 `AutoComplete` 组件让用户手动输入 analysisId（降级方案）。

**工作量**：纯前端 0.5h（API 函数 + 类型）。后端端点实现时间不计入前端。

---

### GAP-003 — SegmentComparison 分析ID Select options={[]}

**文件**：`frontend/src/pages/SegmentComparison.tsx` 第 109-117 行

**问题**：
```tsx
<Select
  placeholder="分析结果ID"
  value={analysisId}
  onChange={setAnalysisId}
  options={[]}  // ← 硬编码空数组
/>
```

**修复**：
1. 新增 state：`const [analyses, setAnalyses] = useState<AnalysisSummary[]>([])`
2. 当 `selectedStudyId` 变化时，调用 `listAnalyses(selectedStudyId)` 填充 `analyses`
3. Select 改为：
   ```tsx
   options={analyses.map(a => ({ label: `${a.analysis_id} (${a.model_type})`, value: a.analysis_id }))}
   ```
4. 如后端暂未就绪，采用 `AutoComplete` 降级，允许手动输入 analysisId

**联动**：依赖 GAP-002 的 API + 类型定义。

**工作量**：0.5h（含 AutoComplete 降级 fallback）

---

### GAP-004 — 路由参数名不匹配（新发现 P0）

**文件**：
- `frontend/src/router.tsx` 第 25-26 行
- `frontend/src/pages/QuestionnairePreview.tsx` 第 8 行
- `frontend/src/pages/ResponseSimulator.tsx` 第 8 行

**问题**：
```tsx
// router.tsx - 参数名 "id"
{ path: 'studies/:id/questionnaire', element: <QuestionnairePreview /> },
{ path: 'studies/:id/responses',      element: <ResponseSimulator /> },

// QuestionnairePreview.tsx / ResponseSimulator.tsx - 解构的是 "studyId"
const { studyId } = useParams<{ studyId: string }>()
```

React Router v6 的 `useParams()` 按路由模式中的参数名返回键值。路由是 `:id`，返回对象是 `{ id: "..." }`。解构 `studyId` 拿到的永远是 `undefined`。这两个页面**完全无法工作**。

**修复方案 A（推荐 — 改路由，最小改动）**：
```tsx
// router.tsx
{ path: 'studies/:studyId/questionnaire', element: <QuestionnairePreview /> },
{ path: 'studies/:studyId/responses',      element: <ResponseSimulator /> },
```

**修复方案 B（改组件，同样简单）**：
```tsx
// QuestionnairePreview.tsx & ResponseSimulator.tsx
const { id } = useParams<{ id: string }>()
const studyId = id
```

**推荐方案 A**，理由：`studyId` 语义比 `id` 更清晰，且组件代码已大量使用 `studyId`。

**工作量**：0.25h（改 2 行路由）

---

### GAP-005 — MarketSimulator 分析ID Select 无数据

**文件**：`frontend/src/pages/MarketSimulator.tsx` 第 308-326 行

**问题**：Select children 为空，注释写"for now user types or runs fresh"但 Select 不支持自由输入。

**修复**：同 GAP-003 方案 —— 在用户选择 study 后调用 `listAnalyses()` 填充选项，或改用 `AutoComplete`。

**工作量**：0.5h

---

### GAP-006 — SegmentComparison 用 raw fetch 替代 api.ts service

**文件**：`frontend/src/pages/SegmentComparison.tsx` 第 38-52 行

**当前代码**：
```tsx
const res = await fetch(
  `/api/v1/studies/${selectedStudyId}/analysis/${analysisId}/segment-comparison?...`,
  { headers: { 'X-API-Key': 'dev-key-change-in-prod' } },
)
```

`api.ts` 中已有 `getSegmentComparison()` 函数（第 250-261 行），使用统一 axios 实例、拦截器、错误处理。

**修复**：直接用 service 函数替换：
```tsx
const data = await getSegmentComparison(selectedStudyId, analysisId, segmentA, segmentB)
setResult(data)
```

**工作量**：0.25h

---

### GAP-007 — InterviewLab 用 raw fetch 替代 api.ts converse()

**文件**：`frontend/src/pages/InterviewLab.tsx` 第 41-44 行

**当前代码**：
```tsx
const res = await fetch(`/api/v1/personas/${selectedPersonaId}/converse`, { ... })
```

`api.ts` 中已有 `converse()` 函数（第 238-244 行）。

**修复**：直接用 service 函数替换：
```tsx
const data = await converse(selectedPersonaId, { question, context: {} })
```

另：`InterviewLab.tsx:44` 硬编码了 `context: {}`，但 `ConverseRequest.context` 类型是 `Array<{ role, content }>`。`{}` 不是数组，但仍会序列化为 `{}` 发送。后端可能接受也可能报错。建议修正为 `context: []` 或不传 context。

**工作量**：0.25h

---

## 三、工时估算

| ID | 任务 | 估时 |
|----|------|------|
| GAP-001 | 新建 PersonaDetail 组件 + 路由注册 | 1.5h |
| GAP-002 | api.ts 新增 listAnalyses + 类型定义 | 0.5h |
| GAP-003 | SegmentComparison 修复 options + AutoComplete 降级 | 0.5h |
| GAP-004 | 路由参数名修复（studyId 对齐） | 0.25h |
| GAP-005 | MarketSimulator 分析ID options 填充 | 0.5h |
| GAP-006 | SegmentComparison raw fetch → api.ts service | 0.25h |
| GAP-007 | InterviewLab raw fetch → api.ts service | 0.25h |
| 联调 | 全部修复后的回归测试 | 1.0h |
| **合计** | | **4.75h** |

**前置条件**：GAP-002 完成后端实现后，GAP-003 和 GAP-005 才能完整可用。在此之前可用 AutoComplete 降级。

---

## 四、修复顺序建议

```
第1步: GAP-004 (路由参数名修复)          ← 阻塞性 P0，最快修复
第2步: GAP-001 (PersonaDetail 组件+路由)  ← 独立 P0
第3步: GAP-006, GAP-007 (raw fetch 替换)  ← 独立 P1，快速
第4步: GAP-002 (listAnalyses API + 类型)   ← 后端依赖
第5步: GAP-003, GAP-005 (options 填充)    ← 依赖 GAP-002
```

---

## 五、新增文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/pages/PersonaDetail.tsx` | **新建** | Persona 详情页组件 |
| `frontend/src/router.tsx` | 修改 | 新增 `personas/:id` 路由；修复 `:id` → `:studyId` |
| `frontend/src/services/api.ts` | 修改 | 新增 `listAnalyses()` |
| `frontend/src/types/api.ts` | 修改 | 新增 `AnalysisSummary`, `AnalysisListResponse` |
| `frontend/src/pages/SegmentComparison.tsx` | 修改 | GAP-003 + GAP-006 |
| `frontend/src/pages/MarketSimulator.tsx` | 修改 | GAP-005 |
| `frontend/src/pages/InterviewLab.tsx` | 修改 | GAP-007 |

---

## 六、PersonaDetail 组件设计草图

```
组件结构:
PersonaDetail
├── Spin (loading)
├── Alert (error)
├── Card "基本信息"
│   ├── persona_id, segment, life_stage, city_tier, income_bracket
│   ├── authenticity_score (Tag: 绿/橙/红)
│   └── bias_audit_status (Tag)
├── Collapse "四层画像"
│   ├── Panel "Layer 1: 人口统计" → layer1_demographics
│   ├── Panel "Layer 2: 行为模式" → layer2_behavior
│   ├── Panel "Layer 3: 心理动机" → layer3_psychology
│   └── Panel "Layer 4: 情境叙事" → layer4_scenarios
├── Card "语言样本" → language_samples (List)
├── Card "洗碗机场景上下文" → dishwasher_context
└── Card "生成元数据" → generation_metadata

数据来源: getPersona(id) → PersonaDetail (api.ts:217)
或 getPersonaFullDetail(id) → PersonaFullDetail (api.ts:222，两者实际调用同一端点)
```

API 返回 `PersonaDetail` 时含 `profile?: Record<string, unknown>`，如果后端已返回四层数据在 `profile` 字段中，组件需从 `profile` 中提取。`PersonaFullDetail` 类型（第 359-372 行）明确包含了四层字段，建议实际请求时后端返回该完整结构。如果暂时只返回 `PersonaDetail`，组件用 `profile` 做 fallback 渲染。
