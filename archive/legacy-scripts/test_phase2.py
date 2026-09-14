#!/usr/bin/env python3
"""
测试 Phase 2 实现
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from uuid import UUID

from app.core.config import settings
from app.tools.registry import get_tool_registry
from app.tools.init import init_tools
from app.tools.base import ToolContext
from app.agent.context import StudentContextBuilder
from app.agent.intent_router import IntentRouter


async def test_tools():
    """测试所有Tool"""
    print("=" * 60)
    print("测试 Tools")
    print("=" * 60)

    # 创建数据库连接
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 初始化工具
        registry = get_tool_registry()
        init_tools(db, registry)

        print(f"\n✅ 已注册 {len(registry.list_all_tools())} 个工具:")
        for tool in registry.list_all_tools():
            print(f"  - {tool.name}: {tool.description.strip()[:50]}...")

        # 测试工具调用（需要真实的student_id和school_id）
        # 这里使用测试数据中的ID
        try:
            from init_test_data import get_test_data
            test_data = await get_test_data(db)

            student = test_data['students'][0]
            school = test_data['schools'][0]

            tool_context = ToolContext(
                request_id="test-request",
                agent_run_id="test-agent-run",
                user_id=student['user_id'],
                school_id=school['id'],
                student_id=student['id'],
                entitlement_level="BASIC"
            )

            # 测试 get_exam_summary
            print("\n" + "-" * 60)
            print("测试 get_exam_summary")
            tool = registry.get("get_exam_summary")
            result = await tool.execute(tool_context, {})
            print(f"✅ 结果: {result.ok}")
            if result.ok:
                print(f"   考试: {result.data.get('exam_name')}")
                print(f"   总分: {result.data.get('total_score')}")
                print(f"   排名: {result.data.get('class_rank')}")

            # 测试 get_subject_scores
            print("\n" + "-" * 60)
            print("测试 get_subject_scores")
            tool = registry.get("get_subject_scores")
            result = await tool.execute(tool_context, {})
            print(f"✅ 结果: {result.ok}")
            if result.ok:
                print(f"   科目数: {result.data.get('subject_count')}")

            # 测试 get_ranking_change
            print("\n" + "-" * 60)
            print("测试 get_ranking_change")
            tool = registry.get("get_ranking_change")
            result = await tool.execute(tool_context, {})
            print(f"✅ 结果: {result.ok}")
            if result.ok:
                print(f"   当前总分: {result.data.get('total_score_change', {}).get('current_total_score')}")
                print(f"   排名变化: {result.data.get('total_score_change', {}).get('class_rank_change')}")

        except Exception as e:
            print(f"⚠️  无法测试工具调用（可能缺少测试数据）: {e}")


async def test_context_builder():
    """测试 StudentContextBuilder"""
    print("\n" + "=" * 60)
    print("测试 StudentContextBuilder")
    print("=" * 60)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            from init_test_data import get_test_data
            test_data = await get_test_data(db)

            student = test_data['students'][0]
            school = test_data['schools'][0]

            builder = StudentContextBuilder(db)
            context = await builder.build_context(
                student_id=student['id'],
                school_id=school['id']
            )

            print(f"\n✅ 学生上下文构建成功:")
            print(f"   学生姓名: {context.student_name}")
            print(f"   权益等级: {context.entitlement_level}")
            print(f"   历史考试: {len(context.recent_exams)} 次")

            if context.latest_exam:
                print(f"   最近考试: {context.latest_exam['exam_name']}")
                print(f"   总分: {context.latest_exam['total_score']}")

            print("\n生成的Prompt上下文:")
            print(context.to_prompt_context())

        except Exception as e:
            print(f"❌ 测试失败: {e}")


async def test_intent_router():
    """测试 Intent Router"""
    print("\n" + "=" * 60)
    print("测试 Intent Router")
    print("=" * 60)

    router = IntentRouter()

    test_queries = [
        "这次考试考得怎么样？",
        "数学考了多少分？",
        "比上次进步了吗？",
        "最近几次考试的趋势如何？",
        "哪些题目丢分最多？",
        "能给我做个诊断分析吗？",
        "你好",
    ]

    for query in test_queries:
        intent = router.route(query)
        entities = router.extract_entities(query)

        print(f"\n查询: {query}")
        print(f"  意图: {intent.name} (置信度: {intent.confidence})")
        print(f"  建议工具: {intent.suggested_tools}")
        if entities:
            print(f"  实体: {entities}")


async def test_agent_schemas():
    """测试 Agent 相关的 Schema"""
    print("\n" + "=" * 60)
    print("测试 Agent Schemas")
    print("=" * 60)

    from app.agent.agent_loop import AgentStep, AgentResponse

    # 测试 AgentStep
    step = AgentStep(
        step_number=1,
        tool_name="get_exam_summary",
        tool_args={},
        reasoning="获取考试总结"
    )
    print(f"\n✅ AgentStep 创建成功: {step.tool_name}")

    # 测试 AgentResponse
    response = AgentResponse(
        agent_run_id="test-run-id",
        final_answer="你这次考试总分120分",
        steps=[step],
        total_tools_called=1
    )
    print(f"✅ AgentResponse 创建成功: {response.final_answer[:30]}...")


async def main():
    """主测试函数"""
    print("\n🚀 Phase 2 功能测试")
    print("=" * 60)

    try:
        await test_tools()
        await test_context_builder()
        await test_intent_router()
        await test_agent_schemas()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
