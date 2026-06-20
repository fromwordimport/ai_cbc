> **版本**：v1.0
> **日期**：2026-06-20
> **负责人**：小维（DevOps/MLOps）
> **状态**：待审核

# AI_CBC Azure B2 系列四机部署与上手操作设计

## 1. 背景与目标

用户已获得四台 Azure 虚拟机：

- **B2pts v2（Arm 架构）**：Linux × 1、Windows × 1
- **B2ats v2（AMD x86 架构）**：Linux × 1、Windows × 1

用户完全不懂服务器配置，当前处于开发阶段，未来会转为测试和演示阶段。核心需求：

1. 从公网通过 HTTPS 访问 AI_CBC 平台。
2. 开发时 1 人使用，演示时 2-3 人同时登录。
3. 至少保留一个演示案例数据长期可用。
4. 操作简单，维护负担低。

本设计在 [`2026-06-19-azure-b2ats-selfhosting-design.md`](2026-06-19-azure-b2ats-selfhosting-design.md) 的基础上，针对用户“四机可用但希望先跑通一台”的场景，给出一个最简、最稳的落地方案。

## 2. 约束与假设

| 约束项 | 实际值 | 影响 |
|--------|--------|------|
| 可用 VM | 4 台 B2 系列 | 资源分散，优先集中在一台 simplest path |
| B2ats v2 架构 | x64 | Docker 镜像和 Python 数据科学库兼容性最好 |
| B2pts v2 架构 | Arm64 | pymc/PyTensor 可能存在兼容风险，先不用于生产服务 |
| Windows Server | 2 台 | 跑 Linux 容器需 WSL2，增加维护成本，先不用于生产服务 |
| 并发 | 1-3 人 | 单台 B2ats v2 足够 |
| 公网访问 | 是 | 必须 HTTPS、限制端口、启用后端认证 |
| 域名 | 已有二级域名 | 可用 Let's Encrypt 免费证书 |

## 3. 服务器角色分配

| 服务器 | 角色 | 说明 |
|--------|------|------|
| **B2ats v2（AMD + Linux）** | **主服务机** | 运行全部 AI_CBC 服务 |
| B2pts v2（Arm + Linux） | 预留/备份机 | 暂不装机，后续可做异地备份或测试 |
| B2ats v2（AMD + Windows） | 开发/办公机 | 不跑生产服务 |
| B2pts v2（Arm + Windows） | 开发/办公机 | 不跑生产服务 |

**关键决策：** 先只使用一台 Linux/x86 机器，其他三台闲置。这是为了把复杂度降到最低，等跑稳后再考虑扩展。

## 4. 部署架构

### 4.1 服务栈

Azure B2ats v2 的标准规格为 **2 vCPU / 1 GiB RAM**，因此默认采用裁剪版服务栈，只保留用户直接访问所需的核心路径：

```
Internet
   |
   v
[Nginx :80/:443]
   |
   +---> [FastAPI API :8000]
               |
               +---> [MongoDB :27017]
               +---> [Redis :6379]
```

 Celery worker/beat、Prometheus、Grafana 在 1 GiB 内存下无法稳定运行，先不部署。后台 HB 分析任务需要时可在本地手动运行，或后续升级到 4GB+ 机器后再恢复。

### 4.2 资源分配参考（默认 1 GiB 场景）

参考 [`2026-06-19-azure-b2ats-selfhosting-design.md`](2026-06-19-azure-b2ats-selfhosting-design.md) 的裁剪方案：

| 服务 | 内存限制 | CPU 限制 | 说明 |
|------|----------|----------|------|
| `aicbc-api` | 384 MB | 0.8 | `API_WORKERS=1`，关闭调试 |
| `mongo` | 256 MB | 0.5 | WiredTiger 缓存限制 128 MB |
| `redis` | 64 MB | 0.2 | `maxmemory 64mb` + `allkeys-lru` |
| `nginx` | 32 MB | 0.2 | 反向代理 + HTTPS |

**合计内存上限约 736 MB**，剩余约 264 MB 给操作系统、Docker daemon 和 swap。

若后续升级到 2 GiB 或更高内存，可再恢复完整栈，分配如下：

| 服务 | 内存限制 | CPU 限制 | 说明 |
|------|----------|----------|------|
| `aicbc-api` | 512 MB | 0.5 | `API_WORKERS=1` 或 `2` |
| `worker` | 512 MB | 0.5 | 仅跑 HB 分析时才忙 |
| `beat` | 128 MB | 0.1 | 定时任务调度 |
| `mongo` | 512 MB | 0.5 | WiredTiger 缓存限制 256 MB |
| `redis` | 128 MB | 0.1 | `maxmemory 128mb` |
| `nginx` | 64 MB | 0.1 | 反向代理 + HTTPS |
| `prometheus` | 256 MB | 0.1 | 指标采集 |
| `grafana` | 128 MB | 0.1 | 监控面板 |

> 注：实际分配需根据 VM 真实内存调整。若只有 1 GiB，请回到裁剪版方案。

## 5. 操作系统与基础软件

### 5.1 操作系统

- **Ubuntu 24.04 LTS Server**（无桌面版，更省资源）
- 原因：与项目 Docker 部署文档一致；社区资料最多；新手遇到问题最容易搜索到答案。

### 5.2 必装软件

| 软件 | 用途 |
|------|------|
| `openssh-server` | 远程 SSH 管理 |
| `docker.io` 或 `docker-ce` | 容器运行 |
| `docker-compose-plugin` | 编排多个容器 |
| `git` | 拉取代码 |
| `certbot` | 申请 Let's Encrypt 证书 |
| `ufw` | 简单防火墙 |

## 6. 网络与安全

### 6.1 Azure NSG（网络安全组）

只开放三个端口：

| 端口 | 协议 | 来源 | 用途 |
|------|------|------|------|
| 22 | TCP | 你的本地 IP | SSH 管理 |
| 80 | TCP | 0.0.0.0/0 | HTTP → HTTPS 重定向 + Certbot 验证 |
| 443 | TCP | 0.0.0.0/0 | HTTPS 正式访问 |

**禁止开放：** 27017、6379、8000、9090、3000。这些服务只在 Docker 内部网络通信。

### 6.2 服务器防火墙（UFW）

```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 6.3 SSH 安全

- 使用 SSH 密钥登录，禁用密码登录。
- 可选：修改默认 22 端口（对新手不建议，容易把自己锁外面）。

### 6.4 应用层安全

- 后端必须启用 `API_KEY` / JWT 认证（参考 [`2026-06-19-frontend-auth-jwt.md`](../../plans/2026-06-19-frontend-auth-jwt.md)）。
- 成本熔断（Cost Fuse）必须配置，防止公网暴露后被恶意刷 LLM 费用。
- `SECRET_KEY` 生产环境必须 ≥ 32 位随机字符串。

## 7. 域名与 HTTPS

1. **域名解析：** 把二级域名 A 记录指向 B2ats v2 Linux 的公网 IP。
2. **证书申请：** 使用 Certbot standalone 或 webroot 模式申请证书。
3. **Nginx 配置：** 基于项目现有 `docker/nginx.azure-b2ats.conf`，修改 `ssl_certificate` 和 `ssl_certificate_key` 为 Certbot 生成的路径。
4. **自动续期：** Certbot 默认会安装 systemd timer 自动续期。

最终访问地址：

- 前端/API：`https://你的二级域名`
- 后台任务（需要时手动启动）：通过 SSH 在容器内运行
- 监控栈：默认不部署；需要时可通过 SSH 隧道本地访问，或升级内存后通过 Nginx 子路径代理

## 8. 数据持久化与备份

### 8.1 本地持久化

使用 Docker named volume 或 bind mount：

- `mongo_data`：MongoDB 数据文件
- `redis_data`：Redis 持久化数据
- `./ssl`：Let's Encrypt 证书
- `./backups`：临时备份文件

### 8.2 MongoDB 备份策略

满足“至少一个演示案例长期保留”的需求：

- **每周全量备份：** 通过 cron 每周运行一次 `mongodump`。
- **保留策略：** 本地保留最近 4 份周备份。
- **可选：** 手动把备份文件下载到本地电脑或上传到 Azure Blob Storage。

备份脚本示例：

```bash
#!/bin/bash
BACKUP_DIR="/opt/aicbc/backups"
DATE=$(date +%Y%m%d_%H%M%S)
docker exec aicbc-mongo mongodump --out /backup/${DATE}
tar czf ${BACKUP_DIR}/mongo_${DATE}.tar.gz -C ${BACKUP_DIR} ${DATE}
rm -rf ${BACKUP_DIR}/${DATE}
# 保留最近 4 份
ls -t ${BACKUP_DIR}/mongo_*.tar.gz | tail -n +5 | xargs -r rm
```

### 8.3 恢复流程

```bash
# 解压备份
tar xzf /opt/aicbc/backups/mongo_YYYYMMDD_HHMMSS.tar.gz -C /tmp/restore
# 恢复到 MongoDB
docker exec -i aicbc-mongo mongorestore --drop /tmp/restore/YYYYMMDD_HHMMSS
```

## 9. 环境变量配置

复制 `.env.example` 为 `.env`，至少修改以下项：

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥（可选） |
| `MONGODB_URL` | `mongodb://mongo:27017/aicbc`（Docker 内部） |
| `REDIS_URL` | `redis://redis:6379/0`（Docker 内部） |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `SECRET_KEY` | 生产环境 ≥32 位随机字符串 |
| `API_KEY` | 服务账号 API Key |
| `FRONTEND_RESEARCHER_PASSWORD_HASH` | 前端研究员登录密码哈希 |
| `FRONTEND_ADMIN_PASSWORD_HASH` | 前端管理员登录密码哈希 |

## 10. 部署步骤（实施计划输入）

1. 在 Azure 门户创建 B2ats v2 Linux VM，选择 Ubuntu 24.04 LTS。
2. 配置 NSG：只开放 22、80、443。
3. SSH 登录 VM，更新系统并安装 Docker、Docker Compose、Git、Certbot、UFW。
4. 配置 2GB swap（即使内存 1GB 也强烈建议开，避免 OOM）。
5. 配置 UFW 防火墙。
6. 克隆 AI_CBC 代码到 `/opt/aicbc`。
7. 复制 `.env.example` 为 `.env` 并填入所有机密。
8. 配置域名 A 记录指向 VM 公网 IP。
9. 申请 Let's Encrypt 证书。
10. 使用项目现成的 `docker-compose.azure-b2ats.yml` 启动服务：`docker compose -f docker-compose.azure-b2ats.yml up -d`。
11. 配置 MongoDB 备份 cron 任务。
12. 验证 HTTPS、登录、创建研究、生成画像等。

## 11. 运维日常操作

| 操作 | 命令 |
|------|------|
| 启动服务 | `docker compose -f docker-compose.azure-b2ats.yml up -d` |
| 停止服务 | `docker compose -f docker-compose.azure-b2ats.yml down` |
| 查看日志 | `docker compose -f docker-compose.azure-b2ats.yml logs -f api` |
| 重启单个服务 | `docker compose -f docker-compose.azure-b2ats.yml restart api` |
| 更新代码 | `git pull && docker compose -f docker-compose.azure-b2ats.yml up -d --pull always` |
| 手动备份 | `sudo /opt/aicbc/scripts/backup-mongodb.sh` |
| 查看资源占用 | `docker stats` |
| 查看实时日志 | `docker compose -f docker-compose.azure-b2ats.yml logs -f --tail 100` |
| 运行一次性后台任务 | 参考完整 `docker-compose.yml` 临时启动 worker 容器 |

## 12. 已知限制与风险

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| 单点故障 | 整机故障则服务全停 | 每周备份 MongoDB；关键配置和 `.env` 本地另存 |
| 内存不足 | B2ats v2 标准规格为 1 GiB | 默认使用 `docker-compose.azure-b2ats.yml` 裁剪版；升级内存后再恢复完整栈 |
| Arm 兼容风险 | B2pts v2 为 Arm，pymc 可能异常 | 主服务不用 Arm 机器 |
| Windows 维护成本 | WSL2 + Docker 对新手不友好 | 生产服务不放在 Windows 上 |
| 公网安全风险 | 暴露后可能被扫描、刷 API | 只开 22/80/443；启用后端认证和成本熔断 |
| 证书续期失败 | Certbot 续期异常会导致 HTTPS 中断 | 每月手动检查一次 `certbot renew --dry-run` |

## 13. 后续升级路径

| 阶段 | 触发条件 | 动作 |
|------|----------|------|
| 当前 | 开发/演示 | 单台 B2ats v2 Linux 跑主服务 |
| 升级 1 | 内存不够或需要监控 | 升到 B2s（4GB）或恢复完整监控栈 |
| 升级 2 | 需要后台任务常驻 | 恢复 worker/beat，或单独一台机器跑 Celery |
| 升级 3 | 正式生产环境 | 应用与数据库分离，考虑 K8s overlay |

## 14. 决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 主力服务器 | B2ats v2 Linux（AMD/x86） | 兼容性最好，文档最匹配 |
| 编排方式 | Docker Compose | 与项目现有方案一致，新手友好 |
| 数据库/缓存 | 自托管 MongoDB + Redis | 零额外费用，与 .env.example 一致 |
| HTTPS | Let's Encrypt + Certbot | 免费、自动续期 |
| 其他三台机器 | 暂不使用 | 降低初始复杂度，先跑通一台 |
| 备份 | 本地每周备份 + 手动异地保存 | 满足“至少一个案例长期保留” |

## 15. 相关文档

- [`../../CLAUDE.md`](../../CLAUDE.md) — 项目全局规范
- [`../../docker/CLAUDE.md`](../../docker/CLAUDE.md) — 容器构建规范
- [`../../src/CLAUDE.md`](../../src/CLAUDE.md) — 后端开发与配置
- [`../../k8s/CLAUDE.md`](../../k8s/CLAUDE.md) — Kubernetes 部署说明（后续升级参考）
- [`../../docker-compose.yml`](../../docker-compose.yml) — 完整版 Compose 参考
- [`../../.env.example`](../../.env.example) — 环境变量模板
- [`2026-06-19-azure-b2ats-selfhosting-design.md`](2026-06-19-azure-b2ats-selfhosting-design.md) — 1GB 内存裁剪版部署设计
- [`../../plans/2026-06-19-frontend-auth-jwt.md`](../../plans/2026-06-19-frontend-auth-jwt.md) — 前端 JWT 认证设计
