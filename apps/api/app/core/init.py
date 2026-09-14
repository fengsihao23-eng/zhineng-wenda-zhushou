"""
初始化工具并注册到应用启动
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.tools.init import init_tools
from app.tools.registry import get_tool_registry
from app.core.default_prompts import ensure_default_prompts


async def startup_init_tools(db: AsyncSession):
    """应用启动时初始化工具"""
    registry = get_tool_registry()
    init_tools(db, registry)
    await ensure_default_prompts(db)
    return registry
