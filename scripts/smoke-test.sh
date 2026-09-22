#!/bin/bash

# 快速冒烟测试脚本
# 用于快速验证部署是否成功

set -e

echo "🔥 运行冒烟测试..."

BASE_URL="${BASE_URL:-http://localhost}"

# 健康检查
echo "检查健康端点..."
curl -f "$BASE_URL/health" || {
  echo "✗ 健康检查失败"
  exit 1
}

echo "✓ 健康检查通过"

# 运行冒烟测试
cd apps/web
npx playwright test smoke.spec.ts --project=chromium

echo "✓ 冒烟测试全部通过"
