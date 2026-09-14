#!/bin/bash
# 初始化Prompt模板

set -e

echo "🔧 Initializing Prompt templates..."

cd "$(dirname "$0")/../apps/api"

# 运行初始化脚本
python -m scripts.init_prompts

echo "✅ Prompts initialized successfully!"
