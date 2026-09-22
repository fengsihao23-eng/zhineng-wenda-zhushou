"""
Admin API - Prompt管理
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_admin, require_global_prompt_publisher
from app.core.prompt_registry import PromptRegistry
from app.core.errors import NotFoundError, ApiError
from app.schemas.prompt import (
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptRenderRequest,
    PromptRenderResponse
)

router = APIRouter(
    prefix="/prompts",
    tags=["prompts"],
    dependencies=[Depends(require_admin)],
)


@router.post("/", response_model=PromptTemplateOut, dependencies=[Depends(require_global_prompt_publisher)])
async def create_prompt(
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建Prompt模板"""
    registry = PromptRegistry(db)
    prompt = await registry.create(data)
    return prompt


@router.get("/{name}/{version}", response_model=PromptTemplateOut)
async def get_prompt(
    name: str,
    version: str,
    db: AsyncSession = Depends(get_db)
):
    """获取Prompt模板"""
    registry = PromptRegistry(db)
    try:
        prompt = await registry.get(name, version)
        return prompt
    except NotFoundError:
        raise


@router.get("/", response_model=list[PromptTemplateOut])
async def list_prompts(
    scene: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """列出Prompt模板"""
    registry = PromptRegistry(db)
    prompts = await registry.list_prompts(scene, status, limit, offset)
    return prompts


@router.post("/{name}/{version}/publish", dependencies=[Depends(require_global_prompt_publisher)])
async def publish_prompt(
    name: str,
    version: str,
    db: AsyncSession = Depends(get_db)
):
    """发布Prompt版本"""
    registry = PromptRegistry(db)
    await registry.publish(name, version)
    return {"status": "published", "name": name, "version": version}


@router.post("/{name}/{version}/deprecate", dependencies=[Depends(require_global_prompt_publisher)])
async def deprecate_prompt(
    name: str,
    version: str,
    db: AsyncSession = Depends(get_db)
):
    """废弃Prompt版本"""
    registry = PromptRegistry(db)
    await registry.deprecate(name, version)
    return {"status": "deprecated", "name": name, "version": version}


@router.post("/render", response_model=PromptRenderResponse)
async def render_prompt(
    request: PromptRenderRequest,
    db: AsyncSession = Depends(get_db)
):
    """渲染Prompt"""
    registry = PromptRegistry(db)
    try:
        content = await registry.render(
            name=request.name,
            version=request.version,
            **request.variables
        )

        # 获取使用的版本
        prompt = await registry.get(request.name, request.version)

        return PromptRenderResponse(
            content=content,
            version=prompt.version
        )
    except NotFoundError:
        raise
    except ValueError:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "PROMPT_RENDER_FAILED", "Prompt 渲染失败")
