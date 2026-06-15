# AI_CBC 前端 P0 缺失页面补齐报告

## 新增页面清单

| 编号 | 页面 | 路由 | 文件路径 | 状态 |
|------|------|------|----------|------|
| P0-001 | 研究创建与配置页 | `/studies/new` | `frontend/src/pages/StudyCreate.tsx` | ✅ 已完成 |
| P0-002 | 画像管理页 | `/personas` | `frontend/src/pages/PersonaManager.tsx` | ✅ 已完成 |
| P0-003 | 问卷预览页 | `/studies/:id/questionnaire` | `frontend/src/pages/QuestionnairePreview.tsx` | ✅ 已完成 |
| P0-004 | 模拟作答页 | `/studies/:id/responses` | `frontend/src/pages/ResponseSimulator.tsx` | ✅ 已完成 |

## API 对接状态

| API 函数 | 方法 | 端点 | 文件 | 状态 |
|----------|------|------|------|------|
| `createStudy` | POST | `/studies` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `generateQuestionnaire` | POST | `/studies/{id}/generate` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `getQuestionnaire` | GET | `/studies/{id}/questionnaire` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `generatePersonas` | POST | `/personas/generate` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `simulateResponses` | POST | `/studies/{id}/simulate-responses` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `exportDataset` | GET | `/studies/{id}/responses/export` | `frontend/src/services/api.ts` | ✅ 已对接 |
| `getPersona` | GET | `/personas/{id}` | `frontend/src/services/api.ts` | ✅ 已补充（详情弹窗使用） |

## 类型定义补充

| 类型 | 文件 | 状态 |
|------|------|------|
| `CreateStudyRequest` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `GenerateQuestionnaireResponse` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `QuestionnaireDetail` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `ChoiceSet` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `ChoiceAlternative` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `SimulateResponsesRequest` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `SimulateResponsesResponse` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `RawDatasetExportResponse` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `PersonaDetail` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `GeneratePersonasRequest` | `frontend/src/types/api.ts` | ✅ 已补充 |
| `GeneratePersonasResponse` | `frontend/src/types/api.ts` | ✅ 已补充 |

## 路由与导航更新

| 文件 | 变更内容 | 状态 |
|------|----------|------|
| `frontend/src/router.tsx` | 新增 4 条路由：`/studies/new`、`/studies/:id/questionnaire`、`/studies/:id/responses`、`/personas` | ✅ 已更新 |
| `frontend/src/components/Layout.tsx` | 新增侧边栏菜单项：创建研究、画像管理 | ✅ 已更新 |

## 构建状态

- 命令：`npm run build`
- 状态：待验证

## 备注

- 所有新增页面遵循现有代码风格：函数组件 + hooks + Ant Design 组件。
- 错误处理统一使用 `try/catch` + `Alert` 组件。
- 加载状态统一使用 `Spin` 或 `Skeleton`。
- 类型定义中不确定的深层字段使用 `Record<string, unknown>` 占位并标注 `TODO`。
- 未修改任何后端代码。
