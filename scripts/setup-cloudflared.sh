#!/usr/bin/env bash
set -euo pipefail

TUNNEL_TOKEN="${CF_TUNNEL_TOKEN:?环境变量 CF_TUNNEL_TOKEN 未设置}"

if docker ps -q -f name=cloudflared | grep -q .; then
    echo "cloudflared 容器已运行，先停止"
    docker stop cloudflared || true
    docker rm cloudflared || true
fi

docker run -d \
  --name cloudflared \
  --restart unless-stopped \
  --network host \
  -e TUNNEL_TOKEN="$TUNNEL_TOKEN" \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run --token "$TUNNEL_TOKEN"

echo "cloudflared 已启动"
