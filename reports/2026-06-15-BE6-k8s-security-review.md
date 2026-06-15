# K8s Staging 部署安全审查报告

> **日期**: 2026-06-15
> **审查人**: 小安 (安全工程师)
> **范围**: k8s/ 目录下所有 manifest 文件
> **目标**: 为 BE-6 K8s Staging 部署验证提供安全审查意见

---

## 1. 执行摘要

本次审查覆盖 8 个 K8s manifest 文件。整体安全配置处于**中等水平**，Pod SecurityContext 基本到位，但存在若干需要修复的问题。共识别 **2 个 CRITICAL、3 个 HIGH、4 个 MEDIUM、3 个 LOW** 级别问题。

---

## 2. 详细发现

### 2.1 Pod/Container SecurityContext

#### SEC-001: `readOnlyRootFilesystem: false` 在 API/Worker/Beat 容器上 [HIGH]

**文件**: `deployment.yaml:96`, `worker-deployment.yaml:88`, `beat-deployment.yaml:73`

**问题**: API、Worker、Beat 三个 Deployment 的容器级 `securityContext` 中 `readOnlyRootFilesystem` 设置为 `false`。这意味着容器可以写入根文件系统，增加了运行时攻击面（如恶意代码写入 /tmp、/etc 等）。

**建议**:
1. 将 `readOnlyRootFilesystem` 改为 `true`
2. 为需要写入的目录（如 `/tmp`、`/var/log`）挂载 `emptyDir` 卷
3. 对 Celery beat 的 schedule 文件使用持久化卷或 ConfigMap

**优先级**: HIGH

---

#### SEC-002: MongoDB StatefulSet `readOnlyRootFilesystem: false` [MEDIUM]

**文件**: `statefulset.yaml:94`

**问题**: MongoDB 容器允许写入根文件系统。虽然 MongoDB 数据目录已挂载 PVC，但运行时仍可能写入其他路径。

**建议**: 评估是否可将 `readOnlyRootFilesystem` 设为 `true`，并将必要的运行时目录（如 /tmp）挂载为 emptyDir。

**优先级**: MEDIUM

---

#### SEC-003: 缺少 `seccompProfile` 配置 [MEDIUM]

**文件**: 所有 Deployment 和 StatefulSet

**问题**: 所有 Pod/Container 均未设置 `seccompProfile`。默认情况下 Kubernetes 使用 `RuntimeDefault`，但显式声明可确保一致性并防止集群级别配置被覆盖。

**建议**: 在 Pod 级 `securityContext` 中添加：
```yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

**优先级**: MEDIUM

---

### 2.2 NetworkPolicy

#### SEC-004: 外部出口规则过于宽泛（0.0.0.0/0:80/443） [HIGH]

**文件**: `network-policy.yaml:65-70`, `100-105`

**问题**: `allow-api-egress` 和 `allow-worker-egress` 中，到外部 LLM API 的出口规则使用 `to: []`（即 0.0.0.0/0），允许访问任意 IP 的 80/443 端口。这超出了实际需要（只需访问 Anthropic、OpenAI 等特定 API 端点）。

**建议**:
1. 使用 Egress 网络策略的 `to` 段配合 IPBlock 限制仅允许已知 LLM API 的 CIDR
2. 或考虑使用 Egress Gateway / 代理来控制外部访问
3. 至少应注释说明此放宽的合理性

**优先级**: HIGH

---

#### SEC-005: Worker 和 Beat 缺少 Ingress 限制 [MEDIUM]

**文件**: `network-policy.yaml`

**问题**: NetworkPolicy 仅限制 API 组件的 Ingress，Worker 和 Beat 组件没有专门的 Ingress 限制。Worker 和 Beat 不需要接收外部流量，应默认拒绝所有 Ingress。

**建议**: 为 worker 和 beat 添加默认拒绝 Ingress 的 NetworkPolicy：
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-ingress-worker-beat
  namespace: aicbc-prod
spec:
  podSelector:
    matchExpressions:
      - key: app.kubernetes.io/component
        operator: In
        values: [worker, beat]
  policyTypes:
    - Ingress
```

**优先级**: MEDIUM

---

### 2.3 Secret 管理

#### SEC-006: Secret 模板包含硬编码占位符 [CRITICAL]

**文件**: `secret.yaml:27-31`

**问题**: Secret 模板文件中包含 `stringData` 形式的占位符值（`"REPLACE_WITH_ACTUAL_KEY"`）。虽然文件头部有警告注释，但：
1. `stringData` 在 etcd 中以 base64 存储，不如 `data` 字段明确
2. 占位符值可能在 CI/CD 流程中被意外应用到集群
3. 缺少 `kubeseal` 或 External Secrets Operator 的集成说明

**建议**:
1. 将 `stringData` 改为 `data`（强制 base64 编码，增加误用难度）
2. 在 CI/CD 中集成 `kubeseal` 或 External Secrets Operator
3. 添加 `metadata.annotations` 标记为模板：`sealedsecrets.bitnami.com/managed: "false"`

**优先级**: CRITICAL

---

#### SEC-007: Secret 包含明文 MongoDB URL [LOW]

**文件**: `secret.yaml:30`

**问题**: `MONGODB_URL` 以明文形式存储在 Secret 中，且值为 `mongodb://mongo:27017/aicbc`（无认证）。虽然 MongoDB 在同一 namespace 内，但缺少认证增加了横向移动风险。

**建议**:
1. 为 MongoDB 启用认证（用户名/密码）
2. 将认证凭据单独存储在 Secret 中
3. 更新 MONGODB_URL 为 `mongodb://username:password@mongo:27017/aicbc`

**优先级**: LOW

---

### 2.4 Resource Limits

#### SEC-008: 缺少 ResourceQuota 和 LimitRange [LOW]

**文件**: 全局

**问题**: Namespace 级别未设置 ResourceQuota 和 LimitRange。单个恶意/故障 Pod 可能耗尽 namespace 资源，影响其他组件。

**建议**: 添加 `resource-quota.yaml` 和 `limit-range.yaml`：
```yaml
# ResourceQuota
apiVersion: v1
kind: ResourceQuota
metadata:
  name: aicbc-quota
  namespace: aicbc-prod
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "20"
---
# LimitRange
apiVersion: v1
kind: LimitRange
metadata:
  name: aicbc-limits
  namespace: aicbc-prod
spec:
  limits:
    - default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      type: Container
```

**优先级**: LOW

---

### 2.5 Ingress

#### SEC-009: Ingress 使用 example.com 域名 [MEDIUM]

**文件**: `ingress.yaml:21-24`

**问题**: Ingress 配置使用 `api.aicbc.example.com` 作为占位符域名。在 staging 环境中应使用实际域名，否则 TLS 证书和 DNS 解析无法正常工作。

**建议**:
1. Staging overlay 应替换为实际 staging 域名（如 `api-staging.aicbc.internal`）
2. Prod overlay 使用生产域名
3. 或添加注释明确说明此为模板，部署前必须替换

**优先级**: MEDIUM

---

#### SEC-010: Ingress 注解缺少安全头 [LOW]

**文件**: `ingress.yaml:8-16`

**问题**: Ingress 注解缺少安全相关配置：
- 缺少 `nginx.ingress.kubernetes.io/configuration-snippet` 添加 HSTS 头
- 缺少 `nginx.ingress.kubernetes.io/proxy-buffering: "on"`
- rate-limit 注解存在但值较低（100/min），需评估是否足够

**建议**:
```yaml
annotations:
  nginx.ingress.kubernetes.io/configuration-snippet: |
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
```

**优先级**: LOW

---

### 2.6 ServiceAccount 权限

#### SEC-011: 使用默认 ServiceAccount [CRITICAL]

**文件**: 所有 Deployment 和 StatefulSet

**问题**: 所有 Pod 均未指定 `serviceAccountName`，默认使用 namespace 的 `default` ServiceAccount。`default` SA 通常绑定了过多的权限（如读取所有 Secret、访问 API Server 等），违反最小权限原则。

**建议**:
1. 为每个组件创建专用 ServiceAccount：
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: aicbc-api
  namespace: aicbc-prod
automountServiceAccountToken: false  # 除非需要访问 K8s API
---
# 在 Deployment 中引用
spec:
  template:
    spec:
      serviceAccountName: aicbc-api
      automountServiceAccountToken: false
```
2. 禁用 `automountServiceAccountToken`（除非组件需要访问 K8s API）
3. 创建 RBAC Role/RoleBinding 限制 API 访问权限

**优先级**: CRITICAL

---

### 2.7 其他安全问题

#### SEC-012: `imagePullPolicy: Always` 配合 `latest` 标签 [HIGH]

**文件**: `deployment.yaml:39`, `worker-deployment.yaml:36`, `beat-deployment.yaml:34`

**问题**: 所有应用容器使用 `image: ghcr.io/fromwordimport/aicbc:latest` 和 `imagePullPolicy: Always`。这导致：
1. 镜像不可变性无法保证（每次拉取可能不同）
2. 回滚困难（无法确定具体版本）
3. 与 Kustomize overlay 的 `images.newTag` 功能冲突

**建议**:
1. Base manifest 中使用明确版本标签（如 `0.1.0`）
2. 由 CI/CD 或 Kustomize overlay 在部署时替换为具体版本
3. `imagePullPolicy: IfNotPresent`（显式标签时）

**优先级**: HIGH

---

#### SEC-013: MongoDB 单副本无高可用 [MEDIUM]

**文件**: `statefulset.yaml:34`

**问题**: MongoDB StatefulSet 设置 `replicas: 1`，单点故障风险。虽然文件注释提到"考虑 MongoDB replica set"，但生产环境应落实。

**建议**:
1. 评估使用云托管 MongoDB（Atlas、DocumentDB）
2. 或部署 MongoDB Community Operator 管理 replica set
3. 至少配置定期备份（如 Velero、mongodump CronJob）

**优先级**: MEDIUM

---

## 3. 问题汇总表

| ID | 问题 | 优先级 | 文件 | 修复难度 |
|----|------|--------|------|----------|
| SEC-011 | 使用默认 ServiceAccount | CRITICAL | 所有 | 中 |
| SEC-006 | Secret 模板含硬编码占位符 | CRITICAL | secret.yaml | 低 |
| SEC-001 | readOnlyRootFilesystem: false | HIGH | deployment/worker/beat | 中 |
| SEC-004 | 外部出口过于宽泛 | HIGH | network-policy.yaml | 中 |
| SEC-012 | latest 标签 + Always pull | HIGH | 所有 Deployment | 低 |
| SEC-002 | MongoDB readOnlyRootFilesystem | MEDIUM | statefulset.yaml | 中 |
| SEC-003 | 缺少 seccompProfile | MEDIUM | 所有 | 低 |
| SEC-005 | Worker/Beat 缺少 Ingress 限制 | MEDIUM | network-policy.yaml | 低 |
| SEC-009 | example.com 占位符域名 | MEDIUM | ingress.yaml | 低 |
| SEC-013 | MongoDB 单副本 | MEDIUM | statefulset.yaml | 高 |
| SEC-007 | 明文 MongoDB URL | LOW | secret.yaml | 低 |
| SEC-008 | 缺少 ResourceQuota | LOW | 全局 | 低 |
| SEC-010 | 缺少安全头 | LOW | ingress.yaml | 低 |

---

## 4. 修复建议优先级

### 立即修复（CRITICAL + HIGH）

1. **SEC-011**: 创建专用 ServiceAccount，禁用 automountServiceAccountToken
2. **SEC-006**: 将 Secret 模板改为 `data` 字段，集成 kubeseal/ESO
3. **SEC-001**: 设置 `readOnlyRootFilesystem: true`，为 /tmp 挂载 emptyDir
4. **SEC-004**: 限制外部出口到已知 LLM API 的 IP 范围
5. **SEC-012**: 使用显式版本标签替代 latest

### 短期修复（MEDIUM）

6. **SEC-003**: 添加 seccompProfile: RuntimeDefault
7. **SEC-005**: 为 worker/beat 添加默认拒绝 Ingress 的 NetworkPolicy
8. **SEC-009**: 替换 example.com 为实际域名
9. **SEC-002**: 评估 MongoDB readOnlyRootFilesystem
10. **SEC-013**: 规划 MongoDB 高可用方案

### 长期改进（LOW）

11. **SEC-007**: 为 MongoDB 启用认证
12. **SEC-008**: 添加 ResourceQuota 和 LimitRange
13. **SEC-010**: 添加 Ingress 安全头注解

---

## 5. 结论

当前 K8s 配置在 Pod SecurityContext 方面基本到位（runAsNonRoot、runAsUser、allowPrivilegeEscalation、capabilities drop），但存在以下关键安全缺口：

1. **ServiceAccount 权限过宽**（CRITICAL）：使用默认 SA 是最大风险，应立即修复
2. **Secret 管理不规范**（CRITICAL）：模板文件存在误用风险
3. **运行时文件系统可写**（HIGH）：增加攻击面
4. **网络出口过于宽泛**（HIGH）：应限制到已知端点
5. **镜像版本不可追溯**（HIGH）：latest 标签不利于安全审计

建议小维在 BE-6 报告中包含以上安全审查意见，并优先处理 CRITICAL 和 HIGH 级别问题。

---

*审查完成时间: 2026-06-15*
*审查人: 小安 (安全工程师)*
