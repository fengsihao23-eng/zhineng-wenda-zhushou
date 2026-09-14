"""
Prompt Registry Schemas
"""
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from uuid import UUID
from jinja2 import Template, TemplateError


class PromptTemplateBase(BaseModel):
    """Prompt模板基础Schema"""
    name: str = Field(..., max_length=100, description="Prompt名称")
    scene: str = Field(..., max_length=50, description="使用场景")
    content: str = Field(..., description="Prompt内容")
    variables: list[str] = Field(default_factory=list, description="可替换变量列表")
    description: str | None = Field(None, description="描述")


class PromptTemplateCreate(PromptTemplateBase):
    """创建Prompt模板"""
    pass


class PromptTemplateUpdate(BaseModel):
    """更新Prompt模板"""
    content: str | None = None
    description: str | None = None
    status: str | None = None


class PromptTemplateOut(PromptTemplateBase):
    """Prompt模板输出"""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: str
    status: str
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    def render(self, **kwargs) -> str:
        """
        渲染 Prompt

        Args:
            **kwargs: 变量值

        Returns:
            渲染后的内容

        Raises:
            ValueError: 缺少必需变量或渲染失败
        """
        # 检查必需变量
        missing = set(self.variables) - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")

        # 使用 Jinja2 渲染
        try:
            template = Template(self.content)
            return template.render(**kwargs)
        except TemplateError as e:
            raise ValueError(f"Failed to render prompt: {e}")


class PromptRenderRequest(BaseModel):
    """Prompt渲染请求"""
    name: str = Field(..., description="Prompt名称")
    version: str | None = Field(None, description="版本号，不指定则使用最新published版本")
    variables: dict = Field(default_factory=dict, description="变量值")


class PromptRenderResponse(BaseModel):
    """Prompt渲染响应"""
    content: str = Field(..., description="渲染后的内容")
    version: str = Field(..., description="使用的版本")
