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

# 健康检查：等待最多 30 秒，检查日志中是否出现成功注册隧道的标志
MAX_WAIT=30
INTERVAL=2
ELAPSED=0
echo "等待 cloudflared 隧道连接注册..."
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    if docker logs cloudflared 2>/dev/null | grep -qE "Registered tunnel connection|Active"; then
        echo "cloudflared 隧道连接已注册"
        exit 0
    fi
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "错误：cloudflared 在 ${MAX_WAIT} 秒内未能成功注册隧道连接"
echo "--- 最近 30 行日志 ---"
docker logs --tail 30 cloudflared 2>/dev/null || echo "无法获取容器日志"
exit 1
