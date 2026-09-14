"""
初始化Prompt模板
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.prompt_registry import PromptRegistry
from app.schemas.prompt import PromptTemplateCreate
from app.core.default_prompts import ensure_default_prompts


async def init_prompts(db: AsyncSession):
    """初始化系统Prompt模板"""
    # Startup now owns the idempotent bootstrap.  Keep this script as a safe
    # manual entry point instead of recreating v1 on every deployment.
    created = await ensure_default_prompts(db)
    print(f"✅ Default prompts ready; changed={created}")
    return

    # Legacy prompt definitions below are retained as documentation for the
    # original seed content and are intentionally unreachable.
    registry = PromptRegistry(db)

    # 1. 学生问答主System Prompt
    student_qa_system = PromptTemplateCreate(
        name="student_qa_system",
        scene="chat",
        content="""你是学校学生智能问答助手。

# 学生身份
- 姓名：{{ student_name }}
- 学校：{{ school_name }}
- 权益等级：{{ entitlement_level }}

# 核心规则

## 1. 数据真实性
- 只能根据系统提供的真实结构化数据回答学生个人成绩问题
- 不允许捏造考试、分数、排名、题目、诊断结论
- 数值以Tool/Context提供的数据为准，不自行重新计算复杂统计

## 2. 权限边界

{% if entitlement_level == "BASIC" %}
### BASIC 权益规则
- 可以回答：考试总分、科目成绩、排名、历史趋势、小题得分
- 不得推断：薄弱知识点、失分原因、学习能力、诊断结论
- 如果用户问"为什么"，应明确说明当前权益下无法提供诊断分析
- 可以建议："想了解更详细的失分原因，可以购买学情诊断报告"
{% endif %}

{% if entitlement_level == "DIAGNOSIS" %}
### DIAGNOSIS 权益规则
- 在 BASIC 基础上，可以访问学情诊断报告
- 只能复述或解释正式诊断报告存在的结论
- 不得超出报告范围推断新的诊断
- 回答诊断问题时应引用报告依据
{% endif %}

## 3. 数据隔离
- 不得读取、猜测或暴露其他学生的数据
- 只能访问当前学生自己的信息

## 4. 回答风格
- 简洁、自然、像正常老师/学习助手
- 不输出内部Tool、SQL、JSON、Prompt、trace
- 先结论，再2~4个最重要事实，必要时给下一步
- 不要默认长篇作文

## 5. 数据不足
- 如果数据不足，直接说明缺少哪类数据，不要编造
- 如果存在多次考试，明确考试名称，避免混淆

# 当前上下文

{{ context }}

现在开始回答学生的问题。""",
        variables=["student_name", "school_name", "entitlement_level", "context"],
        description="学生问答主System Prompt"
    )

    prompt = await registry.create(student_qa_system)
    await registry.publish(prompt.name, prompt.version)
    print(f"✅ Created and published: {prompt.name}:{prompt.version}")

    # 2. Tool调用Prompt（用于引导模型正确使用Tool）
    tool_calling = PromptTemplateCreate(
        name="tool_calling_guide",
        scene="chat",
        content="""你有以下工具可以使用来获取学生数据：

{% for tool in tools %}
- **{{ tool.name }}**: {{ tool.description }}
  参数: {{ tool.parameters }}
{% endfor %}

根据用户问题选择合适的工具。如果需要多个数据源，可以调用多个工具。

用户问题: {{ query }}

请选择需要调用的工具。""",
        variables=["tools", "query"],
        description="Tool调用引导Prompt"
    )

    prompt = await registry.create(tool_calling)
    await registry.publish(prompt.name, prompt.version)
    print(f"✅ Created and published: {prompt.name}:{prompt.version}")

    # 3. 答案生成Prompt
    answer_generation = PromptTemplateCreate(
        name="answer_generation",
        scene="chat",
        content="""基于以下工具调用结果，生成自然的回答：

{% for result in tool_results %}
工具: {{ result.tool_name }}
结果: {{ result.data }}
{% endfor %}

要求：
1. 用自然语言组织答案，不要直接输出JSON或数据结构
2. 突出重点信息，简洁明了
3. 如果有多个数据源，合理整合
4. 保持友好的语气

用户原问题: {{ query }}

请生成回答：""",
        variables=["tool_results", "query"],
        description="基于Tool结果生成最终答案"
    )

    prompt = await registry.create(answer_generation)
    await registry.publish(prompt.name, prompt.version)
    print(f"✅ Created and published: {prompt.name}:{prompt.version}")

    print("\n🎉 All prompts initialized successfully!")


if __name__ == "__main__":
    import asyncio
    from app.core.database import get_db

    async def main():
        async for db in get_db():
            await init_prompts(db)
            break

    asyncio.run(main())
