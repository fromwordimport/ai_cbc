#!/usr/bin/env bash
# AI_CBC Azure B2ats v2 服务器端部署脚本
# 由 GitHub Actions 通过 SSH 调用，也可在服务器上手动执行

set -euo pipefail

APP_DIR="/opt/aicbc"
COMPOSE_FILE="$APP_DIR/docker-compose.azure-b2ats.yml"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 1. 进入应用目录
cd "$APP_DIR" || { echo "ERROR: 无法进入目录 $APP_DIR" >&2; exit 1; }

# 2. 预检
if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: docker 命令未安装"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    log "ERROR: Docker daemon 未运行"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    log "ERROR: Compose 文件不存在：$COMPOSE_FILE"
    exit 1
fi

log "开始部署 AI_CBC 到 Azure B2ats v2..."

# 3. 拉取最新镜像（不在服务器上构建）
if ! docker compose -f "$COMPOSE_FILE" pull; then
    log "ERROR: 镜像拉取失败，保留当前运行中的服务"
    exit 1
fi

# 4. 停止并重新启动服务
log "重启服务..."
docker compose -f "$COMPOSE_FILE" down
docker compose -f "$COMPOSE_FILE" up -d

# 5. 等待 API 健康（最多 90 秒）
log "等待 API 健康检查..."
for i in {1..45}; do
    if curl -sf http://localhost:8000/health > /dev/null; then
        log "API health check passed"
        break
    fi
    log "Waiting for API health... ($i/45)"
    sleep 2
done

if ! curl -sf http://localhost:8000/health > /dev/null; then
    log "ERROR: API health check failed after 90 seconds"
    exit 1
fi

# 6. 清理旧镜像，防止小磁盘耗尽
log "清理超过 24 小时的未使用镜像..."
docker image prune -f --filter "until=24h" || true

log "部署完成"
