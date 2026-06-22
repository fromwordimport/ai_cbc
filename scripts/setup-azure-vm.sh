#!/usr/bin/env bash
# AI_CBC Azure B2ats v2 VM 初始化脚本
# 用法：以具有 sudo 权限的普通用户身份通过 SSH 登录后执行

set -euo pipefail

APP_DIR="/opt/aicbc"

# 1. 更新系统
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# 2. 确保基础工具已安装
sudo apt-get install -y curl git certbot ufw openssl

# 3. 安装 Docker（使用 Docker 官方安装脚本）
# 参考文档：https://docs.docker.com/engine/install/ubuntu/
if ! command -v docker &> /dev/null; then
    # 注意：脚本后续步骤不依赖 Docker 命令，因此无需在当前会话中刷新组权限。
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker 已安装。请重新登录以应用 docker 用户组权限。"
fi

# 4. 配置 2GB swap
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 5. 配置 UFW 防火墙（仅开放 22/80/443）
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# 6. 创建应用目录及子目录（幂等）
# 目录归当前执行用户所有，便于后续 git clone 和 docker compose 操作
sudo mkdir -p "$APP_DIR"/{logs,backups/mongo,ssl,certbot/{www,conf}}
sudo chown -R "$(whoami):$(whoami)" "$APP_DIR"

# 7. 生成 Redis 密码（若尚未生成）
if [ ! -f "$APP_DIR/.redis_password" ]; then
    REDIS_PASSWORD=$(openssl rand -base64 32)
    echo "$REDIS_PASSWORD" > "$APP_DIR/.redis_password"
    chmod 600 "$APP_DIR/.redis_password"
    echo "Redis 密码已生成并保存到 $APP_DIR/.redis_password"
    echo "请将其写入 .env：REDIS_PASSWORD=$REDIS_PASSWORD"
fi

# 8. 可选：若设置了 AZURE_WORKER_SUBNET，则允许 worker 子网访问 Redis 与 MongoDB
if [ -n "${AZURE_WORKER_SUBNET:-}" ]; then
    sudo ufw allow from "$AZURE_WORKER_SUBNET" to any port 6379 proto tcp
    sudo ufw allow from "$AZURE_WORKER_SUBNET" to any port 27017 proto tcp
    echo "已允许 worker 子网 $AZURE_WORKER_SUBNET 访问 6379/27017"
fi

echo "VM 初始化完成。下一步：克隆项目到 $APP_DIR 并配置 .env"
