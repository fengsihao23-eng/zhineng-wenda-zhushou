#!/bin/bash
# 数据库备份脚本

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-intelligent_qa}"

echo "开始备份数据库: $POSTGRES_DB"
echo "备份时间: $TIMESTAMP"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份数据库
docker compose exec -T db pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean \
    --if-exists \
    > "$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql"

# 压缩备份文件
gzip "$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql"

echo "备份完成: ${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

# 保留最近 7 天的备份
find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime +7 -delete

echo "旧备份已清理（保留最近7天）"
