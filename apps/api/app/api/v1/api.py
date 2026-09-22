"""
API v1 路由
"""
from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, chat, prompts, traces, platform
from app.api.v1.endpoints import management_details, education

api_router = APIRouter()

# 健康检查
api_router.include_router(health.router, prefix="/health", tags=["health"])

# 认证
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# 对话
api_router.include_router(chat.router, tags=["chat"])

# Admin - Prompt管理
api_router.include_router(prompts.router, prefix="/admin", tags=["admin", "prompts"])

# Admin - Trace查询
api_router.include_router(traces.router, prefix="/admin", tags=["admin", "traces"])

# Student analytics, role workbenches and governance workflows
api_router.include_router(platform.router)
api_router.include_router(management_details.router)
api_router.include_router(education.router)
