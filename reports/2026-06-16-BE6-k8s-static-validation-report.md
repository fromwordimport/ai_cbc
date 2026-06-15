# K8s Manifest 静态验证报告

> **日期**: 2026-06-16
> **执行**: team-lead
> **脚本**: `scripts/validate_k8s_manifests.py`
> **目标**: 在无 kubectl/kustomize/集群的本地环境中，对 `k8s/base/` 与 `k8s/overlays/` 进行离线结构与安全检查

---

## 1. 执行摘要

使用 Python + PyYAML 编写的静态验证脚本对 K8s manifest 进行了检查。脚本覆盖：

- Kustomize base 与 overlays 的资源引用完整性
- Deployment/StatefulSet 的 ServiceAccount、SecurityContext、seccompProfile、capabilities、readOnlyRootFilesystem 等安全字段
- Secret 是否使用 `data` 字段
- NetworkPolicy 关键资源是否存在
- 镜像标签与 imagePullPolicy

**结果**：脚本运行成功，发现 4 项预期内提示（非阻塞）：
- 4 项 Secret 占位符提示（由 CI/CD 或外部密钥管理注入真实值）

**真实 manifest 结构问题**：本次静态检查未发现结构缺失或安全字段遗漏。

---

## 2. 详细输出

```
== AI_CBC K8s Manifest Static Validator ==

Found 4 issue(s):

[secret]
  - Secret/aicbc-secrets: ANTHROPIC_API_KEY still contains placeholder value
  - Secret/aicbc-secrets: OPENAI_API_KEY still contains placeholder value
  - Secret/aicbc-secrets: SECRET_KEY still contains placeholder value
  - Secret/aicbc-secrets: REDIS_PASSWORD still contains placeholder value
```

**说明**：base kustomization 与 staging/prod overlay 均已使用显式版本标签；CI/CD 部署时通过 sed 将 `newTag` 替换为 commit SHA。Secret 中保留 base64 占位符，供 CI/CD 或外部密钥管理注入。

---

## 3. 问题说明

### 3.1 镜像标签（预期内）

- **设计**: base kustomization 与 staging/prod overlay 均使用显式版本 `0.1.0`，由 CI/CD 在部署阶段通过 sed 替换为具体 commit SHA
- **部署前检查项**: 确认 CI/CD 已将 overlay 中的 `newTag: 0.1.0` 替换为 `newTag: <git-sha>`

### 3.2 Secret 占位符（预期内）

- **位置**: `k8s/base/secret.yaml`
- **设计**: 使用 base64 编码的占位符值，注释明确说明需通过 CI/CD、Sealed Secrets 或 External Secrets Operator 注入真实值
- **部署前检查项**: 确认真实密钥已通过安全方式注入，未将明文 Secret 提交到 Git

---

## 4. 与真实集群验证的边界

本静态验证**不能替代**真实 K8s 集群部署验证。以下问题只能在线上集群发现：

1. **Kustomize 渲染正确性**: `kubectl kustomize k8s/overlays/staging` 的最终 YAML 是否符合预期
2. **Pod 启动与就绪**: 容器镜像拉取、启动探针、就绪探针是否通过
3. **服务间连通性**: API → MongoDB、API → Redis、Worker → Redis 等连接是否正常
4. **NetworkPolicy 实际生效**: CNI 插件是否正确拦截/放行流量
5. **Ingress 与 TLS**: 域名解析、证书配置、外部可达性

---

## 5. 结论与建议

- **静态验证**: 通过（仅预期内 CI/CD 占位符提示）
- **下一步**: 尽快获取 Staging 集群或本地 kind/minikube 环境，执行真实 `kubectl apply -k k8s/overlays/staging` 验证
- **短期可行方案**: 在 GitHub Actions 等 Linux runner 上执行 Kustomize 渲染和（如有集群凭据）远程部署

---

*报告生成时间: 2026-06-16*
*验证脚本: `scripts/validate_k8s_manifests.py`*
