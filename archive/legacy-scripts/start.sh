#!/bin/bash
# Phase 2 启动脚本

echo "================================"
echo "启动 Phase 2 服务"
echo "================================"

# 1. 检查依赖
echo ""
echo "1️⃣ 检查 Python 依赖..."
cd /Users/hao/智能问答助手/apps/api

if ! pip show fastapi > /dev/null 2>&1; then
    echo "⚠️  未安装依赖，正在安装..."
    pip install -r requirements.txt
else
    echo "✅ 依赖已安装"
fi

# 2. 检查环境变量
echo ""
echo "2️⃣ 检查环境变量..."
if [ ! -f .env ]; then
    echo "❌ 未找到 .env 文件"
    echo "请先配置 .env 文件（尤其是 DEEPSEEK_API_KEY 或 OPENAI_API_KEY）"
    exit 1
else
    echo "✅ .env 文件存在"
fi

# 3. 提示数据库配置
echo ""
echo "3️⃣ 数据库配置"
echo "请确保 PostgreSQL 已启动（端口 5432）"
echo "如果使用 Docker: docker compose up -d db redis"
echo ""
read -p "数据库已启动？按回车继续，或 Ctrl+C 退出..."

# 4. 启动 API 服务
echo ""
echo "4️⃣ 启动 API 服务..."
echo "服务将在 http://localhost:8000 启动"
echo "API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

export PYTHONPATH=$PWD:$PYTHONPATH
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
