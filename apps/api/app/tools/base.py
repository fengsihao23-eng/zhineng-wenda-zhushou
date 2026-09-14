"""
Tool基类
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class ToolContext(BaseModel):
    """Tool执行上下文"""
    request_id: str = Field(..., description="请求ID")
    agent_run_id: str = Field(..., description="Agent运行ID")
    user_id: UUID = Field(..., description="用户ID")
    school_id: UUID = Field(..., description="学校ID")
    student_id: UUID = Field(..., description="学生ID")
    entitlement_level: str = Field(..., description="权益等级")


class EvidenceRef(BaseModel):
    """数据来源证据"""
    type: str = Field(..., description="证据类型")
    resource_id: str = Field(..., description="资源ID")
    label: str = Field(..., description="用户可读标签")
    as_of: Optional[datetime] = Field(None, description="数据时间戳")


class ToolResult(BaseModel):
    """Tool执行结果"""
    ok: bool = Field(..., description="是否成功")
    data: dict = Field(..., description="返回数据")
    evidence: list[EvidenceRef] = Field(default_factory=list, description="证据链")
    error_code: Optional[str] = Field(None, description="错误代码")
    error_message: Optional[str] = Field(None, description="错误消息")


class BaseTool(ABC):
    """Tool基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool描述（给模型看）"""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """输入参数JSON Schema"""
        pass

    @property
    def required_entitlement(self) -> str | None:
        """所需权益等级"""
        return None

    @property
    def read_only(self) -> bool:
        """是否只读"""
        return True

    @property
    def timeout(self) -> int:
        """超时时间（秒）"""
        return 10

    @abstractmethod
    async def execute(
        self,
        tool_context: ToolContext,
        args: dict
    ) -> ToolResult:
        """执行Tool"""
        pass

    def validate_entitlement(self, tool_context: ToolContext):
        """验证权益"""
        if self.required_entitlement:
            if tool_context.entitlement_level != self.required_entitlement:
                from app.core.errors import EntitlementRequiredError
                raise EntitlementRequiredError(
                    product_code=self.required_entitlement
                )
