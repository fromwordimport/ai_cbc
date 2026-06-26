#!/usr/bin/env bash
set -euo pipefail

echo "测试 Cloudflare HTTPS 连通性..."
curl -fsSI https://cloudflare.com > /dev/null || { echo "FAIL: 无法访问 https://cloudflare.com"; exit 1; }

echo "测试 Docker Hub 镜像拉取..."
docker pull hello-world > /dev/null || { echo "FAIL: 无法从 Docker Hub 拉取镜像"; exit 1; }
docker rmi hello-world > /dev/null || true

echo "测试 GitHub 仓库访问..."
cd /opt/aicbc
git fetch origin master || { echo "FAIL: 无法 fetch GitHub"; exit 1; }

echo "PASS: 默认出站访问可用"
