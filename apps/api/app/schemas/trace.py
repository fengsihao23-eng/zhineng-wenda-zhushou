"""
Trace & Audit Schemas
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class AgentRunBase(BaseModel):
    """Agent运行基础Schema"""
    query: str = Field(..., description="用户查询")
    intent: str | None = Field(None, description="识别的意图")
    entitlement_level: str = Field(..., description="权益等级")


class AgentRunCreate(AgentRunBase):
    """创建Agent运行"""
    session_id: UUID | None = None
    school_id: UUID
    student_id: UUID


class AgentRunUpdate(BaseModel):
    """更新Agent运行"""
    status: str | None = None
    model_profile_id: str | None = None
    prompt_version: str | None = None
    tool_call_count: int | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: Decimal | None = None
    error_code: str | None = None
    guard_action: str | None = None
    finished_at: datetime | None = None


class AgentRunOut(AgentRunBase):
    """Agent运行输出"""
    id: UUID
    session_id: UUID | None
    school_id: UUID
    student_id: UUID
    status: str
    model_profile_id: str | None
    prompt_version: str | None
    tool_call_count: int
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: Decimal | None
    error_code: str | None
    guard_action: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ToolCallLogBase(BaseModel):
    """Tool调用日志基础Schema"""
    tool_name: str = Field(..., description="Tool名称")
    input_json: dict = Field(..., description="输入参数")
    status: str = Field(..., description="状态")


class ToolCallLogCreate(ToolCallLogBase):
    """创建Tool调用日志"""
    agent_run_id: UUID
    output_summary_json: dict | None = None
    latency_ms: int | None = None
    error_code: str | None = None


class ToolCallLogOut(ToolCallLogBase):
    """Tool调用日志输出"""
    id: UUID
    agent_run_id: UUID
    output_summary_json: dict | None
    latency_ms: int | None
    error_code: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelUsageLogBase(BaseModel):
    """模型使用日志基础Schema"""
    provider: str = Field(..., description="提供商")
    model: str = Field(..., description="模型名称")
    prompt_tokens: int = Field(..., description="Prompt Token数")
    completion_tokens: int = Field(..., description="完成Token数")
    total_tokens: int = Field(..., description="总Token数")


class ModelUsageLogCreate(ModelUsageLogBase):
    """创建模型使用日志"""
    agent_run_id: UUID | None = None
    estimated_cost: Decimal | None = None
    latency_ms: int | None = None


class ModelUsageLogOut(ModelUsageLogBase):
    """模型使用日志输出"""
    id: UUID
    agent_run_id: UUID | None
    estimated_cost: Decimal | None
    latency_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogBase(BaseModel):
    """审计日志基础Schema"""
    action: str = Field(..., description="操作")
    actor_type: str = Field(..., description="执行者类型")
    actor_id: UUID = Field(..., description="执行者ID")
    allowed: bool = Field(..., description="是否允许")


class AuditLogCreate(AuditLogBase):
    """创建审计日志"""
    resource_type: str | None = None
    resource_id: UUID | None = None
    reason: str | None = None
    metadata: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


class AuditLogOut(AuditLogBase):
    """审计日志输出"""
    id: UUID
    resource_type: str | None
    resource_id: UUID | None
    reason: str | None
    # SQLAlchemy exposes the migrated ``metadata`` column as ``extra_data``
    # because ``metadata`` is reserved by Declarative.
    metadata: dict | None = Field(
        default=None,
        validation_alias=AliasChoices("extra_data", "metadata"),
        serialization_alias="metadata",
    )
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AgentRunDetail(AgentRunOut):
    """Agent运行详情"""
    tool_calls: list[ToolCallLogOut] = Field(default_factory=list)
    model_usage: list[ModelUsageLogOut] = Field(default_factory=list)
