#!/bin/bash
# 健康检查脚本

set -e

WEB_URL="${WEB_URL:-http://localhost/}"
API_URL="${API_URL:-http://localhost/api/v1}"

check_service() {
    local service=$1
    local url=$2

    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")

    if [ "$response" -eq 200 ]; then
        echo "✓ $service 健康 (HTTP $response)"
        return 0
    else
        echo "✗ $service 异常 (HTTP $response)"
        return 1
    fi
}

echo "===================="
echo "健康检查开始"
echo "===================="

check_service "Web" "$WEB_URL/"
check_service "API" "$API_URL/health"
check_service "数据库" "$API_URL/health/db"
check_service "Redis" "$API_URL/health/redis"

echo "===================="
echo "健康检查完成"
echo "===================="
