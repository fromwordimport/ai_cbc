#!/usr/bin/env bash
# AI_CBC MongoDB 备份并上传至 Azure Blob
# 建议在服务器上通过 cron 每日执行一次

set -euo pipefail

BACKUP_BASE="/opt/aicbc/backups/mongo"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE/$TIMESTAMP"
RETENTION_DAYS=7

# Azure Blob 配置（从环境读取）
AZURE_STORAGE_CONNECTION_STRING="${AZURE_STORAGE_CONNECTION_STRING:-}"
AZURE_BACKUP_CONTAINER="${AZURE_BACKUP_CONTAINER:-aicbc-backups}"

# 1. 执行 mongodump
mkdir -p "$BACKUP_DIR"
docker exec aicbc-mongo mongodump --out "/backup/$TIMESTAMP"

# 2. 压缩备份
cd "$BACKUP_BASE"
tar czf "$TIMESTAMP.tar.gz" "$TIMESTAMP"
rm -rf "$TIMESTAMP"

# 3. 上传到 Azure Blob（如果配置了连接串）
if [ -n "$AZURE_STORAGE_CONNECTION_STRING" ]; then
    az storage blob upload \
        --connection-string "$AZURE_STORAGE_CONNECTION_STRING" \
        --container-name "$AZURE_BACKUP_CONTAINER" \
        --file "$TIMESTAMP.tar.gz" \
        --name "aicbc-mongo-$TIMESTAMP.tar.gz" \
        --overwrite false
    echo "备份已上传：aicbc-mongo-$TIMESTAMP.tar.gz"
else
    echo "未配置 AZURE_STORAGE_CONNECTION_STRING，备份保留在本地：$BACKUP_DIR.tar.gz"
fi

# 4. 清理本地旧备份
find "$BACKUP_BASE" -name "*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

echo "MongoDB 备份完成：$TIMESTAMP.tar.gz"
