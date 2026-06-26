#!/usr/bin/env bash
set -euo pipefail

# check-tunnel.sh — 验证 cloudflared 隧道容器健康状态
# 返回：exit 0 表示运行正常，exit 1 表示异常

CONTAINER_NAME="cloudflared"
LOG_TAIL_LINES=30

echo "=== cloudflared 隧道健康检查 ==="
echo ""

# 1. 打印最近日志
echo "--- 最近 ${LOG_TAIL_LINES} 行日志 ---"
if docker logs --tail "${LOG_TAIL_LINES}" "${CONTAINER_NAME}" 2>/dev/null; then
    echo ""
else
    echo "错误：无法获取 ${CONTAINER_NAME} 容器日志（容器可能不存在）"
    exit 1
fi

echo ""

# 2. 检查容器是否正在运行
if docker ps -q -f name="^/${CONTAINER_NAME}$" | grep -q .; then
    echo "状态：${CONTAINER_NAME} 容器正在运行"
    exit 0
else
    echo "错误：${CONTAINER_NAME} 容器未在运行"
    exit 1
fi
