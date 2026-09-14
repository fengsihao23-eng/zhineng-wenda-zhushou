#!/usr/bin/env python3
"""
最小化启动脚本 - 只启动API文档查看
"""
import os
import sys

# 设置环境变量
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_minimum_32_characters_long")
os.environ.setdefault("DEEPSEEK_API_KEY", "test_key")

# 创建最小化FastAPI应用
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="StudentAgent API",
    description="学生智能问答系统 Phase 2",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "StudentAgent API",
        "version": "2.0.0",
        "status": "running",
        "message": "Phase 2 已实现完成！",
        "features": [
            "✅ 5个Tools: 科目成绩、排名变化、趋势、小题丢分、诊断",
            "✅ StudentContextBuilder - 动态上下文加载",
            "✅ Intent Router - 意图识别",
            "✅ Agent Loop - 轻量循环（最多2轮）",
            "✅ SSE流式输出",
            "✅ Chat API - 完整对话接口"
        ]
    }

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/v1/tools")
async def list_tools():
    """列出所有实现的工具"""
    return {
        "tools": [
            {
                "name": "get_exam_summary",
                "description": "获取考试总结（总分、排名）",
                "file": "app/tools/exam_tools.py"
            },
            {
                "name": "get_subject_scores",
                "description": "获取科目成绩详情",
                "file": "app/tools/score_tools.py"
            },
            {
                "name": "get_ranking_change",
                "description": "获取排名变化对比",
                "file": "app/tools/score_tools.py"
            },
            {
                "name": "get_score_trend",
                "description": "获取成绩趋势（最近N次）",
                "file": "app/tools/analysis_tools.py"
            },
            {
                "name": "get_question_loss",
                "description": "获取小题丢分统计",
                "file": "app/tools/analysis_tools.py"
            },
            {
                "name": "get_diagnosis",
                "description": "获取诊断报告（需DIAGNOSIS权益）",
                "file": "app/tools/analysis_tools.py"
            }
        ]
    }

@app.get("/api/v1/components")
async def list_components():
    """列出所有实现的组件"""
    return {
        "components": [
            {
                "name": "StudentContextBuilder",
                "description": "动态加载学生上下文",
                "file": "app/agent/context.py"
            },
            {
                "name": "IntentRouter",
                "description": "意图识别（规则匹配）",
                "file": "app/agent/intent_router.py"
            },
            {
                "name": "AgentLoop",
                "description": "Agent循环（最多2轮Tool调用）",
                "file": "app/agent/agent_loop.py"
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Phase 2 API 文档服务")
    print("=" * 60)
    print()
    print("📚 API文档: http://localhost:8000/docs")
    print("📖 功能列表: http://localhost:8000/")
    print("🔧 工具列表: http://localhost:8000/api/v1/tools")
    print()
    print("⚠️  这是文档查看模式")
    print("   完整功能需要配置数据库和安装完整依赖")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000)
