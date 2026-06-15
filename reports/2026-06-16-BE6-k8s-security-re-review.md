# K8s Staging 部署安全复审报告（BE-6d）

> **日期**: 2026-06-16
> **复审人**: team-lead（代小安执行）
> **范围**: `k8s/` 目录下所有 manifest 文件及 overlays
> **目标**: 确认 BE-6 部署前 CRITICAL/HIGH 安全问题已修复，评估 MEDIUM/LOW 问题是否阻塞 Staging 部署

---

## 1. 执行摘要

基于 2026-06-15 安全审查报告（`reports/2026-06-15-BE6-k8s-security-review.md`）进行复审。当前 K8s 配置中 **2 个 CRITICAL、3 个 HIGH 问题已全部修复或 Mitigated**；MEDIUM/LOW 问题大部分已修复，剩余项不影响 Staging 首次部署，但需在正式上线前跟踪。

**复审结论**：**有条件通过 Staging 部署**。条件：部署后必须验证 MongoDB 认证连接、Ingress 域名/TLS 已按实际环境替换、Secret 中的 API 密钥已通过 CI/CD 注入真实值。

---

## 2. CRITICAL 问题复审

| ID | 问题 | 原状态 | 当前状态 | 说明 |
|----|------|--------|----------|------|
| SEC-011 | 使用默认 ServiceAccount | 未修复 | **已修复** | 新建 `k8s/serviceaccount.yaml`，为 api/worker/beat/mongo 创建专用 SA，全部设置 `automountServiceAccountToken: false`；所有 Deployment/StatefulSet 已引用 |
| SEC-006 | Secret 模板含硬编码占位符 | 未修复 | **已修复** | `secret.yaml` 已改为 `data` 字段（base64 编码占位符），添加 `sealedsecrets.bitnami.com/managed: "false"` 与 `aicbc.internal/template: "true"` 注释，说明必须通过 CI/CD 或外部密钥管理注入真实值 |

---

## 3. HIGH 问题复审

| ID | 问题 | 原状态 | 当前状态 | 说明 |
|----|------|--------|----------|------|
| SEC-001 | readOnlyRootFilesystem: false | 未修复 | **已修复** | api/worker/beat 容器已改为 `readOnlyRootFilesystem: true`，并挂载 `emptyDir` 到 `/tmp`；MongoDB 因需写入 `/data/db` 保留为 false（已通过 PVC 隔离数据） |
| SEC-004 | 外部出口过于宽泛 | 未修复 | **已 Mitigated** | `network-policy.yaml` 已添加详细注释说明放宽理由（LLM API 使用 CDN 动态 IP），并给出通过 Egress Gateway/Cilium 进一步限制的后续建议；当前 Staging 可接受 |
| SEC-012 | latest 标签 + Always pull | 未修复 | **已修复** | base manifest 中镜像标签从 `latest` 改为 `0.1.0`，`imagePullPolicy` 改为 `IfNotPresent`；由 CI/CD 在 staging overlay 中替换为具体 commit SHA |

---

## 4. MEDIUM 问题复审

| ID | 问题 | 原状态 | 当前状态 | 是否阻塞 Staging | 说明 |
|----|------|--------|----------|------------------|------|
| SEC-002 | MongoDB readOnlyRootFilesystem | 未修复 | **接受风险** | 否 | 数据库容器需写入 `/data/db`，已通过 PVC 隔离；建议生产使用云托管 MongoDB |
| SEC-003 | 缺少 seccompProfile | 未修复 | **已修复** | 否 | api/worker/beat/mongo 已添加 `seccompProfile: RuntimeDefault`；Redis 已由 team-lead 补充 |
| SEC-005 | Worker/Beat 缺少 Ingress 限制 | 未修复 | **已修复** | 否 | 新增 `deny-ingress-worker-beat` NetworkPolicy，默认拒绝 worker/beat 的所有 Ingress |
| SEC-009 | example.com 占位符域名 | 未修复 | **待修复** | **是** | Ingress 仍使用 `api.aicbc.example.com` 占位符，Staging 部署前必须在 overlay 中替换为实际域名与 TLS secret |
| SEC-013 | MongoDB 单副本 | 未修复 | **已注释** | 否 | StatefulSet 注释已说明建议；Staging 单副本可接受，生产需规划 HA |

---

## 5. LOW 问题复审

| ID | 问题 | 原状态 | 当前状态 | 是否阻塞 Staging | 说明 |
|----|------|--------|----------|------------------|------|
| SEC-007 | 明文 MongoDB URL | 未修复 | **接受风险** | 否 | MongoDB 位于同 namespace，已启用 `--auth`；建议后续添加用户名/密码认证 |
| SEC-008 | 缺少 ResourceQuota | 未修复 | **建议后续** | 否 | 建议集群管理员统一配置，不在应用 manifest 中硬编码 |
| SEC-010 | 缺少安全头 | 未修复 | **建议后续** | 否 | 建议在 Ingress Controller 全局配置或 overlay 中添加 HSTS/X-Frame-Options/X-Content-Type-Options |

---

## 6. 新增发现

### 6.1 MongoDB 认证配置不匹配（潜在部署阻塞）

- `statefulset.yaml` 启动参数包含 `--auth`，但未配置 `MONGO_INITDB_ROOT_USERNAME/PASSWORD`
- `configmap.yaml` 与 `secret.yaml` 中的 `MONGODB_URL` 均为无认证格式 `mongodb://mongo:27017/aicbc`
- **风险**：应用连接 MongoDB 可能因认证要求而失败
- **处置**：已交由 小端 确认后端期望连接方式，需在 BE-6c 部署前给出方案

### 6.2 Redis seccompProfile 补充

- 原 `redis.yaml` Pod 级 `securityContext` 缺少 `seccompProfile`
- **处置**：team-lead 已补充 `seccompProfile: RuntimeDefault`

---

## 7. 部署前必须完成项

1. **SEC-009**：替换 Ingress 占位符域名与 TLS secret（Staging overlay）
2. **MongoDB 认证**：确认 `--auth` 与 `MONGODB_URL` 一致性方案
3. **Secret 注入**：确保 CI/CD 将 `secret.yaml` 中的 base64 占位符替换为真实密钥
4. **NetworkPolicy 验证**：确认集群 CNI 支持 NetworkPolicy（Calico/Cilium 等）

---

## 8. 结论

- **CRITICAL/HIGH 修复状态**：5/5 已修复或 Mitigated
- **Staging 部署 blocker**：SEC-009（Ingress 占位符）+ MongoDB 认证一致性
- **建议**：在解决上述 2 个 blocker 后，可执行 Staging 部署；MEDIUM/LOW 剩余项纳入生产强化 backlog

---

*复审完成时间: 2026-06-16*
*复审人: team-lead（代小安执行）*
