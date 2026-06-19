#!/usr/bin/env bash
# AI_CBC Azure B2ats v2 VM 初始化脚本
# 用法：以普通用户身份通过 SSH 登录后执行

set -euo pipefail

APP_DIR="/opt/aicbc"

# 1. 更新系统
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# 2. 安装 Docker（使用 Docker 官方安装脚本）
# 参考：https://docs.docker.com/engine/install/ubuntu/
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

# 4. 创建应用目录（幂等：仅当不存在时创建并设置属主）
if [ ! -d "$APP_DIR" ]; then
    sudo mkdir -p "$APP_DIR"
    sudo chown "$USER:$USER" "$APP_DIR"
fi

# 5. 创建子目录
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/backups/mongo"
mkdir -p "$APP_DIR/ssl"
mkdir -p "$APP_DIR/certbot/www"
mkdir -p "$APP_DIR/certbot/conf"

echo "VM 初始化完成。下一步：克隆项目到 $APP_DIR 并配置 .env"
