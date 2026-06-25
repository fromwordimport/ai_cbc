# AI_CBC 项目报告索引

> **版本**：v1.1
> **定位**：`reports/` 目录的中央索引，分类汇总项目过程中的进度、审计、验证与计划类报告
> **维护者**：小P（项目负责人）
> **更新日期**：2026-06-25

---

## 一、报告总览

`reports/` 目录存放项目推进过程中产生的各类工作性报告，包括整改进度、专项审计、修复方案、验证报告与性能基准。正式规格文档仍归口到 `docs/` 各子目录；开发计划与实施类文档在完成后应归档或迁移到 `docs/生产就绪评估/`。

---

## 二、按类别导航

### 2.1 进度与状态报告

| 文件 | 日期 | 说明 |
|------|------|------|
| `2026-06-14-生产就绪整改进度报告.md` | 2026-06-14 | 模块1-7完成状态、测试回归、API契约对齐、缺失模块实现、遗留风险 |
| `performance_test_report_v0.2.0.md` | 2026-06-15 | Locust 压测脚本、50并发基线、瓶颈分析与100/500/1000并发执行指南 |

### 2.2 专项审计报告

| 文件 | 日期 | 审查范围 | 关键结论 |
|------|------|---------|---------|
| `2026-06-15-BE6-k8s-security-review.md` | 2026-06-15 | k8s/ 目录下所有 manifest 文件 | 2 CRITICAL + 3 HIGH + 4 MEDIUM + 3 LOW，含 SEC-001~SEC-013 |
| `2026-06-16-BE6-k8s-security-re-review.md` | 2026-06-16 | k8s/ 目录下所有 manifest 文件及 overlays | CRITICAL/HIGH 5/5 已修复或 Mitigated；Staging 部署剩余 blocker 为 SEC-009 和 MongoDB 认证一致性 |
| `agent_audit.md` | 2026-06-11 | Agent框架、提示模板、评估链、LLM客户端 | SEC-012 Persona注入、自纠正未闭环、Prompt Caching缺失 |
| `security_audit.md` | 2026-06-11 | 安全中间件、API输入校验、红队测试、LLM安全 | 99/99红队通过；SEC-012/013两个High漏洞待修复 |
| `cost_audit.md` | 2026-06-11 | 成本追踪、熔断机制、study_id传递链 | study_id传递链修复、持久化状态、自动预算重置 |
| `integration_audit.md` | 2026-06-11 | 子系统集成点 | 集成状态简要评估 |
| `bias_pipeline_review.md` | 2026-06-11 | 偏见审计管线 | 公平性规则嵌入与审计链路审查 |
| `quality_report.md` | 2026-06-11 | 全量测试与覆盖率 | 测试分布、覆盖率缺口、慢测试 |
| `methodology_review.md` | 2026-06-11 | 方法论层面 | 建模与实验设计方法论审查 |
| `model_validation.md` | 2026-06-11 | 模型验证 | 参数恢复与模型验证状态 |
| `frontend_gap.md` | 2026-06-11 | 前端完整性 | 12页面状态、API对接率75%、P0/P1缺口 |

### 2.3 修复与实施计划

| 文件 | 日期 | 说明 |
|------|------|------|
| `agent_fix_plan.md` | 2026-06-12 | Agent框架P0/P1修复方案：feedback注入、trigger_correction实现、AnalysisAgent统一 |
| `bias_implementation_plan.md` | 2026-06-12 | 6条公平性硬规则嵌入实施计划 |
| `design_refactor_plan.md` | 2026-06-12 | 设计重构方案 |
| `frontend_fix_plan.md` | 2026-06-12 | 前端P0/P1缺口修复方案：路由、分析列表、raw fetch替换 |
| `router_unification_plan.md` | 2026-06-12 | API路由统一方案 |
| `prohibited_pairs_implementation_plan.md` | 2026-06-13 | 禁止组合功能实现计划（由根目录 `plan.md` 归档） |

### 2.4 验证与检查清单

| 文件 | 日期 | 说明 |
|------|------|------|
| `fairness_verification_checklist.md` | 2026-06-11 | 公平性验证检查清单 |
| `synthetic_vs_prior_validation.md` | 2026-06-11 | 合成数据与先验对比验证 |
| `uat_plan.md` | 2026-06-11 | 业务验收计划（UAT）v2.0 |
| `2026-06-16-BE6-k8s-static-validation-report.md` | 2026-06-16 | 无集群环境下的 K8s manifest 静态验证（Python 脚本） | 通过，仅 CI/CD 占位符提示 |
| `frontend_e2e_experience_report.md` | 2026-06-13 | Playwright完整CBC流程体验报告（由 `frontend/AI_CBC_体验报告.md` 归档） |

### 2.5 性能基准报告

| 文件 | 日期 | 说明 |
|------|------|------|
| `performance/2026-06-23-baseline.md` | 2026-06-23 | 后端性能优化基线报告：环境、测试配置、关键指标、火焰图/内存图占位 |

---

## 三、与正式文档的边界

| 类型 | 存放位置 | 示例 |
|------|---------|------|
| 正式规格/设计文档 | `docs/`、`consumer-simulation/`、`cbc-questionnaire-system/`、`cbc-analysis-system/` | `数据字典.md`、洗碗机CBC实验设计方案 |
| 正式验收文档 | `docs/验收/` | 验收测试计划、缺陷报告、签署文件 |
| 正式培训材料 | `docs/training/` | 虚拟消费者验证逻辑白皮书、速查卡 |
| 工作性报告/审计/计划 | `reports/` | 本目录内各文件 |
| 已过期/待清理文件 | `delete/` | `progress_report.md`、`frontend_fixes.md`、`performance_review.md` |

---

## 四、新增与归档规则

1. **新增报告**：先归类到上述四种类别之一，文件名建议使用 `YYYY-MM-DD-主题.md` 格式。
2. **报告升级**：当报告内容被后续正式文档或更大范围报告覆盖时，应将旧版本移入 `delete/` 并在本索引中删除条目。
3. **索引同步**：每新增/移动/删除 `reports/` 内文件，必须同步更新本 `README.md`。

---

*本索引为 `reports/` 目录的导航中心，所有新增报告必须在此登记。*
