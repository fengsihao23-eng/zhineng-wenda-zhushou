"""
PromptRegistry单元测试
"""
import pytest
from app.core.prompt_registry import PromptRegistry
from app.schemas.prompt import PromptTemplateCreate


@pytest.mark.asyncio
async def test_create_prompt(test_db):
    """测试创建Prompt"""
    registry = PromptRegistry(test_db)

    data = PromptTemplateCreate(
        name="test_prompt",
        scene="test",
        content="Hello {{ name }}!",
        variables=["name"],
        description="测试Prompt"
    )

    prompt = await registry.create(data)

    assert prompt.name == "test_prompt"
    assert prompt.version == "v1"
    assert prompt.status == "draft"
    assert "name" in prompt.variables


@pytest.mark.asyncio
async def test_render_prompt(test_db):
    """测试渲染Prompt"""
    registry = PromptRegistry(test_db)

    data = PromptTemplateCreate(
        name="greeting",
        scene="test",
        content="你好，{{ student_name }}！你的分数是{{ score }}分。",
        variables=["student_name", "score"]
    )

    prompt = await registry.create(data)
    await registry.publish(prompt.name, prompt.version)

    # 渲染
    rendered = await registry.render(
        name="greeting",
        student_name="张三",
        score=95
    )

    assert "张三" in rendered
    assert "95分" in rendered


@pytest.mark.asyncio
async def test_prompt_versioning(test_db):
    """测试版本管理"""
    registry = PromptRegistry(test_db)

    # 创建v1
    data_v1 = PromptTemplateCreate(
        name="version_test",
        scene="test",
        content="v1 content",
        variables=[]
    )
    v1 = await registry.create(data_v1)
    assert v1.version == "v1"

    # 创建v2
    data_v2 = PromptTemplateCreate(
        name="version_test",
        scene="test",
        content="v2 content",
        variables=[]
    )
    v2 = await registry.create(data_v2)
    assert v2.version == "v2"

    # 获取指定版本
    fetched_v1 = await registry.get("version_test", "v1")
    assert fetched_v1.content == "v1 content"

    fetched_v2 = await registry.get("version_test", "v2")
    assert fetched_v2.content == "v2 content"


@pytest.mark.asyncio
async def test_publish_prompt(test_db):
    """测试发布Prompt"""
    registry = PromptRegistry(test_db)

    data = PromptTemplateCreate(
        name="publish_test",
        scene="test",
        content="test content",
        variables=[]
    )

    prompt = await registry.create(data)
    assert prompt.status == "draft"

    # 发布
    await registry.publish(prompt.name, prompt.version)

    # 验证状态
    published = await registry.get(prompt.name, prompt.version)
    assert published.status == "published"


@pytest.mark.asyncio
async def test_get_latest_published(test_db):
    """测试获取最新published版本"""
    registry = PromptRegistry(test_db)

    # 创建多个版本
    for i in range(3):
        data = PromptTemplateCreate(
            name="latest_test",
            scene="test",
            content=f"v{i+1} content",
            variables=[]
        )
        prompt = await registry.create(data)
        if i < 2:  # 只发布前两个版本
            await registry.publish(prompt.name, prompt.version)

    # 获取最新published版本（应该是v2）
    latest = await registry.get("latest_test")
    assert latest.version == "v2"
    assert latest.content == "v2 content"


@pytest.mark.asyncio
async def test_missing_variables(test_db):
    """测试缺少必需变量"""
    registry = PromptRegistry(test_db)

    data = PromptTemplateCreate(
        name="missing_var_test",
        scene="test",
        content="Hello {{ name }} and {{ age }}!",
        variables=["name", "age"]
    )

    prompt = await registry.create(data)
    await registry.publish(prompt.name, prompt.version)

    # 缺少age变量
    with pytest.raises(ValueError, match="Missing required variables"):
        await registry.render(
            name="missing_var_test",
            person="张三"
        )


@pytest.mark.asyncio
async def test_bootstrap_never_republishes_retired_prompt(test_db):
    from app.core.default_prompts import ensure_default_prompts
    from app.db.models.prompt import PromptTemplate
    from sqlalchemy import select
    assert await ensure_default_prompts(test_db) == 1
    item = await test_db.scalar(select(PromptTemplate).where(PromptTemplate.name == "student_qa_system"))
    item.status = "deprecated"
    await test_db.commit()
    assert await ensure_default_prompts(test_db) == 0
    await test_db.refresh(item)
    assert item.status == "deprecated"
