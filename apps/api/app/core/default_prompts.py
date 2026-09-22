"""Idempotent built-in prompts used by every deployment."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prompt import PromptTemplate


DEFAULT_PROMPTS = [
    {
        "name": "student_qa_system",
        "scene": "chat",
        "content": """你是学校学生智能问答助手。\n学生姓名：{{ student_name }}\n学校：{{ school_name }}\n权益等级：{{ entitlement_level }}\n\n只根据已提供的本人数据回答，不编造考试、分数、排名或诊断结论。先给结论，再给关键事实；涉及数据时保留考试名称。BASIC 用户不能获得薄弱点诊断；DIAGNOSIS 用户只能解释正式报告已有结论。遇到风险、隐私或无法确认的请求，说明限制并建议联系老师。\n\n当前上下文：\n{{ context }}""",
        "variables": ["student_name", "school_name", "entitlement_level", "context"],
        "description": "学生问答主 Prompt，部署启动时自动初始化",
    },
]


async def ensure_default_prompts(db: AsyncSession) -> int:
    """Create and publish missing built-in prompts without duplicate versions."""
    changed = 0
    for item in DEFAULT_PROMPTS:
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.name == item["name"],
                PromptTemplate.version == "v1",
            )
        )
        prompt = result.scalar_one_or_none()
        if prompt is None:
            # Multiple workers can bootstrap an empty database concurrently.
            # A deployed draft/deprecated version is an explicit decision;
            # startup must never silently publish it again.
            insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
            created = await db.scalar(insert(PromptTemplate).values(**item, version="v1", status="published")
                                      .on_conflict_do_nothing(index_elements=["name", "version"])
                                      .returning(PromptTemplate.id))
            changed += int(created is not None)
    if changed:
        await db.commit()
    return changed
