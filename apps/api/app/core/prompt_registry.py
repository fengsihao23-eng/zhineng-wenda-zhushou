"""
Prompt Registry - Prompt版本管理
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from typing import Optional
from uuid import UUID
import redis.asyncio as redis
import re

from app.db.models.prompt import PromptTemplate as PromptTemplateModel
from app.schemas.prompt import PromptTemplateOut, PromptTemplateCreate
from app.core.errors import NotFoundError


class PromptRegistry:
    """Prompt注册表"""

    def __init__(self, db: AsyncSession, cache: Optional[redis.Redis] = None):
        self.db = db
        self.cache = cache
        self._cache_ttl = 300  # 5分钟

    @staticmethod
    def _version_key(version: str) -> tuple[int, ...]:
        """Sort semantic ``v1``, ``v1.2`` style versions numerically."""
        numbers = re.findall(r"\d+", version or "")
        return tuple(int(item) for item in numbers) or (0,)

    async def get(
        self,
        name: str,
        version: Optional[str] = None
    ) -> PromptTemplateOut:
        """
        获取Prompt模板

        Args:
            name: Prompt名称
            version: 版本号，不指定则返回最新published版本

        Returns:
            PromptTemplateOut

        Raises:
            NotFoundError: Prompt不存在
        """
        # 尝试从缓存读取
        cache_key = f"prompt:{name}:{version or 'latest'}"
        if self.cache:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    return PromptTemplateOut.model_validate_json(cached)
            except Exception:
                pass  # 缓存失败不影响主流程

        # 从数据库查询
        query = select(PromptTemplateModel).where(
            PromptTemplateModel.name == name
        )

        if version:
            query = query.where(PromptTemplateModel.version == version)
        else:
            # Fetch all published versions and choose in Python.  SQLite has
            # second-level CURRENT_TIMESTAMP precision, so ordering only by
            # created_at can return an older version when writes share a tick.
            query = query.where(PromptTemplateModel.status == 'published')

        result = await self.db.execute(query)
        if version:
            model = result.scalar_one_or_none()
        else:
            models = result.scalars().all()
            model = max(
                models,
                key=lambda item: (
                    item.created_at,
                    self._version_key(item.version),
                ),
                default=None,
            )

        if not model:
            raise NotFoundError(f"Prompt {name}:{version or 'latest'} not found")

        prompt = PromptTemplateOut.model_validate(model)

        # 写入缓存
        if self.cache:
            try:
                await self.cache.setex(
                    cache_key,
                    self._cache_ttl,
                    prompt.model_dump_json()
                )
            except Exception:
                pass  # 缓存失败不影响主流程

        return prompt

    async def render(
        self,
        name: str,
        version: Optional[str] = None,
        **variables
    ) -> str:
        """
        获取并渲染Prompt

        Args:
            name: Prompt名称
            version: 版本号
            **variables: 变量值

        Returns:
            渲染后的内容
        """
        prompt = await self.get(name, version)
        return prompt.render(**variables)

    async def create(
        self,
        data: PromptTemplateCreate,
        created_by: Optional[UUID] = None
    ) -> PromptTemplateOut:
        """
        创建新版本Prompt

        Args:
            data: Prompt数据
            created_by: 创建者ID

        Returns:
            PromptTemplateOut
        """
        # 查询当前最大版本号.  SQL ``max`` on strings makes v10 sort before
        # v9, so parse version components in Python.
        result = await self.db.execute(
            select(PromptTemplateModel.version).where(
                PromptTemplateModel.name == data.name
            )
        )
        versions = [item for item in result.scalars().all() if item]
        max_version = max(versions, key=self._version_key, default=None)

        # 计算新版本号
        if max_version:
            # v1 -> v2, v1.1 -> v1.2
            parts = max_version.lstrip('v').split('.')
            if len(parts) == 1:
                new_version = f"v{int(parts[0]) + 1}"
            else:
                parts[-1] = str(int(parts[-1]) + 1)
                new_version = f"v{'.'.join(parts)}"
        else:
            new_version = "v1"

        # 创建模型
        model = PromptTemplateModel(
            name=data.name,
            scene=data.scene,
            version=new_version,
            content=data.content,
            variables=data.variables,
            status='draft',
            description=data.description,
            created_by=created_by
        )

        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)

        return PromptTemplateOut.model_validate(model)

    async def publish(self, name: str, version: str):
        """
        发布版本

        Args:
            name: Prompt名称
            version: 版本号
        """
        result = await self.db.execute(
            update(PromptTemplateModel)
            .where(
                PromptTemplateModel.name == name,
                PromptTemplateModel.version == version
            )
            .values(status='published', updated_at=func.now())
        )
        if result.rowcount == 0:
            raise NotFoundError(f"Prompt {name}:{version} not found")
        await self.db.commit()

        # 清除缓存
        if self.cache:
            try:
                await self.cache.delete(f"prompt:{name}:{version}")
                await self.cache.delete(f"prompt:{name}:latest")
            except Exception:
                pass

    async def deprecate(self, name: str, version: str):
        """
        废弃版本

        Args:
            name: Prompt名称
            version: 版本号
        """
        result = await self.db.execute(
            update(PromptTemplateModel)
            .where(
                PromptTemplateModel.name == name,
                PromptTemplateModel.version == version
            )
            .values(status='deprecated', updated_at=func.now())
        )
        if result.rowcount == 0:
            raise NotFoundError(f"Prompt {name}:{version} not found")
        await self.db.commit()

        # 清除缓存
        if self.cache:
            try:
                await self.cache.delete(f"prompt:{name}:{version}")
            except Exception:
                pass

    async def list_prompts(
        self,
        scene: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[PromptTemplateOut]:
        """
        列出Prompt模板

        Args:
            scene: 场景过滤
            status: 状态过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            Prompt列表
        """
        query = select(PromptTemplateModel)

        if scene:
            query = query.where(PromptTemplateModel.scene == scene)
        if status:
            query = query.where(PromptTemplateModel.status == status)

        query = query.order_by(
            PromptTemplateModel.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        models = result.scalars().all()

        return [PromptTemplateOut.model_validate(m) for m in models]
