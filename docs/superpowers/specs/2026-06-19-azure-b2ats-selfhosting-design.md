> **版本**：v1.0
> **日期**：2026-06-19
> **负责人**：小维（DevOps/MLOps）
> **状态**：待审核

# AI_CBC 迁移至 Azure B2ats v2 自托管部署设计

## 1. 背景与目标

当前 AI_CBC 的 `.env.example` 和部分历史部署说明仍建议：

- Render 托管应用服务
- MongoDB Atlas 托管数据库
- Upstash Redis 托管缓存

这些外部托管服务在国内访问或成本控制上存在不便。本设计将 AI_CBC 迁移到用户自有的 **Azure B2ats v2** 云服务器上，使用自托管的 MongoDB 和 Redis，完全脱离 Render、MongoDB Atlas、Upstash Redis。

## 2. 约束条件

| 约束项 | 实际值 | 影响 |
|--------|--------|------|
| VM 规格 | Azure B2ats v2 | 2 vCPU， burstable 性能 |
| 内存 | 1 GiB | 必须大幅裁剪服务 |
| 架构 | x64 | 现有 Docker 镜像可直接使用 |
| 磁盘 | 64 GB 标准 SSD（免费额度） | 需控制日志和备份体积 |
| 出站流量 | 15 GB/月 | 需避免大量日志/监控数据外发 |
| Blob 存储 | 5 GB 免费 | 足够 MongoDB 备份使用 |
| 预算 | 零额外费用 | 不能购买更高规格服务 |

## 3. 架构设计

### 3.1 部署拓扑

```
Internet
   |
   v
[Nginx :80/:443]  ──(反向代理)──> [FastAPI API :8000]
                                       |
                                       v
                              [MongoDB :27017]
                              [Redis   :6379]
```

### 3.2 设计原则

1. **内存优先**：1 GiB 内存是硬约束，所有服务必须显式限制内存。
2. **核心最小化**：只保留用户可直接访问的核心路径（API + DB + Cache + HTTPS）。
3. **数据可恢复**：即使整机故障，也能从 Azure Blob 备份恢复 MongoDB 数据。
4. **不暴露内部端口**：MongoDB 和 Redis 只监听 Docker 内部网络，不映射到宿主机公网。
5. **镜像复用**：继续使用现有 `docker/Dockerfile` 和 GHCR 镜像仓库，不在 B2ats v2 上本地构建。

## 4. 运行服务与资源配置

### 4.1 保留服务

| 服务 | 用途 | 内存限制 | CPU 限制 | 说明 |
|------|------|----------|----------|------|
| `aicbc-api` | FastAPI 应用入口 | 384 MB | 0.8 | `API_WORKERS=1`，关闭调试 |
| `mongo` | 主数据存储 | 256 MB | 0.5 | WiredTiger 缓存限制为 128 MB |
| `redis` | 缓存 / Celery broker | 64 MB | 0.2 | `maxmemory 64mb` + `allkeys-lru` |
| `nginx` | HTTPS 反向代理 | 32 MB | 0.2 | Certbot 自动续期 |

**合计内存上限：约 736 MB**，剩余约 264 MB 给 Docker daemon、操作系统和 swap。

### 4.2 移除服务

以下服务在 1 GiB 内存下无法常驻运行：

- `worker`：Celery 后台任务处理
- `beat`：Celery 定时任务调度
- `prometheus`：指标采集
- `grafana`：指标可视化

> 后续升级到 4GB+ 机器时，可直接取消移除并恢复这些服务。

### 4.3 Swap 配置

必须在宿主机创建 2 GB swap 文件，防止 OOM：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

并在 `/etc/fstab` 中持久化：

```
/swapfile none swap sw 0 0
```

## 5. 网络与安全

### 5.1 Azure 网络安全组（NSG）

| 端口 | 协议 | 来源 | 用途 |
|------|------|------|------|
| 22 | TCP | 你的本地 IP | SSH 管理 |
| 80 | TCP | 0.0.0.0/0 | HTTP → HTTPS 重定向 |
| 443 | TCP | 0.0.0.0/0 | HTTPS 访问 |

**禁止**开放：

- 27017（MongoDB）
- 6379（Redis）
- 8000（API 直接访问）
- 9090（Prometheus）
- 3000（Grafana）

### 5.2 Docker 网络隔离

所有服务通过 Docker Compose 内部网络 `aicbc-network` 通信。MongoDB 和 Redis 不映射宿主机端口，仅 API 和 Nginx 对外提供服务。

### 5.3 HTTPS

使用 Certbot + Let's Encrypt 自动签发和续期证书。Nginx 负责：

- HTTP(80) → HTTPS(443) 强制重定向
- TLS 1.2+
- 反向代理到 `aicbc-api:8000`

## 6. 数据持久化与备份

### 6.1 本地持久化

使用 Docker named volume 或 bind mount：

- `mongo_data`：MongoDB 数据文件
- `redis_data`：Redis 持久化数据（可选，视 Redis 策略而定）
- `./ssl`：Let's Encrypt 证书
- `./backups`：临时备份文件

### 6.2 Azure Blob 备份

利用 Azure 12 个月免费的 5 GB Blob 存储：

1. 创建 Storage Account 和 Blob Container（如 `aicbc-backups`）。
2. 使用 `azcopy` 或 Azure CLI 上传 MongoDB dump。
3. 每日凌晨通过 cron 或独立备份容器执行：

```bash
mongodump --host mongo --out /backup/$(date +%Y%m%d_%H%M%S)
az storage blob upload-batch --destination aicbc-backups --source /backup
```

4. 保留策略：保留最近 7 天备份，超出删除。

### 6.3 恢复流程

```bash
# 从 Blob 下载最新备份
az storage blob download-batch --source aicbc-backups --destination /restore

# 恢复到 MongoDB
mongorestore --host mongo /restore/<latest_dump>
```

## 7. CI/CD 调整

### 7.1 镜像构建

继续使用 GitHub Actions 构建并推送镜像到 GHCR：

- 工作流：`.github/workflows/cd-staging.yml`
- 镜像：`ghcr.io/fromwordimport/aicbc:<sha>`
- 无需额外构建 ARM64 版本（B2ats v2 为 x64）

### 7.2 部署到 B2ats v2

新增一个轻量级部署步骤，通过 SSH 在服务器上执行：

```bash
cd /opt/aicbc
docker compose pull
docker compose up -d
```

由于 B2ats v2 只有 1 GB 内存，**不在服务器上执行 `docker compose build`**。

### 7.3 建议的 GitHub Secrets

| Secret | 用途 |
|--------|------|
| `AZURE_VM_IP` | B2ats v2 公网 IP |
| `AZURE_VM_USER` | SSH 用户名 |
| `AZURE_VM_SSH_KEY` | SSH 私钥 |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob 备份上传 |

## 8. 部署步骤（实施计划输入）

1. 创建 Azure B2ats v2 VM（Ubuntu 22.04 LTS，64GB SSD）。
2. 配置 NSG：开放 22/80/443，关闭其他端口。
3. 登录 VM，安装 Docker 和 Docker Compose。
4. 配置 2GB swap。
5. 克隆项目到 `/opt/aicbc`。
6. 创建 `.env` 并填入 LLM key 等机密。
7. 使用裁剪版 `docker-compose.azure-b2ats.yml` 启动服务。
8. 配置 Nginx + Certbot 获取 HTTPS 证书。
9. 配置 Azure Blob 备份 cron 任务。
10. 在 GitHub Actions 中添加 SSH 部署步骤。
11. 执行端到端验证（/health、创建研究、生成画像等）。

## 9. 已知限制与风险

| 限制/风险 | 说明 | 缓解措施 |
|-----------|------|----------|
| 单点故障 | 整机故障则服务全停 | 每日 Blob 备份，保留恢复脚本 |
| 无后台任务 | worker/beat 无法常驻 | 需要后台任务时临时手动启动；或后续升级机器 |
| 无监控栈 | 无法使用 Prometheus/Grafana | 使用 Azure Monitor 基础指标或手动查看日志 |
| 内存紧张 | 1 GiB 容易 OOM | 严格限制容器内存 + 启用 swap |
| CPU 突发限制 | B2ats v2 是 burstable | 避免持续高负载，LLM 调用在外部 API，本地主要是 I/O |
| 不适合生产 | 仅适合个人测试/小规模 demo | 明确告知用户，升级路径清晰 |

## 10. 后续升级路径

当预算允许或免费额度升级时，可按以下路径平滑扩展：

| 阶段 | 机器规格 | 变化 |
|------|----------|------|
| 当前 | B2ats v2（1GB） | 裁剪版，无 worker/监控 |
| 升级 1 | B2s（4GB） | 取消裁剪，恢复 worker + beat |
| 升级 2 | B2ms（8GB） | 恢复 Prometheus + Grafana |
| 升级 3 | 多台机器 | 应用与数据库分离，考虑 K8s |

## 11. 决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 部署平台 | Azure B2ats v2 | 用户已有 12 个月免费额度 |
| 编排方式 | Docker Compose | 与现有 `docker-compose.yml` 一致，运维简单 |
| 数据库 | 自托管 MongoDB 容器 | 替代 MongoDB Atlas，零额外费用 |
| 缓存 | 自托管 Redis 容器 | 替代 Upstash Redis，零额外费用 |
| 后台任务 | 暂不常驻 | 1GB 内存不足，避免 OOM |
| 监控 | 暂不部署 | 1GB 内存不足，使用 Azure 基础监控 |
| 备份 | Azure Blob | 5GB 免费额度足够 |
| HTTPS | Let's Encrypt + Certbot | 免费自动续期 |

## 12. 相关文档

- [`../../CLAUDE.md`](../../CLAUDE.md) — 项目全局规范
- [`../../docker/CLAUDE.md`](../../docker/CLAUDE.md) — 容器构建规范
- [`../../k8s/CLAUDE.md`](../../k8s/CLAUDE.md) — Kubernetes 部署说明（后续升级参考）
- [`../../docker-compose.yml`](../../docker-compose.yml) — 完整版 Compose 参考
- [`../../.env.example`](../../.env.example) — 环境变量模板
