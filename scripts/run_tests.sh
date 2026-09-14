#!/bin/bash
# 运行所有测试

set -euo pipefail

echo "🧪 Running tests..."

# 进入API目录
cd "$(dirname "$0")/../apps/api"

# 安装测试依赖
echo "📦 Installing test dependencies..."
python -m pip install -r requirements.txt
python -m pip install -r requirements-test.txt

# 运行测试
echo "🚀 Running pytest..."
python -m pytest -q

echo "✅ All tests passed!"
