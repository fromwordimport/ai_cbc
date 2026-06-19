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
