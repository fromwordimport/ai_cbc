# AI_CBC Azure B2ats v2 首次部署手册

> **前提**：已拥有 Azure 订阅和 12 个月免费额度

## 0. 部署架构（双机）

AI_CBC 在 Azure B2ats v2 场景下使用 **一主一从** 两台 VM：

| VM | 建议名称 | 角色 | 运行的服务 |
|----|----------|------|------------|
| **主 VM** | `aicbc-b2ats-vm` | 对外提供 API、持久化数据、反向代理 | API (uvicorn)、MongoDB、Redis、nginx |
| **Worker VM** | `aicbc-b2ats-worker-vm` | 后台异步执行分析任务 | Celery analysis worker |

- 主 VM 暴露 **80/443** 供外部访问 API，暴露 **27017/6379** 供 Worker VM 内网连接。
- Worker VM 不直接对外暴露服务，通过主 VM 的 Redis 与 MongoDB 跨机通信。
- GitHub Actions `cd-azure-b2ats.yml` 会分别 SSH 到两台 VM 进行部署。

> 如果你只想做单机验证，可只创建主 VM，使用 `docker-compose.azure-b2ats.yml`，跳过 Worker VM 相关步骤。

## 1. 创建 Azure VM（主 VM）

1. 登录 Azure Portal： https://portal.azure.com
2. 搜索 "Virtual machines" → 点击 **Create** → **Azure virtual machine**
3. 选择 Resource group（如 `aicbc-rg`）
4. 虚拟机名称：`aicbc-b2ats-vm`
5. 区域：选择离你最近的区域（如 East Asia）
6. 镜像：**Ubuntu Server 22.04 LTS**
7. 大小：**Standard_B2ats_v2**（2 vCPU，1 GiB RAM）
8. 身份验证：选择 **SSH public key**，生成或上传公钥
9. 入站端口：勾选 **HTTP (80)**、**HTTPS (443)**、**SSH (22)**
10. 磁盘：Standard SSD，64 GB
11. 点击 **Review + create**，然后 **Create**

### 1.1 创建 Worker VM（可选但推荐）

Worker VM 专门运行 Celery analysis worker，不直接对外提供服务。

1. 重复上面的创建流程，虚拟机名称建议为：`aicbc-b2ats-worker-vm`
2. 大小：可复用 **Standard_B2ats_v2**，也可选择其他支持 Docker 的规格
3. 镜像：建议与主 VM 架构保持一致；当前 CD 同时构建 `linux/amd64` 与 `linux/arm64` 镜像，因此 x64 或 ARM64 均可
4. 入站端口：仅保留 **SSH (22)**，无需暴露 80/443
5. 磁盘：Standard SSD，64 GB

Worker VM 后续通过主 VM 的内网 IP 连接 MongoDB（27017）与 Redis（6379），因此两台 VM 需要位于同一 VNet / 子网，或在网络安全组中放行对应端口。

## 2. 配置网络安全组

创建 VM 后，进入 **主 VM** → **Networking** → **Network settings** → **Inbound port rules**，确保：

| 端口 | 操作 | 优先级 | 来源 | 用途 |
|------|------|--------|------|------|
| 22 | Allow | 1000 | 你的本地 IP | SSH |
| 80 | Allow | 1010 | Any | HTTP → HTTPS 重定向 |
| 443 | Allow | 1020 | Any | HTTPS |
| 27017 | Allow | 1030 | Worker VM 内网 IP / 子网 | Worker 连接 MongoDB |
| 6379 | Allow | 1040 | Worker VM 内网 IP / 子网 | Worker 连接 Redis |

禁用其他所有入站规则。

> Worker VM 的安全组只需开放 **SSH (22)**。

## 3. 初始化主 VM

SSH 登录到主 VM：

```bash
ssh azureuser@<主VM_PUBLIC_IP>
```

执行初始化脚本：

```bash
git clone https://github.com/fromwordimport/aicbc.git /opt/aicbc
cd /opt/aicbc
bash scripts/setup-azure-vm.sh
```

**注意**：脚本执行后会提示重新登录以应用 docker 用户组。退出并重新 SSH 登录。

### 3.1 初始化 Worker VM

SSH 登录到 Worker VM：

```bash
ssh azureuser@<WorkerVM_PUBLIC_IP>
```

同样执行：

```bash
git clone https://github.com/fromwordimport/aicbc.git /opt/aicbc
cd /opt/aicbc
bash scripts/setup-azure-vm.sh
```

退出并重新 SSH 登录，使 docker 用户组生效。

## 4. 配置环境变量

### 4.1 主 VM

```bash
cd /opt/aicbc
cp .env.azure-b2ats.example .env
nano .env
```

至少填写：

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `SECRET_KEY`
- `API_KEY`（服务账号调用 API 用，需与 GitHub Actions `secrets.API_KEY` 一致）
- `AZURE_STORAGE_CONNECTION_STRING`（可选，用于备份）

### 4.2 Worker VM

同样复制 `.env.azure-b2ats.example` 为 `.env`，但数据库连接需指向主 VM：

```bash
MONGODB_URL=mongodb://<主VM内网IP>:27017/aicbc
REDIS_URL=redis://<主VM内网IP>:6379/0
```

Worker VM 不需要暴露 `API_HOST`，`API_PORT` 保持默认即可。

## 5. 配置 HTTPS 证书

### 5.1 使用 Let's Encrypt + Certbot（推荐，需域名）

1. 将你的域名 A 记录指向 **主 VM** 公网 IP
2. 在 VM 上安装 Certbot：

```bash
sudo apt-get install -y certbot
```

3. 获取证书：

```bash
sudo certbot certonly --standalone -d your-domain.com --agree-tos -m your-email@example.com
```

4. 将证书链接到项目目录：

```bash
sudo ln -s /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/aicbc/ssl/cert.pem
sudo ln -s /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/aicbc/ssl/key.pem
```

5. 设置自动续期：

```bash
echo "0 3 * * * root certbot renew --quiet && docker compose -f /opt/aicbc/docker-compose.azure-b2ats.yml restart nginx" | sudo tee /etc/cron.d/aicbc-certbot
```

### 5.2 无域名临时方案

如果没有域名，可以生成自签名证书（仅在 **主 VM** 使用）：

```bash
cd /opt/aicbc/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=<主VM_PUBLIC_IP>"
```

浏览器会提示证书不可信，仅用于测试。

## 6. 启动服务

### 6.1 主 VM

```bash
cd /opt/aicbc
docker compose -f docker-compose.azure-b2ats.yml up -d
```

检查状态：

```bash
docker compose -f docker-compose.azure-b2ats.yml ps
curl -sf http://localhost:8000/health || echo "API not healthy"
```

### 6.2 Worker VM

```bash
cd /opt/aicbc
export AZURE_MAIN_VM_IP=<主VM内网IP>
docker compose -f docker-compose.azure-worker.yml up -d
```

检查 worker 是否连接上主 VM：

```bash
docker logs -f aicbc-worker
```

应能看到 `Connected to redis://<主VM内网IP>:6379/0` 以及 `ready` 日志。

## 7. 后续操作

1. 在 GitHub 配置部署所需的 Secret：
   - `AZURE_VM_IP`：主 VM 公网 IP
   - `AZURE_VM_USER`：主 VM SSH 用户名
   - `AZURE_VM_SSH_KEY`：主 VM SSH 私钥
   - `AZURE_WORKER_VM_IP`：Worker VM 公网 IP
   - `AZURE_WORKER_VM_USER`：Worker VM SSH 用户名
   - `AZURE_WORKER_VM_SSH_KEY`：Worker VM SSH 私钥
2. 如需从 GitHub Actions 直接调用 API（如 `feature-switch.yml`、`data-pipeline.yml`），还需在对应 environment 配置 `STAGING_API_HOST` / `PROD_API_HOST` 与 `API_KEY`。
3. 后续 `master` 分支更新会自动触发 `.github/workflows/cd-azure-b2ats.yml` 部署到这两台 VM。

## 8. 配置自动备份

### 8.1 安装 Azure CLI

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### 8.2 测试备份脚本

```bash
cd /opt/aicbc
source .env
bash scripts/backup-mongodb-to-azure.sh
```

### 8.3 配置每日定时备份

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/aicbc && source .env && bash scripts/backup-mongodb-to-azure.sh >> /opt/aicbc/logs/backup.log 2>&1") | crontab -
```

## 9. 配置 GitHub Actions 自动部署

1. 在 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions** 中添加：
   - `AZURE_VM_IP`：主 VM 公网 IP
   - `AZURE_VM_USER`：主 VM SSH 用户名（如 `azureuser`）
   - `AZURE_VM_SSH_KEY`：主 VM SSH 私钥（与 VM 公钥配对）
   - `AZURE_WORKER_VM_IP`：Worker VM 公网 IP
   - `AZURE_WORKER_VM_USER`：Worker VM SSH 用户名
   - `AZURE_WORKER_VM_SSH_KEY`：Worker VM SSH 私钥

2. 在 GitHub 中创建 `azure-b2ats` environment（可选，用于审批保护）

3. 推送代码到 master，触发 `.github/workflows/cd-azure-b2ats.yml` 同时部署主 VM 与 Worker VM

## 10. 验证部署

从本地访问主 VM：

```bash
curl https://your-domain.com/health
```

或：

```bash
curl -k https://<主VM_PUBLIC_IP>/health
```

Worker VM 验证：

```bash
docker logs -f aicbc-worker
```

## 11. 常见问题

### OOM Killed

检查内存使用：

```bash
docker stats --no-stream
free -h
```

确认 swap 已启用：

```bash
swapon --show
```

### 容器无法启动

查看日志：

```bash
docker compose -f docker-compose.azure-b2ats.yml logs -f api
```

### 备份上传失败

检查 Azure CLI 是否登录：

```bash
az storage container list --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```
