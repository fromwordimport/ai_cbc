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
