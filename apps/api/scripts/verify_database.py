"""验证数据库表结构"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from app.core.config import settings


async def verify_database():
    """验证数据库表"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    expected_tables = [
        # 身份表
        "schools", "users", "roles", "user_roles", "students",
        # 考试表
        "exams", "subjects", "exam_subjects",
        # 成绩表
        "student_exam_scores", "student_subject_scores", "question_scores",
        # 诊断表
        "diagnosis_reports", "student_entitlements",
        # Chat表
        "chat_sessions", "chat_messages",
        # Trace表
        "agent_runs", "tool_call_logs", "model_usage_logs", "audit_logs",
        # Prompt表
        "prompt_templates"
    ]

    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ))
        existing_tables = [row[0] for row in result]

    print("="*60)
    print("数据库表验证")
    print("="*60)

    missing_tables = []
    existing_required = []
    for table in expected_tables:
        if table in existing_tables:
            existing_required.append(table)
            print(f"✅ {table}")
        else:
            print(f"❌ {table} (缺失)")
            missing_tables.append(table)

    print("="*60)
    print(f"\n已存在的表: {len(existing_required)}/{len(expected_tables)}")

    if missing_tables:
        print(f"⚠️  缺失 {len(missing_tables)} 个表:")
        for table in missing_tables:
            print(f"   - {table}")
        print("\n建议:")
        print("1. 检查迁移历史: docker compose -p intelligent-qa exec api alembic history")
        print("2. 创建新迁移: docker compose -p intelligent-qa exec api alembic revision --autogenerate -m 'add_missing_tables'")
        print("3. 执行迁移: docker compose -p intelligent-qa exec api alembic upgrade head")
    else:
        print("✅ 所有必需的表都已创建")

    print("="*60)

    # 显示其他表（不在预期列表中的）
    other_tables = [t for t in existing_tables if t not in expected_tables and t != 'alembic_version']
    if other_tables:
        print(f"\n其他表 ({len(other_tables)}):")
        for table in other_tables:
            print(f"   - {table}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_database())
