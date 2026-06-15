# AI_CBC 前端完整性审查报告

> **审查人**: 小前
> **日期**: 2026-06-11
> **审查范围**: `frontend/` 全部前端代码，对照后端 API 路由

---

## 一、页面实现状态

| 规划页面 | 状态 | 组件路径 | 备注 |
|----------|------|---------|------|
| Dashboard | ✅ 完整 | `pages/Dashboard.tsx` | 核心看板，API 已对接 |
| ImportanceDashboard | ✅ 完整 | `pages/ImportanceDashboard.tsx` | 属性重要性图 |
| StudyCreate | ✅ 完整 | `pages/StudyCreate.tsx` | 创建研究 |
| QuestionnairePreview | ✅ 完整 | `pages/QuestionnairePreview.tsx` | 问卷预览 |
| QuestionnaireConfig | ✅ 完整 | `pages/QuestionnaireConfig.tsx` | 新增页面 |
| AnalysisStatus | ✅ 完整 | `pages/AnalysisStatus.tsx` | 新增页面 |
| Settings | ✅ 完整 | `pages/Settings.tsx` | 新增页面，含 API 配置 |
| MarketSimulator | 🚧 基本完成 | `pages/MarketSimulator.tsx` | **硬编码洗碗机属性** |
| PersonaManager | 🚧 基本完成 | `pages/PersonaManager.tsx` | **缺少详情路由（GAP-001）** |
| ResponseSimulator | 🚧 基本完成 | `pages/ResponseSimulator.tsx` | 进度条硬编码 50%，类型不匹配 |
| InterviewLab | 🚧 基本完成 | `pages/InterviewLab.tsx` | **绕过 api.ts，使用原生 fetch** |
| SegmentComparison | 🚧 基本完成 | `pages/SegmentComparison.tsx` | **分析ID Select 硬编码空数组（GAP-003）** |

---

## 二、路由完整性

### 2.1 已注册路由

| 路由 | 组件 | 状态 |
|------|------|------|
| `/` | Dashboard | ✅ |
| `/importance` | ImportanceDashboard | ✅ |
| `/market-simulator` | MarketSimulator | ✅ |
| `/personas` | PersonaManager | ✅ |
| `/questionnaire-config` | QuestionnaireConfig | ✅ |
| `/analysis-status` | AnalysisStatus | ✅ |
| `/settings` | Settings | ✅ |
| `/study/create` | StudyCreate | ✅ |
| `/questionnaire/preview/:id` | QuestionnairePreview | ✅ |
| `/response-simulator` | ResponseSimulator | ✅ |
| `/interview-lab` | InterviewLab | ✅ |
| `/segment-comparison` | SegmentComparison | ✅ |

### 2.2 缺失路由

| 路由 | 说明 | 优先级 |
|------|------|--------|
| `/personas/:id` | 画像详情页未注册 —— **GAP-001** | P0 |
| `*` (404) | 无 404 兜底页面 | P1 |

---

## 三、API 对接矩阵

### 3.1 对接概览

后端共 28 个业务端点，前端已对接 **21 个**（**75%**）。

### 3.2 按模块对接详情

| 模块 | 端点总数 | 已对接 | 对接率 |
|------|---------|--------|--------|
| 健康检查 | 3 | 3 | 100% |
| 画像管理 | 4 | 3 | 75% |
| 问卷系统 | 3 | 3 | 100% |
| 作答模拟 | 3 | 3 | 100% |
| 对话模拟 | 1 | 1 | 100% |
| 分析引擎 | 8 | 8 | **100%** |
| 市场模拟 | 2 | 2 | 100% |
| 行为模拟 | 3 | 1 | 33% |

### 3.3 关键类型不匹配

| 接口 | 前端类型字段 | 后端返回字段 | 风险 |
|------|-------------|-------------|------|
| `SimulateResponsesResponse` | `simulated_count` | `simulated` | 前端读不到数据 |
| `RawDatasetExportResponse` | `download_url` | `choice_records` 数组 | 下载功能失效 |
| `GeneratePersonasResponse` | `generated_count` + `persona_ids` | `generated` + `personas` 列表 | 前端读不到数据 |
| `ConverseResponse` | `answer` | `consumer_response` | 对话结果展示为空 |

---

## 四、缺失功能清单

### P0（阻塞发布 — 3项）

| 编号 | 描述 | 影响 |
|------|------|------|
| **GAP-001** | `/personas/:id` 路由未注册，PersonaManager 详情按钮 404 | 画像详情不可用 |
| **GAP-002** | 后端缺少 `GET /studies/{id}/analyses` 列表端点 | 市场模拟分析ID下拉为空 |
| **GAP-003** | SegmentComparison 分析ID Select `options={[]}` 硬伤 | 市场细分对比不可用 |

### P1（发布前修复 — 6项）

| 编号 | 描述 |
|------|------|
| GAP-004 | InterviewLab 和 SegmentComparison 绕过 `api.ts`，使用原生 `fetch` + 硬编码 API Key |
| GAP-005 | MarketSimulator 属性水平硬编码为洗碗机，不支持其他产品 |
| GAP-006 | ResponseSimulator 进度条硬编码 50% |
| GAP-007 | 4 处 API 类型不匹配 |
| GAP-008 | 无 404 页面 |
| GAP-009 | 缺少动态属性加载 |

### P2（长期优化 — 3项）

| 编号 | 描述 |
|------|------|
| GAP-010 | 图表组件未复用（ImportanceDashboard 与 SegmentComparison 重复 ECharts 配置） |
| GAP-011 | 无懒加载（12 页面全量打包） |
| GAP-012 | Ant Design TabPane 已废弃（React 19 兼容性） |

---

## 五、UI/UX 问题

| 问题 | 位置 | 严重度 |
|------|------|--------|
| 进度条硬编码 | ResponseSimulator | Medium |
| 属性硬编码 | MarketSimulator | Medium |
| 无加载骨架屏 | 多个页面 | Low |
| 无空状态提示 | PersonaManager 空白列表 | Low |
| AntD TabPane 废弃警告 | InterviewLab | Low |

---

## 六、关键对比（与 6月10日旧版报告）

| 维度 | 旧版 | 新版 | 变化 |
|------|------|------|------|
| 页面数 | 3 | 12 | +9 |
| API 对接率 | 40% | 75% | +35pp |
| P0 缺失 | 4 项 | 3 项 | -1 |
| Axios 拦截器 | 无 | 有 | 已补齐 |
| 类型不匹配 | 未审查 | 4 项 | 新发现 |

---

## 七、总结

前端框架已基本建立，12 页面全部有组件文件，API 对接率从 40% 提升至 75%。剩余工作集中在：

1. **P0**: 画像详情路由 + 分析列表接口 + SegmentComparison fix
2. **P1**: fetch 绕过 -> api.ts、类型不匹配、硬编码 -> 动态
3. **P2**: 组件复用、懒加载、无障碍

预计 P0+P1 修复工作量：**3-4 人日**。
