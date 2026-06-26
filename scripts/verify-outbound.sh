#!/usr/bin/env bash
set -euo pipefail

echo "测试 Cloudflare HTTPS 连通性..."
curl --max-time 10 -fsSI https://cloudflare.com > /dev/null || { echo "FAIL: 无法访问 https://cloudflare.com"; exit 1; }

echo "测试 Docker Hub 镜像拉取..."
timeout 60 docker pull hello-world > /dev/null || { echo "FAIL: 无法从 Docker Hub 拉取镜像"; exit 1; }
docker rmi hello-world > /dev/null || true

echo "测试 GitHub 仓库访问..."
APP_DIR="${APP_DIR:-/opt/aicbc}"
if [[ ! -d "$APP_DIR" ]]; then
    echo "FAIL: 目录不存在: $APP_DIR"
    exit 1
fi
if [[ ! -d "$APP_DIR/.git" ]]; then
    echo "FAIL: 目录不是 git 仓库: $APP_DIR"
    exit 1
fi
cd "$APP_DIR"
git fetch origin master || { echo "FAIL: 无法 fetch GitHub"; exit 1; }

echo "PASS: 默认出站访问可用"
