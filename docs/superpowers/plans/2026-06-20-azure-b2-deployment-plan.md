# Azure B2 系列 AI_CBC 部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Azure B2ats v2（AMD + Linux）虚拟机上完成 AI_CBC 的公网部署，支持 HTTPS 访问和 MongoDB 自动备份。

**Architecture:** 单台 Ubuntu 24.04 LTS 服务器运行 Docker Compose 裁剪版栈（api + mongo + redis + nginx），使用 Let's Encrypt 证书实现 HTTPS，通过 cron 每周备份 MongoDB 数据。

**Tech Stack:** Azure VM, Ubuntu 24.04 LTS, Docker, Docker Compose, Nginx, Let's Encrypt (Certbot), MongoDB, Redis, Bash

---

## 文件结构

| 文件 | 类型 | 职责 |
|------|------|------|
| `scripts/setup-azure-vm.sh` | 已有（小幅修改） | 初始化 VM：安装 Docker、certbot、ufw、git，配置 swap 和防火墙 |
| `scripts/deploy-to-azure-b2ats.sh` | 已有 | 在 VM 上拉取镜像并重启 AI_CBC 服务 |
| `scripts/backup-mongodb-to-azure.sh` | 已有 | 备份 MongoDB，可选上传到 Azure Blob；无 Blob 配置时保留本地备份 |
| `scripts/restore-mongodb.sh` | 新建 | 从本地备份压缩包恢复 MongoDB |
| `.env` | 修改（基于 `.env.example`） | 生产环境配置：LLM key、数据库连接、SECRET_KEY、前端密码哈希 |
| `docker-compose.azure-b2ats.yml` | 已有 | 1 GiB 内存裁剪版服务栈 |
| `docker/nginx.azure-b2ats.conf` | 已有 | Nginx HTTPS 反向代理配置 |

---

### Task 1: 在 Azure 门户创建 VM

**Files:** 无本地文件变更，全部在 Azure 门户操作。

- [ ] **Step 1: 创建资源组（如尚未创建）**

在 [Azure 门户](https://portal.azure.com) 中：
1. 搜索“资源组” → 创建。
2. 选择订阅，填写资源组名称，例如 `rg-aicbc`。
3. 区域选择离你物理位置最近的（如 East Asia / Southeast Asia）。
4. 点击“查看 + 创建” → 创建。

Expected: 资源组 `rg-aicbc` 创建成功。

- [ ] **Step 2: 创建 B2ats v2 Linux 虚拟机**

1. 搜索“虚拟机” → 创建 → Azure 虚拟机。
2. 选择刚才创建的资源组。
3. 虚拟机名称：`aicbc-vm`。
4. 区域：与资源组相同。
5. 可用性选项：无需基础结构冗余。
6. 安全类型：标准。
7. 映像：**Ubuntu Server 24.04 LTS - x64 Gen2**。
8. 大小：选择 **B2ats v2**（如列表中没有，点击“查看所有大小”搜索）。
9. 身份验证类型：**SSH 公钥**。
10. 用户名：`aicbcadmin`（或其他小写英文名）。
11. SSH 公钥源：选择“使用现有公钥”，把本地生成的 SSH 公钥粘贴进去（见 Step 3）。
12. 入站端口规则：选择“允许所选端口”，勾选 **SSH (22)**、**HTTP (80)**、**HTTPS (443)**。
13. 磁盘：默认 30 GB OS 磁盘足够；如需更大可选 64 GB。
14. 网络：保持默认虚拟网络和子网。
15. 点击“查看 + 创建” → 创建。

Expected: 虚拟机 `aicbc-vm` 部署完成，门户显示“运行中”。

- [ ] **Step 3: 生成 SSH 密钥对（如没有）**

在本地终端（PowerShell / Git Bash / WSL）运行：

```bash
ssh-keygen -t ed25519 -C "aicbc-admin" -f ~/.ssh/aicbc_ed25519
```

按回车使用空密码（或设置密码）。

Expected: 生成两个文件 `~/.ssh/aicbc_ed25519`（私钥）和 `~/.ssh/aicbc_ed25519.pub`（公钥）。

- [ ] **Step 4: 记录 VM 公网 IP**

在 Azure 门户 → 虚拟机 → `aicbc-vm` → 概述中，复制“公共 IP 地址”，例如 `20.198.xxx.xxx`。

Expected: 获得一个可 ping 通的公网 IPv4 地址。

- [ ] **Step 5: SSH 登录测试**

在本地终端运行（把 `x.x.x.x` 替换为实际 IP）：

```bash
ssh -i ~/.ssh/aicbc_ed25519 aicbcadmin@x.x.x.x
```

Expected: 成功登录到 Ubuntu，提示符变为 `aicbcadmin@aicbc-vm:~$`。

---

### Task 2: 初始化服务器环境

**Files:**
- Modify: `scripts/setup-azure-vm.sh`

- [ ] **Step 1: 上传并执行 VM 初始化脚本**

在本地终端运行（替换 IP）：

```bash
scp -i ~/.ssh/aicbc_ed25519 scripts/setup-azure-vm.sh aicbcadmin@x.x.x.x:/tmp/
ssh -i ~/.ssh/aicbc_ed25519 aicbcadmin@x.x.x.x "bash /tmp/setup-azure-vm.sh"
```

Expected: 脚本输出安装进度，最后提示“VM 初始化完成”。

- [ ] **Step 2: 重新登录使 docker 组生效**

```bash
ssh -i ~/.ssh/aicbc_ed25519 aicbcadmin@x.x.x.x
```

然后验证：

```bash
docker ps
sudo ufw status
free -h
```

Expected:
- `docker ps` 不报错
- `ufw status` 显示 22/80/443 为 ALLOW
- `free -h` 显示 swap 约 2G

---

### Task 3: 克隆项目并准备环境变量

**Files:**
- Modify: `.env`（基于 `.env.example`）

- [ ] **Step 1: 在 VM 上克隆代码**

在 VM 上执行：

```bash
cd /opt/aicbc
git clone https://github.com/fromwordimport/AI_CBC.git .
```

Expected: 项目代码克隆到 `/opt/aicbc`。

- [ ] **Step 2: 生成前端登录密码哈希**

在本地开发环境（已安装项目依赖）运行：

```bash
uv run python scripts/generate_password_hash.py
```

输入研究员密码和管理员密码，分别记录输出的 bcrypt 哈希值。

Expected: 得到两行类似 `$2b$12$...` 的哈希字符串。

- [ ] **Step 3: 生成安全密钥**

在本地终端运行：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Expected: 得到一串 ≥ 64 字符的随机字符串，作为 `SECRET_KEY`。

- [ ] **Step 4: 创建生产环境 .env**

在 VM 上执行：

```bash
cd /opt/aicbc
cp .env.example .env
nano .env
```

至少修改以下字段（把示例值替换为真实值）：

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx

MONGODB_URL=mongodb://mongo:27017/aicbc
REDIS_URL=redis://redis:6379/0

ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
API_WORKERS=1

SECRET_KEY=你的随机密钥
API_KEY=一个强随机字符串

FRONTEND_RESEARCHER_PASSWORD_HASH=你的研究员密码哈希
FRONTEND_ADMIN_PASSWORD_HASH=你的管理员密码哈希
```

保存后退出（Ctrl+O, Enter, Ctrl+X）。

Expected: `/opt/aicbc/.env` 文件存在且包含真实机密。

---

### Task 4: 配置域名和 HTTPS 证书

**Files:** 无本地文件变更，涉及域名 DNS 和 Certbot 操作。

- [ ] **Step 1: 配置域名 A 记录**

登录你的域名服务商后台：
1. 找到二级域名管理页面。
2. 添加一条 **A 记录**：主机记录填二级域名的前缀（如 `aicbc`），记录值填 VM 公网 IP。
3. TTL 保持默认或 600 秒。
4. 保存。

Expected: 等待几分钟后，本地可解析到该 IP：

```bash
nslookup aicbc.yourdomain.com
```

- [ ] **Step 2: 申请 Let's Encrypt 证书**

在 VM 上执行（替换为你的真实域名和邮箱）：

```bash
sudo certbot certonly --standalone -d aicbc.yourdomain.com --agree-tos --no-eff-email -m your-email@example.com
```

Expected: 显示 `Congratulations! Your certificate and chain have been saved at: /etc/letsencrypt/live/aicbc.yourdomain.com/...`

- [ ] **Step 3: 验证证书文件**

```bash
sudo ls -la /etc/letsencrypt/live/aicbc.yourdomain.com/
```

Expected: 存在 `fullchain.pem` 和 `privkey.pem`。

- [ ] **Step 4: 创建证书挂载目录的符号链接**

项目的 `docker-compose.azure-b2ats.yml` 期望证书挂载到 `./certbot/conf`。执行：

```bash
cd /opt/aicbc
sudo mkdir -p certbot/conf/live certbot/www
sudo cp -r /etc/letsencrypt/live/aicbc.yourdomain.com certbot/conf/live/
sudo cp /etc/letsencrypt/options-ssl-nginx.conf certbot/conf/ 2>/dev/null || true
sudo cp /etc/letsencrypt/ssl-dhparams.pem certbot/conf/ 2>/dev/null || true
```

Expected: `/opt/aicbc/certbot/conf/live/aicbc.yourdomain.com/` 下存在 `fullchain.pem` 和 `privkey.pem`。

---

### Task 5: 创建恢复脚本并配置自动备份

**Files:**
- Create: `scripts/restore-mongodb.sh`

- [ ] **Step 1: 上传恢复脚本到 VM**

在本地终端运行（替换 IP）：

```bash
scp -i ~/.ssh/aicbc_ed25519 scripts/restore-mongodb.sh aicbcadmin@x.x.x.x:/opt/aicbc/scripts/
ssh -i ~/.ssh/aicbc_ed25519 aicbcadmin@x.x.x.x "chmod +x /opt/aicbc/scripts/restore-mongodb.sh"
```

Expected: `/opt/aicbc/scripts/restore-mongodb.sh` 存在且可执行。

- [ ] **Step 2: 添加 cron 每周自动备份**

在 VM 上执行：

```bash
mkdir -p /opt/aicbc/logs
(crontab -l 2>/dev/null; echo "0 3 * * 0 /opt/aicbc/scripts/backup-mongodb-to-azure.sh >> /opt/aicbc/logs/backup.log 2>&1") | crontab -
```

Expected: 执行 `crontab -l` 看到新增的一条每周日凌晨 3 点运行的备份任务。

- [ ] **Step 3: （可选）配置 Azure Blob 上传**

如果你希望备份自动上传到 Azure Blob：
1. 在 Azure 门户创建 Storage Account 和 Container（如 `aicbc-backups`）。
2. 在 VM 的 `/opt/aicbc/.env` 中追加：

```bash
AZURE_STORAGE_CONNECTION_STRING=你的连接串
AZURE_BACKUP_CONTAINER=aicbc-backups
```

Expected: 备份脚本运行时会上传到 Blob；不配置则保留本地备份。

---

### Task 6: 启动 AI_CBC 服务

**Files:** 无本地文件变更，使用已有 `docker-compose.azure-b2ats.yml` 和 `scripts/deploy-to-azure-b2ats.sh`。

- [ ] **Step 1: 首次部署启动服务**

在 VM 上执行：

```bash
cd /opt/aicbc
bash scripts/deploy-to-azure-b2ats.sh
```

Expected: 脚本拉取镜像、启动容器，并输出 `API health check passed` 和 `部署完成`。

- [ ] **Step 2: 检查容器健康状态**

```bash
cd /opt/aicbc
docker compose -f docker-compose.azure-b2ats.yml ps
```

Expected: `api`、`mongo`、`redis`、`nginx` 状态为 `healthy` 或 `running`。

- [ ] **Step 3: 查看启动日志**

```bash
cd /opt/aicbc
docker compose -f docker-compose.azure-b2ats.yml logs -f --tail 50 api
```

按 Ctrl+C 退出日志。

Expected: 没有持续报错，API 正常监听 8000 端口。

---

### Task 7: 验证端到端功能

**Files:** 无本地文件变更。

- [ ] **Step 1: 验证 HTTPS 健康检查**

在本地浏览器访问：

```
https://aicbc.yourdomain.com/health
```

Expected: 浏览器显示绿色锁标志，返回 JSON 健康状态（如 `{"status":"ok"}`）。

- [ ] **Step 2: 验证前端登录**

访问：

```
https://aicbc.yourdomain.com
```

Expected: 出现登录页面，使用设置的研究员/管理员账号密码能成功登录。

- [ ] **Step 3: 验证创建研究和生成画像**

1. 登录后创建一个新的 CBC 研究。
2. 设置属性水平。
3. 生成 10-20 个虚拟消费者画像。

Expected: 页面返回成功，MongoDB 中新增数据。

- [ ] **Step 4: 验证 MongoDB 数据持久化**

在 VM 上执行：

```bash
cd /opt/aicbc
docker compose -f docker-compose.azure-b2ats.yml exec mongo mongosh aicbc --eval "db.studies.countDocuments()"
```

Expected: 返回大于 0 的数字，表示研究数据已写入。

- [ ] **Step 5: 验证备份脚本**

在 VM 上执行：

```bash
/opt/aicbc/scripts/backup-mongodb-to-azure.sh
```

Expected: 在 `/opt/aicbc/backups/mongo/` 下生成一个 `YYYYMMDD_HHMMSS.tar.gz` 文件。

- [ ] **Step 6: 验证证书自动续期**

```bash
sudo certbot renew --dry-run
```

Expected: 显示续期模拟成功，无错误。

---

## 自评检查

**1. Spec coverage:**
- 服务器角色分配：Task 1 只创建 B2ats v2 Linux VM，其他三台不使用 ✓
- 操作系统：Task 1 选择 Ubuntu 24.04 LTS ✓
- 网络安全：Task 1 配置 NSG 22/80/443，Task 2 配置 UFW ✓
- HTTPS：Task 4 配置域名 + Certbot + 证书挂载 ✓
- 数据持久化：Task 5 配置自动备份和恢复脚本 ✓
- 环境变量：Task 3 配置 `.env` ✓
- 启动服务：Task 6 使用部署脚本启动 ✓
- 验证：Task 7 端到端验证 ✓

**2. Placeholder scan:**
- 无 TBD/TODO
- 所有命令带具体参数
- 所有路径明确

**3. 类型一致性：**
- 所有步骤使用 `docker-compose.azure-b2ats.yml`
- 备份/恢复脚本路径一致
- `.env` 中的 `MONGODB_URL`/`REDIS_URL` 与裁剪版 Compose 一致

---

## 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-06-20-azure-b2-deployment-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
