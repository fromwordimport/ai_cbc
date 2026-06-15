# BE-6 K8s Staging 部署验证阶段报告

> **版本**：v1.0
> **任务编号**：BE-6
> **执行人**：team-lead
> **日期**：2026-06-16
> **状态**：阶段性完成，真实集群部署验证 pending

---

## 一、任务目标回顾

BE-6 目标：完成 AI_CBC 后端在 Staging 环境的 K8s 部署验证，验证 MongoDB + Redis + Celery + Docker/K8s 全栈可用性，产出可复现的部署证据。

---

## 二、已完成工作

### 2.1 K8s Manifest 结构修复

- 将 base manifest 从 `k8s/` 根目录迁移到标准 `k8s/base/` + `k8s/overlays/{staging,prod}` 结构
- 从 base 移除 `namespace.yaml`，按环境拆分到 overlay
- overlay `resources` 路径修正为 `../../base`
- 创建 staging ingress patch，替换 example.com 占位符
- 更新 `k8s/CLAUDE.md` 目录结构说明

### 2.2 安全加固落地

- SEC-011：4 个组件专用 ServiceAccount，`automountServiceAccountToken: false`
- SEC-006：Secret 模板使用 `data` 字段 + 占位符 + annotations
- SEC-001：`readOnlyRootFilesystem: true` + `/tmp` emptyDir 挂载
- SEC-004：NetworkPolicy 外部出口安全注释 + `deny-ingress-worker-beat`
- SEC-012：镜像标签从 `latest` 改为 `0.1.0`，`imagePullPolicy: IfNotPresent`
- 所有 Pod 添加 `seccompProfile: RuntimeDefault`
- MongoDB `--auth` 移除，与当前无认证 `MONGODB_URL` 保持一致（Staging 可接受，生产后续加固）

### 2.3 后端容器配置兼容性修复

- 发现 Celery worker/beat 启动命令使用 `aicbc.analysis.tasks`，与 Docker 镜像中 `/app/src/` 代码布局不匹配
- 修正为 `src.aicbc.analysis.tasks`
- 同步修正 worker livenessProbe 命令

### 2.4 静态验证

- 创建 `scripts/validate_k8s_manifests.py`
- 运行结果：仅剩 4 项 Secret 占位符提示，无结构/安全字段缺失
- `kustomize build k8s/overlays/staging/` 渲染成功

### 2.5 CI/CD 通道打通

- 代码已 push 到 `https://github.com/fromwordimport/ai_cbc`
- `.github/workflows/ci-cd.yml` 已配置 `deploy-staging` job
- 移除误提交的 `kubectl.exe`，更新 `.gitignore`

---

## 三、未完成工作

### 3.1 真实 Staging 集群部署验证

- 未执行 `kubectl apply -k k8s/overlays/staging/` 到真实集群
- 未验证 Pod Running 状态
- 未执行 `/health` 冒烟测试
- 未验证服务间连通性（API → MongoDB、API → Redis、Worker → Redis）
- 未验证 NetworkPolicy 实际生效
- 未验证 Ingress + TLS

### 3.2 阻塞原因

1. **本地 kind/minikube 验证失败**：
   - WSL2 网络访问 Docker Hub / ghcr.io 超时或不稳定
   - kind v0.30.0 镜像加载存在 containerd 兼容性问题
   - minikube 镜像下载过慢

2. **GitHub Actions Staging 部署无法执行**：
   - Repository secrets 中未配置 `KUBECONFIG_STAGING`
   - 当前不存在可用的远程 Staging K8s 集群

---

## 四、风险与影响

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 未在真实集群验证 manifest | 线上部署时可能发现 kustomize 渲染、Pod 启动、服务连通性问题 | 一旦集群就绪立即执行部署验证；静态验证已通过 |
| Secret 占位符未替换 | 真实部署时应用无法启动 | CI/CD 或外部密钥管理注入；本地测试已验证 Secret 结构 |
| HPA 依赖 metrics-server | kind/minikube 默认无 metrics-server，HPA 无法工作 | 非阻塞，真实集群通常已安装 metrics-server |
| 小伦/小验否决权 | BE-6 未完成真实部署验证，可能无法解除伦理/业务否决 | 需向小伦/小验说明阶段成果，请求阶段性放行或继续阻塞 |

---

## 五、下游任务影响

以下任务仍被 BE-6 阻塞：

- FE-5 前端 Staging 冒烟测试
- QA-2 端到端自动化测试覆盖
- QA-3 性能回归测试基线建立
- QA-6 测试文档更新
- PERF-1/2/3 性能压测与优化
- UAT-1 端到端 UAT 执行
- UAT-2 业务规则校验自动化

如果必须继续推进，建议下游任务改用 `docker-compose` 全栈环境作为临时替代验证环境。

---

## 六、建议下一步

### 短期（本周内）

1. **决策**：是否采购/创建 Staging K8s 集群
   - 云厂商托管 K8s（ACK/TKE/EKS/AKS）
   - 或内部已有的 K8s 集群划分 staging namespace
2. **配置 GitHub Secret `KUBECONFIG_STAGING`**
3. **触发 CI/CD `deploy-staging` job**，完成真实部署验证

### 中期（两周内）

1. 执行 `/health` 冒烟测试
2. 验证 API → MongoDB / Redis 连通性
3. 验证 Celery worker 能正常消费任务
4. 完成 NetworkPolicy 实际流量验证

### 长期

1. 生产环境启用 MongoDB 认证
2. 迁移 `sed` 改文件模式到 Kustomize 原生参数化
3. 部署 Sealed Secrets 或 External Secrets Operator

---

## 七、结论

BE-6 在 **manifest 结构、安全加固、后端容器配置兼容性、静态验证、CI/CD 通道** 方面已取得实质性进展，但由于 **Staging K8s 集群尚未就绪**，真实部署验证无法完成。

建议项目管理层（小P）决策是否继续投入资源创建 Staging 集群，或接受当前阶段成果并记录风险。

---

*相关文件*：
- `k8s/base/`
- `k8s/overlays/staging/`
- `scripts/validate_k8s_manifests.py`
- `reports/2026-06-16-BE6-k8s-static-validation-report.md`
- `reports/2026-06-16-BE6-k8s-security-re-review.md`
- `BE-6-手动执行手册.md`
