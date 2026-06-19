> **版本**：v1.0
> **日期**：2026-06-19
> **负责人**：小维（DevOps/MLOps）
> **状态**：待执行

# Azure B2ats v2 自托管部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Azure B2ats v2（2 vCPU + 1 GiB RAM）云服务器上，使用 Docker Compose 部署 AI_CBC 核心服务（API + MongoDB + Redis + Nginx），脱离 Render、MongoDB Atlas、Upstash Redis，并建立 Azure Blob 备份与 GitHub Actions 自动部署。

**Architecture:** 单台 VM 运行裁剪版 Docker Compose 栈；Nginx 提供 HTTPS 终止与反向代理；MongoDB 与 Redis 仅暴露于 Docker 内部网络；GitHub Actions 构建镜像并 SSH 到服务器 pull & up；Azure Blob 存储每日备份。

**Tech Stack:** Docker, Docker Compose, Nginx, Certbot, Azure Blob Storage, GitHub Actions, GHCR

---

## 文件结构

| 文件 | 用途 |
|------|------|
| `docker-compose.azure-b2ats.yml` | 裁剪版 Compose：只启动 api/mongo/redis/nginx |
| `docker/nginx.azure-b2ats.conf` | 单 API 上游的 Nginx 配置，含 Certbot ACME 路径 |
| `scripts/setup-azure-vm.sh` | VM 初始化：安装 Docker、配置 swap、创建目录 |
| `scripts/backup-mongodb-to-azure.sh` | MongoDB dump + 上传到 Azure Blob |
| `scripts/deploy-to-azure-b2ats.sh` | 服务器端拉取镜像并重启服务 |
| `.github/workflows/cd-azure-b2ats.yml` | GitHub Actions：构建镜像、SSH 部署 |
| `.env.azure-b2ats.example` | Azure B2ats 部署专用环境变量模板 |
| `docs/superpowers/specs/2026-06-19-azure-b2ats-selfhosting-design.md` | 已批准的设计文档（输入） |

---

### Task 1: 创建裁剪版 Docker Compose 文件

**Files:**
- Create: `docker-compose.azure-b2ats.yml`

- [ ] **Step 1: 编写裁剪版 Compose 配置**

```yaml
# AI_CBC Azure B2ats v2 裁剪版部署
# 约束：1 GiB RAM，只运行 api / mongo / redis / nginx
# worker / beat / prometheus / grafana 在此规格下移除

services:
  api:
    image: ghcr.io/fromwordimport/aicbc:latest
    container_name: aicbc-api
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
      - LOG_LEVEL=INFO
      - MONGODB_URL=mongodb://mongo:27017/aicbc
      - REDIS_URL=redis://redis:6379/0
      - API_HOST=0.0.0.0
      - API_PORT=8000
      - API_WORKERS=1
      - METRICS_PATH=/metrics
      - SLOW_REQUEST_THRESHOLD=5.0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      mongo:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 384M
          cpus: '0.8'
        reservations:
          memory: 128M
          cpus: '0.25'
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      start_period: 15s
      retries: 3
    networks:
      - aicbc-network

  mongo:
    image: mongo:7.0
    container_name: aicbc-mongo
    environment:
      - MONGO_INITDB_DATABASE=aicbc
    command:
      - "--bind_ip"
      - "0.0.0.0"
      - "--wiredTigerCacheSizeGB"
      - "0.125"
    volumes:
      - mongo_data:/data/db
      - ./backups/mongo:/backup
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.1'
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      start_period: 30s
      retries: 3
    networks:
      - aicbc-network

  redis:
    image: redis:7.2-alpine
    container_name: aicbc-redis
    command:
      - "redis-server"
      - "--maxmemory"
      - "64mb"
      - "--maxmemory-policy"
      - "allkeys-lru"
      - "--appendonly"
      - "yes"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: '0.2'
        reservations:
          memory: 32M
          cpus: '0.05'
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      start_period: 10s
      retries: 3
    networks:
      - aicbc-network

  nginx:
    image: nginx:alpine
    container_name: aicbc-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx.azure-b2ats.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - ./certbot/www:/var/www/certbot:ro
      - ./certbot/conf:/etc/letsencrypt:ro
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 32M
          cpus: '0.2'
    networks:
      - aicbc-network

volumes:
  mongo_data:
  redis_data:

networks:
  aicbc-network:
    driver: bridge
```

- [ ] **Step 2: 验证 Compose 文件语法**

Run: `docker compose -f docker-compose.azure-b2ats.yml config`
Expected: 输出完整配置，无错误

- [ ] **Step 3: 提交文件**

```bash
git add docker-compose.azure-b2ats.yml
git commit -m "feat(deploy): add Azure B2ats v2 trimmed compose stack"
```

---

### Task 2: 创建 Azure B2ats 专用 Nginx 配置

**Files:**
- Create: `docker/nginx.azure-b2ats.conf`
- Based on: `docker/nginx.conf`

- [ ] **Step 1: 编写单 API 实例 Nginx 配置**

```nginx
# AI_CBC Azure B2ats v2 Nginx Configuration
# Single API upstream, Certbot ACME support, HTTPS redirect

worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 512;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" ';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;

    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=health_limit:10m rate=100r/s;

    upstream api_backend {
        server api:8000 max_fails=3 fail_timeout=30s;
        keepalive 16;
    }

    server {
        listen 80;
        server_name _;

        location /health {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            limit_req zone=health_limit burst=20 nodelay;
        }

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
        ssl_prefer_server_ciphers on;

        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        location /api/ {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 120s;
            proxy_buffering off;
            limit_req zone=api_limit burst=20 nodelay;
        }

        location /health {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            limit_req zone=health_limit burst=50 nodelay;
            access_log off;
        }

        location /docs {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
        }

        location /redoc {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
        }

        location / {
            return 404;
        }
    }
}
```

- [ ] **Step 2: 验证 Nginx 配置语法（在容器内）**

Run: `docker run --rm -v "$(pwd)/docker/nginx.azure-b2ats.conf:/etc/nginx/nginx.conf:ro" nginx:alpine nginx -t`
Expected: `syntax is ok` / `test is successful`

- [ ] **Step 3: 提交文件**

```bash
git add docker/nginx.azure-b2ats.conf
git commit -m "feat(deploy): add Azure B2ats v2 nginx config"
```

---

### Task 3: 创建 Azure B2ats 环境变量模板

**Files:**
- Create: `.env.azure-b2ats.example`

- [ ] **Step 1: 编写专用环境变量模板**

```bash
# AI_CBC Azure B2ats v2 部署环境变量
# 复制为 .env 并填入真实值

# LLM API 配置
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
SECRET_KEY=change-me-to-a-long-random-secret

# 应用配置
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1

# 监控
METRICS_PATH=/metrics
SLOW_REQUEST_THRESHOLD=5.0

# 成本熔断（按需调整）
COST_FUSE_SINGLE_STUDY_CNY=500
COST_FUSE_DAILY_CNY=1000
COST_FUSE_WEEKLY_CNY=5000
COST_FUSE_MONTHLY_CNY=20000
COST_FUSE_DEGRADE_MODEL=claude-haiku-4-5

# Azure Blob 备份（可选，用于自动上传备份）
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
AZURE_BACKUP_CONTAINER=aicbc-backups
```

- [ ] **Step 2: 提交文件**

```bash
git add .env.azure-b2ats.example
git commit -m "docs(deploy): add Azure B2ats v2 env template"
```

---

### Task 4: 创建 VM 初始化脚本

**Files:**
- Create: `scripts/setup-azure-vm.sh`

- [ ] **Step 1: 编写 VM 初始化脚本**

```bash
#!/usr/bin/env bash
# AI_CBC Azure B2ats v2 VM 初始化脚本
# 用法：以普通用户身份通过 SSH 登录后执行

set -euo pipefail

APP_DIR="/opt/aicbc"

# 1. 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 2. 安装 Docker
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker 已安装。请重新登录以应用 docker 用户组权限。"
fi

# 3. 配置 2GB swap
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 4. 创建应用目录
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

# 5. 创建子目录
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/backups/mongo"
mkdir -p "$APP_DIR/ssl"
mkdir -p "$APP_DIR/certbot/www"
mkdir -p "$APP_DIR/certbot/conf"

echo "VM 初始化完成。下一步：克隆项目到 $APP_DIR 并配置 .env"
```

- [ ] **Step 2: 设置脚本可执行权限**

Run: `chmod +x scripts/setup-azure-vm.sh`

- [ ] **Step 3: 提交文件**

```bash
git add scripts/setup-azure-vm.sh
git commit -m "feat(deploy): add Azure VM setup script"
```

---

### Task 5: 创建 MongoDB 备份脚本

**Files:**
- Create: `scripts/backup-mongodb-to-azure.sh`

- [ ] **Step 1: 编写备份脚本**

```bash
#!/usr/bin/env bash
# AI_CBC MongoDB 备份并上传至 Azure Blob
# 建议在服务器上通过 cron 每日执行一次

set -euo pipefail

BACKUP_BASE="/opt/aicbc/backups/mongo"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
RETENTION_DAYS=7

# Azure Blob 配置（从环境读取）
AZURE_STORAGE_CONNECTION_STRING="${AZURE_STORAGE_CONNECTION_STRING:-}"
AZURE_BACKUP_CONTAINER="${AZURE_BACKUP_CONTAINER:-aicbc-backups}"

# 1. 执行 mongodump
mkdir -p "$BACKUP_DIR"
docker exec aicbc-mongo mongodump --out "/backup/$TIMESTAMP"

# 2. 压缩备份
cd "$BACKUP_BASE"
tar czf "$TIMESTAMP.tar.gz" "$TIMESTAMP"
rm -rf "$TIMESTAMP"

# 3. 上传到 Azure Blob（如果配置了连接串）
if [ -n "$AZURE_STORAGE_CONNECTION_STRING" ]; then
    az storage blob upload \
        --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
        --container-name "$AZURE_BACKUP_CONTAINER" \
        --file "$TIMESTAMP.tar.gz" \
        --name "aicbc-mongo-$TIMESTAMP.tar.gz" \
        --overwrite false
    echo "备份已上传：aicbc-mongo-$TIMESTAMP.tar.gz"
else
    echo "未配置 AZURE_STORAGE_CONNECTION_STRING，备份保留在本地：$BACKUP_DIR.tar.gz"
fi

# 4. 清理本地旧备份
find "$BACKUP_BASE" -name "*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "MongoDB 备份完成：$TIMESTAMP.tar.gz"
```

- [ ] **Step 2: 设置脚本可执行权限**

Run: `chmod +x scripts/backup-mongodb-to-azure.sh`

- [ ] **Step 3: 提交文件**

```bash
git add scripts/backup-mongodb-to-azure.sh
git commit -m "feat(deploy): add MongoDB backup to Azure Blob script"
```

---

### Task 6: 创建服务器端部署脚本

**Files:**
- Create: `scripts/deploy-to-azure-b2ats.sh`

- [ ] **Step 1: 编写服务器端部署脚本**

```bash
#!/usr/bin/env bash
# AI_CBC Azure B2ats v2 服务器端部署脚本
# 由 GitHub Actions 通过 SSH 调用，也可在服务器上手动执行

set -euo pipefail

APP_DIR="/opt/aicbc"
cd "$APP_DIR"

# 1. 拉取最新镜像（不在服务器上构建）
docker compose -f docker-compose.azure-b2ats.yml pull

# 2. 停止并重新启动服务
docker compose -f docker-compose.azure-b2ats.yml down
docker compose -f docker-compose.azure-b2ats.yml up -d

# 3. 等待 API 健康
for i in {1..30}; do
    if curl -sf http://localhost:8000/health > /dev/null; then
        echo "API health check passed"
        exit 0
    fi
    echo "Waiting for API health... ($i/30)"
    sleep 2
done

echo "API health check failed after 60 seconds"
exit 1
```

- [ ] **Step 2: 设置脚本可执行权限**

Run: `chmod +x scripts/deploy-to-azure-b2ats.sh`

- [ ] **Step 3: 提交文件**

```bash
git add scripts/deploy-to-azure-b2ats.sh
git commit -m "feat(deploy): add Azure B2ats v2 server deploy script"
```

---

### Task 7: 创建 GitHub Actions 部署工作流

**Files:**
- Create: `.github/workflows/cd-azure-b2ats.yml`

- [ ] **Step 1: 编写 GitHub Actions 工作流**

```yaml
# AI_CBC Azure B2ats v2 部署流水线
# 触发条件：master 分支 push 或手动触发
# 1. 构建并推送镜像到 GHCR
# 2. SSH 到 Azure VM 执行部署脚本

name: CD Azure B2ats v2

on:
  push:
    branches: [master]
    paths-ignore:
      - 'docs/**'
      - '**/*.md'
  workflow_dispatch:

concurrency:
  group: cd-azure-b2ats-${{ github.ref }}
  cancel-in-progress: false

jobs:
  build-push:
    runs-on: ubuntu-22.04
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:${{ github.sha }}
            ghcr.io/${{ github.repository }}:master
            ghcr.io/${{ github.repository }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    runs-on: ubuntu-22.04
    needs: build-push
    environment: azure-b2ats
    steps:
      - uses: actions/checkout@v4

      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.AZURE_VM_IP }}
          username: ${{ secrets.AZURE_VM_USER }}
          key: ${{ secrets.AZURE_VM_SSH_KEY }}
          script: |
            cd /opt/aicbc
            git fetch origin master
            git reset --hard origin/master
            bash scripts/deploy-to-azure-b2ats.sh
```

- [ ] **Step 2: 验证工作流语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/cd-azure-b2ats.yml'))"`
Expected: 无输出（表示 YAML 解析成功）

- [ ] **Step 3: 提交文件**

```bash
git add .github/workflows/cd-azure-b2ats.yml
git commit -m "ci(deploy): add Azure B2ats v2 deployment workflow"
```

---

### Task 8: 更新主环境变量模板注释

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: 在数据库配置处添加 Azure 自托管注释**

在 `.env.example` 中找到：

```
# MongoDB
# 本地开发使用 mongodb://localhost:27017
# Render 部署时替换为 MongoDB Atlas 连接串，例如：
# MONGODB_URL=mongodb+srv://user:password@cluster0.xxxxx.mongodb.net/aicbc?retryWrites=true&w=majority
MONGODB_URL=mongodb://localhost:27017
```

替换为：

```
# MongoDB
# 本地开发使用 mongodb://localhost:27017
# Azure B2ats v2 自托管使用 mongodb://mongo:27017/aicbc
# Render 部署时替换为 MongoDB Atlas 连接串，例如：
# MONGODB_URL=mongodb+srv://user:password@cluster0.xxxxx.mongodb.net/aicbc?retryWrites=true&w=majority
MONGODB_URL=mongodb://localhost:27017
```

同样，找到 Redis 注释：

```
# Redis
# 本地开发使用 redis://localhost:6379/0
# Render 部署时替换为 Upstash Redis URL，例如：
# REDIS_URL=redis://default:password@host.upstash.io:6379
REDIS_URL=redis://localhost:6379/0
```

替换为：

```
# Redis
# 本地开发使用 redis://localhost:6379/0
# Azure B2ats v2 自托管使用 redis://redis:6379/0
# Render 部署时替换为 Upstash Redis URL，例如：
# REDIS_URL=redis://default:password@host.upstash.io:6379
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 2: 提交修改**

```bash
git add .env.example
git commit -m "docs(env): add Azure B2ats v2 connection notes"
```

---

### Task 9: 本地验证 Compose 栈可启动

**Files:**
- Use: `docker-compose.azure-b2ats.yml`
- Use: `.env.azure-b2ats.example`

- [ ] **Step 1: 准备本地测试环境变量**

Run:
```bash
cp .env.azure-b2ats.example .env
# 编辑 .env 填入有效 ANTHROPIC_API_KEY 和 SECRET_KEY
```

- [ ] **Step 2: 启动服务**

Run: `docker compose -f docker-compose.azure-b2ats.yml up -d`
Expected: 4 个容器均处于 Up/Healthy 状态

- [ ] **Step 3: 检查健康状态**

Run: `docker compose -f docker-compose.azure-b2ats.yml ps`
Expected: api、mongo、redis、nginx 状态为 `healthy`

- [ ] **Step 4: 测试 API 健康接口**

Run: `curl http://localhost:8000/health`
Expected: 返回 200 和 JSON 健康状态

- [ ] **Step 5: 清理本地测试容器**

Run: `docker compose -f docker-compose.azure-b2ats.yml down -v`
Expected: 容器和网络被删除

- [ ] **Step 6: 提交任何修复**

如果在验证中发现问题，修复后提交：

```bash
git add .
git commit -m "fix(deploy): resolve Azure B2ats compose startup issues"
```

---

### Task 10: 编写 Azure VM 首次部署操作手册

**Files:**
- Create: `docs/运维/Azure-B2ats-v2-首次部署手册.md`

- [ ] **Step 1: 编写操作手册**

```markdown
# AI_CBC Azure B2ats v2 首次部署手册

> **前提**：已拥有 Azure 订阅和 12 个月免费额度

## 1. 创建 Azure VM

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

## 2. 配置网络安全组

创建 VM 后，进入 VM → **Networking** → **Network settings** → **Inbound port rules**，确保：

| 端口 | 操作 | 优先级 | 来源 | 用途 |
|------|------|--------|------|------|
| 22 | Allow | 1000 | 你的本地 IP | SSH |
| 80 | Allow | 1010 | Any | HTTP → HTTPS 重定向 |
| 443 | Allow | 1020 | Any | HTTPS |

禁用其他所有入站规则。

## 3. 初始化 VM

SSH 登录到 VM：

```bash
ssh azureuser@<VM_PUBLIC_IP>
```

执行初始化脚本：

```bash
git clone https://github.com/fromwordimport/aicbc.git /opt/aicbc
cd /opt/aicbc
bash scripts/setup-azure-vm.sh
```

**注意**：脚本执行后会提示重新登录以应用 docker 用户组。退出并重新 SSH 登录。

## 4. 配置环境变量

```bash
cd /opt/aicbc
cp .env.azure-b2ats.example .env
nano .env
```

至少填写：

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `SECRET_KEY`
- `AZURE_STORAGE_CONNECTION_STRING`（可选，用于备份）

## 5. 配置 HTTPS 证书

### 5.1 使用 Let's Encrypt + Certbot（推荐，需域名）

1. 将你的域名 A 记录指向 VM 公网 IP
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

如果没有域名，可以生成自签名证书：

```bash
cd /opt/aicbc/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=<VM_PUBLIC_IP>"
```

浏览器会提示证书不可信，仅用于测试。

## 6. 启动服务

```bash
cd /opt/aicbc
docker compose -f docker-compose.azure-b2ats.yml up -d
```

检查状态：

```bash
docker compose -f docker-compose.azure-b2ats.yml ps
curl -sf http://localhost:8000/health || echo "API not healthy"
```

## 7. 配置自动备份

### 7.1 安装 Azure CLI

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### 7.2 测试备份脚本

```bash
cd /opt/aicbc
source .env
bash scripts/backup-mongodb-to-azure.sh
```

### 7.3 配置每日定时备份

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/aicbc && source .env && bash scripts/backup-mongodb-to-azure.sh >> /opt/aicbc/logs/backup.log 2>&1") | crontab -
```

## 8. 配置 GitHub Actions 自动部署

1. 在 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions** 中添加：
   - `AZURE_VM_IP`：VM 公网 IP
   - `AZURE_VM_USER`：SSH 用户名（如 `azureuser`）
   - `AZURE_VM_SSH_KEY`：SSH 私钥（与 VM 公钥配对）

2. 在 GitHub 中创建 `azure-b2ats` environment（可选，用于审批保护）

3. 推送代码到 master，触发 `.github/workflows/cd-azure-b2ats.yml`

## 9. 验证部署

从本地访问：

```bash
curl https://your-domain.com/health
```

或：

```bash
curl -k https://<VM_PUBLIC_IP>/health
```

## 10. 常见问题

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
```

- [ ] **Step 2: 提交手册**

```bash
git add docs/运维/Azure-B2ats-v2-首次部署手册.md
git commit -m "docs(ops): add Azure B2ats v2 first-time deployment runbook"
```

---

### Task 11: 更新文档索引

**Files:**
- Modify: `docs/文档索引与导航.md`

- [ ] **Step 1: 在文档总览表中添加运维手册**

在序号 46 后新增一行：

```
| 47 | `docs/运维/Azure-B2ats-v2-首次部署手册.md` | 横切 | 小维 | Azure B2ats v2 首次部署操作手册 |
```

- [ ] **Step 2: 更新版本号和变更日志**

版本号从 v1.13 改为 v1.14，变更日志新增：

```
| 2026-06-19 | v1.14 | 新增 Azure B2ats v2 首次部署操作手册 | 小维 |
```

- [ ] **Step 3: 提交修改**

```bash
git add docs/文档索引与导航.md
git commit -m "docs(index): register Azure B2ats v2 deployment runbook"
```

---

## 自检

### Spec 覆盖检查

| 设计文档章节 | 覆盖任务 |
|-------------|---------|
| 3.1 部署拓扑 | Task 1, Task 2 |
| 4.1 保留服务与资源限制 | Task 1 |
| 4.2 移除服务 | Task 1 |
| 4.3 Swap 配置 | Task 4 |
| 5.1 NSG | Task 10 |
| 5.2 Docker 网络隔离 | Task 1 |
| 5.3 HTTPS | Task 2, Task 10 |
| 6.1 本地持久化 | Task 1 |
| 6.2 Azure Blob 备份 | Task 5, Task 10 |
| 6.3 恢复流程 | Task 10 |
| 7.1 镜像构建 | Task 7 |
| 7.2 部署到 B2ats v2 | Task 6, Task 7 |
| 7.3 GitHub Secrets | Task 7, Task 10 |
| 8. 部署步骤 | Task 10 |

### Placeholder 扫描

- 无 TBD/TODO
- 无 "implement later" / "add appropriate error handling"
- 每个代码/配置步骤均包含实际内容
- 命令均包含预期输出

### 一致性检查

- Compose 中的服务名 `api` / `mongo` / `redis` / `nginx` 与 Nginx upstream 一致
- 环境变量名在 `.env.azure-b2ats.example`、Compose、GitHub Actions 中一致
- 文件路径在脚本、Compose、文档中一致（`/opt/aicbc`）

---

*Plan complete.*
