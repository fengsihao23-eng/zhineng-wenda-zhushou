#!/bin/bash
# Phase 1 快速验证脚本

set -e

echo "🚀 Phase 1 实施验证脚本"
echo "========================================"

# 1. 检查Docker服务
echo ""
echo "📦 1. 检查Docker服务..."
docker-compose ps

# 2. 启动数据库和Redis
echo ""
echo "🔧 2. 启动PostgreSQL和Redis..."
docker compose up -d db redis
sleep 5

# 3. 检查服务健康
echo ""
echo "🏥 3. 检查服务健康..."
docker compose ps db redis

# 4. 运行数据库Migration
echo ""
echo "📊 4. 运行数据库Migration..."
cd apps/api
alembic upgrade head
cd ../..

# 5. 初始化测试数据
echo ""
echo "🎲 5. 初始化测试数据..."
python apps/api/init_test_data.py

# 6. 启动API服务
echo ""
echo "🌐 6. 启动API服务..."
docker-compose up -d api

# 7. 等待API启动
echo ""
echo "⏳ 7. 等待API服务就绪..."
sleep 10

# 8. 测试健康检查
echo ""
echo "✅ 8. 测试健康检查..."
curl -s http://localhost:8000/api/v1/health | jq .

# 9. 测试登录
echo ""
echo "🔐 9. 测试登录..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test_student","password":"password123"}')

echo "$LOGIN_RESPONSE" | jq .

# 提取token
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r .access_token)

if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
    echo "✅ 登录成功，获得访问令牌"

    # 10. 测试获取用户信息
    echo ""
    echo "👤 10. 测试获取用户信息..."
    curl -s -X GET http://localhost:8000/api/v1/auth/me \
      -H "Authorization: Bearer $ACCESS_TOKEN" | jq .

    echo ""
    echo "========================================"
    echo "✅ Phase 1 验证完成！"
    echo "========================================"
    echo ""
    echo "📝 下一步："
    echo "  - 可以使用Postman或curl测试API"
    echo "  - Access Token: $ACCESS_TOKEN"
    echo "  - API文档: http://localhost:8000/docs"
else
    echo "❌ 登录失败"
    exit 1
fi
