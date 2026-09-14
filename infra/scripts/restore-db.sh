#!/bin/bash
# 数据库恢复脚本

set -e

BACKUP_FILE=$1
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-intelligent_qa}"

if [ -z "$BACKUP_FILE" ]; then
    echo "用法: ./restore-db.sh <backup_file>"
    echo "示例: ./restore-db.sh /backups/intelligent_qa_20260910_120000.sql.gz"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "错误: 备份文件不存在: $BACKUP_FILE"
    exit 1
fi

echo "准备恢复数据库: $POSTGRES_DB"
echo "备份文件: $BACKUP_FILE"
read -p "确认恢复？这将覆盖现有数据 (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "取消恢复"
    exit 1
fi

# 解压备份文件（如果是 .gz 格式）
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "解压备份文件..."
    TEMP_FILE="${BACKUP_FILE%.gz}"
    gunzip -c "$BACKUP_FILE" > "$TEMP_FILE"
    RESTORE_FILE="$TEMP_FILE"
else
    RESTORE_FILE="$BACKUP_FILE"
fi

# 恢复数据库
echo "开始恢复..."
docker compose exec -T db psql \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    < "$RESTORE_FILE"

# 清理临时文件
if [[ "$BACKUP_FILE" == *.gz ]]; then
    rm -f "$TEMP_FILE"
fi

echo "数据库恢复完成"
