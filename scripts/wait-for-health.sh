#!/bin/bash

# 等待服务健康检查通过的脚本

MAX_RETRIES=30
RETRY_INTERVAL=5
HEALTH_URL="${HEALTH_URL:-http://localhost/health}"

echo "等待服务启动: $HEALTH_URL"

for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试 $i/$MAX_RETRIES..."

  if curl -f -s "$HEALTH_URL" > /dev/null; then
    echo "✓ 服务已就绪!"
    exit 0
  fi

  if [ $i -lt $MAX_RETRIES ]; then
    echo "服务未就绪，等待 ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
  fi
done

echo "✗ 服务启动超时"
exit 1
