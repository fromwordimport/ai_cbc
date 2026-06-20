#!/usr/bin/env bash
# AI_CBC MongoDB 本地恢复脚本
# 用法：/opt/aicbc/scripts/restore-mongodb.sh <备份压缩包路径>
#
# 示例：
#   /opt/aicbc/scripts/restore-mongodb.sh /opt/aicbc/backups/mongo/20260101_120000.tar.gz

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <backup-archive-path>" >&2
    echo "Example: $0 /opt/aicbc/backups/mongo/20260101_120000.tar.gz" >&2
    exit 1
fi

ARCHIVE="$1"
APP_DIR="/opt/aicbc"
BACKUP_BASE="$APP_DIR/backups/mongo"
RESTORE_DIR="$BACKUP_BASE/restore_tmp"

if [ ! -f "$ARCHIVE" ]; then
    echo "ERROR: 备份文件不存在：$ARCHIVE" >&2
    exit 1
fi

# 预检：确认 MongoDB 容器在运行
if ! docker ps --format '{{.Names}}' | grep -qx "aicbc-mongo"; then
    echo "ERROR: aicbc-mongo 容器未运行" >&2
    exit 1
fi

echo "==> 解压备份文件：$ARCHIVE"
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"
tar xzf "$ARCHIVE" -C "$RESTORE_DIR"

DUMP_NAME=$(ls "$RESTORE_DIR")
echo "==> 从 dump 恢复：$DUMP_NAME"
cd "$APP_DIR"
docker compose -f docker-compose.azure-b2ats.yml exec -T mongo mongorestore --drop "/backup/restore_tmp/$DUMP_NAME"

rm -rf "$RESTORE_DIR"
echo "==> MongoDB 恢复完成"
