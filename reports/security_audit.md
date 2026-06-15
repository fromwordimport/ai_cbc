# AI_CBC 安全审查报告

> **审查人**: 小安
> **日期**: 2026-06-11
> **审查范围**: 安全中间件、API 输入校验、红队测试、LLM 安全（16 个文件）

---

## 一、安全中间件审查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| API Key 认证 | ✅ | `APIKeyMiddleware` 内联在 `main.py`，验证 `X-API-Key` 头 |
| 速率限制 | ✅ | `src/aicbc/api/middleware/rate_limit.py` 实现 per-key 限流 |
| 安全头 | ⚠️ | 缺少 CSP、HSTS、X-Content-Type-Options 等完整安全头 |
| CORS 配置 | ⚠️ | 未设置严格的 CORS 策略 |
| 输入清洗 | ✅ | `src/aicbc/core/security/input_sanitizer.py` 提供 sanitize_id/sanitize_text |
| API 文档 | ✅ | 生产环境已禁用 Swagger/ReDoc |
| 安全监控中间件 | ✅ | `src/aicbc/monitoring/middleware.py` 实现请求日志和安全头注入 |
| API Key 比较 | ⚠️ | 非恒定时间比较，存在时序攻击风险 |

---

## 二、API 输入校验

### 2.1 路由安全评估

| 路由文件 | Schemas 校验 | 路径参数清洗 | 输入过滤 | 评估 |
|----------|-------------|-------------|---------|------|
| `personas.py` | ✅ Pydantic v2 | ✅ sanitize_id | ✅ | PASS |
| `simulations.py` | ✅ | ✅ | ✅ | PASS |
| `responses.py` | ✅ | ✅ | ✅ | PASS |
| `questionnaires.py` | ✅ | ⚠️ 遗漏 sanitize_id | ⚠️ | WARN |
| `health.py` | N/A | N/A | N/A | PASS |

### 2.2 Schemas 安全评估

所有 Pydantic 模型均使用 `str` 类型带 `min_length/max_length` 约束，无 `eval()` 或 pickle 反序列化风险。

---

## 三、红队测试覆盖

| 攻击面 | 测试文件 | 用例数 | 覆盖率评估 |
|--------|----------|--------|-----------|
| Prompt 注入 | `test_api_security.py`, `test_agent_security.py` | 30+ | ✅ |
| 输入清洗绕过 | `test_input_sanitizer.py` | 20+ | ✅ |
| API 认证绕过 | `test_api_security.py` | 10+ | ✅ |
| 越狱指令 | `test_agent_security.py` | 15+ | ✅ |
| 恶意画像注入 | `test_agent_security.py` | 10+ | ✅ |
| 信息泄露 | `test_api_security.py` | 5+ | ✅ |
| DDoS/时序攻击 | 无 | 0 | ❌ 缺失 |
| 日志注入 | 无 | 0 | ❌ 缺失 |

**红队总用例**: 99 个，**全部通过** ✅

---

## 四、LLM 安全

### 4.1 Prompt 注入防护

| 检查项 | 状态 | 说明 |
|--------|------|------|
| System Prompt 清洗 | ⚠️ | Persona 字段直接嵌入 system prompt（**SEC-012**） |
| 用户输入过滤 | ✅ | `llm/client.py` 有 converse 注入检测 |
| 输出校验 | ✅ | 结构化输出验证 |
| 历史截断 | ✅ | 对话历史长度限制 |
| 输出泄漏检测 | ⚠️ | BehaviorSimulator 输出绕过泄漏检测（**SEC-013**） |

### 4.2 工具调用安全

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 工具权限最小化 | ⚠️ | 无工具沙箱机制 |
| 工具输入校验 | ✅ | 参数通过 Pydantic 校验 |
| 工具调用日志 | ✅ | 所有 tool call 已审计日志 |

---

## 五、漏洞与建议

### High（2项）

| 编号 | 描述 | 修复建议 |
|------|------|---------|
| **SEC-012** | Persona 字段直接嵌入 LLM system prompt 无清洗，可构造恶意 Persona | 对 persona 字段应用 `sanitize_text()` |
| **SEC-013** | BehaviorSimulator 输出绕过泄漏检测器 | 输出路径增加 `LeakageDetector` 检查 |

### Medium（7项）

| 编号 | 描述 | 修复建议 |
|------|------|---------|
| SEC-014 | questionnaires 路由遗漏 `sanitize_id()` | 统一路径参数清洗 |
| SEC-015 | 安全头不完整（CSP/HSTS/CORS） | 在 middleware 中添加完整安全头 |
| SEC-016 | API Key 非恒定时间比较 | 使用 `secrets.compare_digest()` |
| SEC-017 | 限流器非线程安全 | 添加 `threading.Lock()` |
| SEC-018 | 属性值可能包含注入内容 | 对问卷属性值清洗 |
| SEC-019 | 工具调用无沙箱 | 高风险工具添加沙箱执行 |
| SEC-020 | 速率限制仅 per-key，无 per-IP | 增加 IP 级别限流 |

### Low/Info（4项）

| 编号 | 描述 |
|------|------|
| SEC-021 | 输入清洗模式库有限 |
| SEC-022 | purchase-decision 路径未清洗 |
| SEC-023 | DDoS 防护测试缺失 |
| SEC-024 | 日志注入测试未覆盖 |

---

## 六、已确认修复项

| 编号 | 描述 | 状态 |
|------|------|------|
| SEC-001 | sanitize_id 路径遍历防护 | ✅ |
| SEC-002 | converse 注入检测 | ✅ |
| SEC-003 | 异常处理信息泄露 | ✅ |
| SEC-004 | API 文档生产禁用 | ✅ |
| SEC-005 | cost-status 过滤 | ✅ |
| SEC-006 | 限流中间件 | ✅ |
| SEC-007 | Agent prompt 注入检测 | ✅ |
| SEC-008 | API Key 认证 | ✅ |
| SEC-009 | 历史截断 | ✅ |
| SEC-010 | 输出泄漏检测 | ✅ |
| SEC-011 | 安全头注入 | ✅ |

---

## 七、总结

**安全态势评分: B+（良好，需加固）**

- 认证层健壮（API Key + 限流）
- 输入校验基本完整（questionnaires 模块需补充清洗）
- 红队测试 99/99 通过，DDoS/时序/日志注入盲区待补
- LLM 安全存在两处 High 漏洞（Persona 注入、输出泄漏绕过）

**建议优先级**：
- P0: SEC-012（Persona 清洗）、SEC-013（输出泄漏）
- P1: SEC-014~020
- P2: SEC-021~024
