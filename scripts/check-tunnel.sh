#!/usr/bin/env bash
set -euo pipefail

# 检查 cloudflared 容器是否运行
if docker ps -q -f name=cloudflared | grep -q .; then
    echo "=== cloudflared 容器状态: 运行中 ==="
    echo
    echo "=== 最近 30 行日志 ==="
    docker logs --tail 30 cloudflared 2>/dev/null || echo "无法获取容器日志"
    exit 0
else
    echo "=== cloudflared 容器状态: 未运行 ==="
    echo
    echo "=== 最近 30 行日志（如有） ==="
    docker logs --tail 30 cloudflared 2>/dev/null || echo "无法获取容器日志"
    exit 1
fi
