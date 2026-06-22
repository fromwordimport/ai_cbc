#!/usr/bin/env bash
# AI_CBC Azure Worker VM (ARM64) 部署脚本
# 由 GitHub Actions 通过 SSH 调用，也可在 worker VM 上手动执行

set -euo pipefail

APP_DIR="/opt/aicbc"
COMPOSE_FILE="$APP_DIR/docker-compose.azure-worker.yml"

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

# 3. 检查跨机连接必需的环境变量
if [ -z "${AZURE_MAIN_VM_IP:-}" ]; then
    log "ERROR: 环境变量 AZURE_MAIN_VM_IP 未设置"
    exit 1
fi

log "开始部署 AI_CBC Worker 到 Azure Worker VM..."

# 4. 拉取最新镜像（ARM64 由多平台构建支持）
if ! docker compose -f "$COMPOSE_FILE" pull; then
    log "ERROR: 镜像拉取失败，保留当前运行中的服务"
    exit 1
fi

# 5. 停止并重新启动 worker 服务
log "重启 worker 服务..."
docker compose -f "$COMPOSE_FILE" down
docker compose -f "$COMPOSE_FILE" up -d

# 6. 等待 worker 进程启动（最多 60 秒）
log "等待 worker 健康检查..."
for i in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T worker supervisorctl -c /etc/supervisor/conf.d/supervisord.conf status worker | grep -q "RUNNING"; then
        log "Worker health check passed"
        break
    fi
    log "Waiting for worker... ($i/30)"
    sleep 2
done

if ! docker compose -f "$COMPOSE_FILE" exec -T worker supervisorctl -c /etc/supervisor/conf.d/supervisord.conf status worker | grep -q "RUNNING"; then
    log "ERROR: Worker health check failed after 60 seconds"
    exit 1
fi

# 7. 清理旧镜像，防止小磁盘耗尽
log "清理超过 24 小时的未使用镜像..."
docker image prune -f --filter "until=24h" || true

log "Worker 部署完成"
