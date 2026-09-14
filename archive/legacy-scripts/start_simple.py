#!/usr/bin/env python3
"""
简化版启动脚本 - 用于快速测试
不依赖数据库，直接启动API服务查看文档
"""
import os
import sys

# 设置环境变量（临时测试用）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_minimum_32_characters_long_for_testing")
os.environ.setdefault("DEEPSEEK_API_KEY", "test_key")
os.environ.setdefault("DEBUG", "true")

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🚀 启动简化版 API 服务（用于查看文档）")
    print("=" * 60)
    print()
    print("📚 API 文档: http://localhost:8000/docs")
    print("📖 ReDoc: http://localhost:8000/redoc")
    print("🔍 健康检查: http://localhost:8000/api/health")
    print()
    print("⚠️  注意: 这是测试模式，部分功能需要配置真实数据库")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
