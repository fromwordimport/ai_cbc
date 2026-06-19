#!/usr/bin/env bash
# AI_CBC MongoDB 备份并上传至 Azure Blob
# 建议在服务器上通过 cron 每日执行一次
#
# 注意：docker-compose.azure-b2ats.yml 已将宿主机的 ./backups/mongo 挂载到容器的 /backup，
# 因此 docker exec 内执行 mongodump --out /backup/<timestamp> 会直接写入宿主机备份目录。

set -euo pipefail

BACKUP_BASE="/opt/aicbc/backups/mongo"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
RETENTION_DAYS=7
LOCK_FILE="/opt/aicbc/backups/.backup.lock"

# Azure Blob 配置（从环境读取）
AZURE_STORAGE_CONNECTION_STRING="${AZURE_STORAGE_CONNECTION_STRING:-}"
AZURE_BACKUP_CONTAINER="${AZURE_BACKUP_CONTAINER:-aicbc-backups}"

cleanup() {
    local exit_code=$?
    if [ -n "${BACKUP_DIR:-}" ] && [ -d "$BACKUP_DIR" ]; then
        rm -rf "$BACKUP_DIR"
    fi
    if [ -n "${TIMESTAMP:-}" ] && [ -f "$BACKUP_BASE/$TIMESTAMP.tar.gz" ]; then
        rm -f "$BACKUP_BASE/$TIMESTAMP.tar.gz"
    fi
    # 无论成功或失败，都清理超过保留期的本地备份
    if [ -d "$BACKUP_BASE" ]; then
        find "$BACKUP_BASE" -maxdepth 1 -name "*.tar.gz" -type f -mtime +"$RETENTION_DAYS" -exec rm -f {} +
    fi
    return $exit_code
}
trap cleanup EXIT

# 防止并发执行
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "ERROR: 另一个 MongoDB 备份进程正在运行" >&2
    exit 1
fi

# 预检：依赖命令
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker 命令未安装" >&2
    exit 1
fi

if ! command -v az >/dev/null 2>&1; then
    echo "ERROR: Azure CLI (az) 未安装" >&2
    exit 1
fi

# 预检：确认 MongoDB 容器在运行
if ! docker ps --format '{{.Names}}' | grep -qx "aicbc-mongo"; then
    echo "ERROR: aicbc-mongo 容器未运行，跳过备份" >&2
    exit 1
fi

# 1. 执行 mongodump（输出到容器 /backup，实际即宿主机 $BACKUP_DIR）
mkdir -p "$BACKUP_DIR"
docker exec aicbc-mongo mongodump --out "/backup/$TIMESTAMP"

# 2. 压缩备份
cd "$BACKUP_BASE" || { echo "ERROR: 无法进入备份目录 $BACKUP_BASE" >&2; exit 1; }
tar czf "$TIMESTAMP.tar.gz" "$TIMESTAMP"
rm -rf "$TIMESTAMP"

# 3. 上传到 Azure Blob（如果配置了连接串）
if [ -n "$AZURE_STORAGE_CONNECTION_STRING" ]; then
    if az storage blob upload \
        --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
        --container-name "$AZURE_BACKUP_CONTAINER" \
        --file "$TIMESTAMP.tar.gz" \
        --name "aicbc-mongo-$TIMESTAMP.tar.gz" \
        --overwrite false; then
        echo "备份已上传：aicbc-mongo-$TIMESTAMP.tar.gz"
    else
        echo "ERROR: Azure Blob 上传失败，本地备份保留在：$BACKUP_BASE/$TIMESTAMP.tar.gz" >&2
        exit 1
    fi
else
    echo "未配置 AZURE_STORAGE_CONNECTION_STRING，备份保留在本地：$BACKUP_BASE/$TIMESTAMP.tar.gz"
fi

echo "MongoDB 备份完成：$TIMESTAMP.tar.gz"
