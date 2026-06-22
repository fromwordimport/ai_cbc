# BE-6 手动执行手册

> **版本**：v1.0
> **任务**：BE-6 K8s Staging 部署验证
> **路径**：B（本地 kind/minikube 兜底验证）
> **适用对象**：项目维护者 / DevOps 工程师
> **日期**：2026-06-16

---

## 一、目标与范围

本手册用于在没有正式远程 Staging 集群的情况下，在本地 WSL2（Ubuntu 22.04/24.04）或 Linux VM 中完成以下验证：

1. 使用 `kind` 或 `minikube` 创建本地 K8s 集群
2. 渲染并应用 `k8s/overlays/staging/` 配置
3. 验证所有 Pod 进入 Running 状态
4. 验证 API `/health` 端点可访问
5. 记录阻塞问题并反馈给 team-lead

**不验证项**：外部域名解析、TLS 证书、真实 LLM API 调用（本地环境通常无 LLM key）。

---

## 二、前置条件

### 2.1 操作系统

- Windows 11 + WSL2（Ubuntu 22.04/24.04）
- 或任意 Linux x86_64 VM
- 至少 8GB 可用内存、20GB 磁盘空间

### 2.2 必须安装的软件

| 软件 | 版本要求 | 安装命令示例（Ubuntu/WSL2） |
|------|---------|---------------------------|
| Docker | 24.x+ | `sudo apt update && sudo apt install -y docker.io` |
| kubectl | v1.30.x+ | [官方安装指南](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/) |
| kind | v0.23.x+ | `curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64 && chmod +x ./kind && sudo mv ./kind /usr/local/bin/` |
| kustomize | v5.x+ | `curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash && sudo mv kustomize /usr/local/bin/` |

验证安装：

```bash
docker --version
kubectl version --client
kind version
kustomize version
```

### 2.3 代码仓库

确保本地已 clone 本仓库，并切换到包含 BE-6 修复的分支（当前为 `master`）：

```bash
cd AI_CBC
git log --oneline -3
# 应看到：
# 663f285 chore(reports): remove outdated BE-6 k8s staging validation v2 report
# e9024df fix(k8s): correct Kustomize base/overlay structure for staging deploy
```

---

## 三、路径 B：本地 kind 集群验证

### 3.1 创建 kind 集群

创建配置文件 `kind-config.yaml`：

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 80
        hostPort: 8080
        protocol: TCP
      - containerPort: 443
        hostPort: 8443
        protocol: TCP
  - role: worker
  - role: worker
```

启动集群：

```bash
kind create cluster --name aicbc-staging --config kind-config.yaml
kubectl cluster-info --context kind-aicbc-staging
```

### 3.2 安装必要组件

本地 kind 集群默认没有 Ingress controller 和 cert-manager。为简化验证，**先跳过 Ingress/TLS**，直接通过 NodePort/Port-forward 访问 API。

如需验证 Ingress，可安装 NGINX Ingress：

```bash
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=90s
```

cert-manager 在本地通常无法申请真实 Let's Encrypt 证书，可跳过或安装自签 CA 版本。

### 3.3 准备本地 Secret（关键步骤）

由于 `k8s/base/secret.yaml` 已从 `k8s/base/kustomization.yaml` 的 resources 列表中移除，base 渲染结果不再包含 Secret。本地验证时必须手动创建真实或测试 Secret。

**方案 A：使用测试密钥（推荐本地验证）**

```bash
kubectl create namespace aicbc-staging
kubectl create secret generic aicbc-secrets \
  --namespace aicbc-staging \
  --from-literal=ANTHROPIC_API_KEY=test-key \
  --from-literal=OPENAI_API_KEY=test-key \
  --from-literal=SECRET_KEY=test-secret-key \
  --from-literal=REDIS_PASSWORD=test-redis-password
```

**方案 B：从 base secret 模板修改后 apply**

如需验证模板渲染，可复制模板并替换占位符：

```bash
# 不推荐直接修改已跟踪文件
mkdir -p /tmp/aicbc-local
cp k8s/base/secret.yaml /tmp/aicbc-local/secret.yaml
# 手动编辑 /tmp/aicbc-local/secret.yaml，将 base64 占位符替换为真实值
kubectl apply -f /tmp/aicbc-local/secret.yaml --namespace aicbc-staging
```

> **注意**：请勿将真实密钥提交到 Git。

### 3.4 渲染并应用 Kustomize 配置

#### 3.4.1 先本地渲染检查

```bash
kustomize build k8s/overlays/staging/ > /tmp/aicbc-staging-rendered.yaml
```

检查输出：

```bash
# 确认 namespace 正确
head -50 /tmp/aicbc-staging-rendered.yaml

# 确认镜像标签（如未通过 CI 替换，可能仍是 latest 或 0.1.0）
grep "image:" /tmp/aicbc-staging-rendered.yaml
```

#### 3.4.2 本地替换镜像标签（可选）

本地没有 CI/CD 自动替换 `newTag`，可按需手动修改 overlay：

```bash
# 示例：将 tag 替换为本地测试标签
sed -i 's/newTag: latest/newTag: 0.1.0/g' k8s/overlays/staging/kustomization.yaml
sed -i 's/newTag: 0.1.0/newTag: local-test/g' k8s/overlays/staging/kustomization.yaml
```

> 修改后不要提交到 Git，验证完成后用 `git checkout k8s/overlays/staging/kustomization.yaml` 还原。

#### 3.4.3 应用配置

```bash
kubectl apply -k k8s/overlays/staging/
```

预期输出：创建 namespace、configmap、serviceaccount、service、deployment、statefulset、networkpolicy、ingress 等资源。注意：secret 需已在 namespace 中提前创建，不再由 base kustomization 渲染。

### 3.5 验证部署状态

#### 3.5.1 查看所有资源

```bash
kubectl get all -n aicbc-staging
```

#### 3.5.2 等待 Pod Running

```bash
kubectl wait --for=condition=ready pod \
  --selector=app.kubernetes.io/name=aicbc \
  --namespace aicbc-staging \
  --timeout=300s

# 或逐个检查
kubectl rollout status deployment/aicbc-api -n aicbc-staging --timeout=300s
kubectl rollout status deployment/aicbc-worker -n aicbc-staging --timeout=300s
kubectl rollout status deployment/aicbc-beat -n aicbc-staging --timeout=300s
kubectl rollout status statefulset/mongo -n aicbc-staging --timeout=300s
kubectl rollout status deployment/redis -n aicbc-staging --timeout=300s
```

#### 3.5.3 查看 Pod 日志

```bash
kubectl logs -n aicbc-staging deployment/aicbc-api --tail=100
kubectl logs -n aicbc-staging deployment/aicbc-worker --tail=100
kubectl logs -n aicbc-staging deployment/aicbc-beat --tail=100
kubectl logs -n aicbc-staging statefulset/mongo --tail=100
```

### 3.6 执行 /health 冒烟测试

#### 3.6.1 通过 Port-forward 访问

```bash
kubectl port-forward -n aicbc-staging service/aicbc-api 8080:80
```

另起一个终端：

```bash
curl -s http://localhost:8080/health | jq .
```

#### 3.6.2 通过 kind 节点端口访问（如配置了 extraPortMappings）

如果安装了 Ingress controller 并映射了端口：

```bash
curl -s http://localhost:8080/health
```

### 3.7 常见问题排查

| 现象 | 可能原因 | 排查命令 |
|------|---------|---------|
| Pod 卡在 Pending | 资源不足 / PVC 未绑定 | `kubectl describe pod -n aicbc-staging <pod-name>` |
| ImagePullBackOff | 镜像不存在或无法拉取 | `kubectl describe pod -n aicbc-staging <pod-name>` |
| CrashLoopBackOff | 应用启动失败 / 环境变量缺失 | `kubectl logs -n aicbc-staging <pod-name> --previous` |
| 无法连接 MongoDB | MONGODB_URL 配置错误 / NetworkPolicy 阻断 | `kubectl exec -n aicbc-staging deployment/aicbc-api -- env \| grep MONGODB` |
| 无法连接 Redis | REDIS_URL 或 REDIS_PASSWORD 错误 | `kubectl exec -n aicbc-staging deployment/aicbc-api -- env \| grep REDIS` |
| NetworkPolicy 阻断 | 默认拒绝策略过严 | 临时删除 network-policy.yaml 中的 default-deny-all 重试 |

### 3.8 清理本地集群

验证完成后清理资源：

```bash
kind delete cluster --name aicbc-staging
```

---

## 四、路径 A 备选：触发 CI/CD 远程 Staging 部署

如果路径 B 验证通过，或你希望直接验证远程 Staging，可执行此路径。

### 4.1 确认 GitHub Secret

1. 打开 GitHub repo → Settings → Secrets and variables → Actions
2. 检查是否存在 `KUBECONFIG_STAGING`
3. 如不存在，准备 kubeconfig 文件并 base64 编码：

```bash
cat ~/.kube/config-staging | base64 -w 0
```

4. 将编码后的字符串粘贴为 `KUBECONFIG_STAGING` 的值

### 4.2 触发部署

将当前分支的 BE-6 修复 push 到 `main` 或 `master`：

```bash
git checkout main
# 或 git checkout master
git merge master  # 假设当前修复在 master
git push origin main
```

CI/CD 将自动执行：

1. `CI` workflow：Preflight / Quality / Security / Unit / Red Team / Frontend / validate-k8s
2. `CD Staging` workflow：构建并推送镜像，部署到 Staging
3. 等待 rollout
4. 执行 `/health` 冒烟测试

> 生产部署请使用 `CD Azure B2ats v2` workflow（push 到 `master` 自动触发，也可手动触发）。原 `CD Production` workflow（基于 kubectl）已删除。

### 4.3 查看部署结果

在 GitHub Actions 中查看 `CD Staging` workflow 的 `deploy-staging` job 输出，确认：

```
kubectl rollout status deployment/aicbc-api --namespace=aicbc-staging --timeout=300s
kubectl rollout status deployment/aicbc-worker --namespace=aicbc-staging --timeout=300s
kubectl rollout status deployment/aicbc-beat --namespace=aicbc-staging --timeout=300s
```

均返回 `successfully rolled out`。

---

## 五、产出物与汇报

完成路径 B 或路径 A 后，请向 team-lead 提供以下信息：

1. 执行环境（OS、kind/minikube 版本、kubectl 版本）
2. 是否成功渲染 `k8s/overlays/staging/`
3. 各 Pod 是否 Running（附 `kubectl get pods -n aicbc-staging` 输出）
4. `/health` 响应结果
5. 遇到的错误及日志片段
6. 是否建议解除 FE-5 / QA-2 / PERF-1 / UAT-1 / UAT-2 的阻塞

---

## 六、相关文件索引

| 文件 | 说明 |
|------|------|
| `k8s/overlays/staging/kustomization.yaml` | Staging overlay 入口 |
| `k8s/base/kustomization.yaml` | Base manifest 入口 |
| `scripts/validate_k8s_manifests.py` | 静态验证脚本（无需集群） |
| `reports/2026-06-16-BE6-k8s-static-validation-report.md` | 静态验证报告 |
| `reports/2026-06-16-BE6-k8s-security-re-review.md` | 安全复审报告 |
| `.github/workflows/ci.yml` | CI 流水线定义（质量门禁、测试、前端构建、K8s 校验） |
| `.github/workflows/cd-staging.yml` | Staging 部署流水线 |
| `.github/workflows/cd-azure-b2ats.yml` | 生产部署流水线（SSH 到 Azure VM） |

---

*本手册由 team-lead 生成，供 BE-6 本地验证使用。*
