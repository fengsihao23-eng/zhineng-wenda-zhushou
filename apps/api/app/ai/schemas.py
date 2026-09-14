"""
AI模型Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class Usage(BaseModel):
    """Token使用量"""
    prompt_tokens: int = Field(..., description="提示Token数")
    completion_tokens: int = Field(..., description="完成Token数")
    total_tokens: int = Field(..., description="总Token数")


class FunctionCall(BaseModel):
    """函数调用"""
    name: str = Field(..., description="函数名称")
    arguments: dict = Field(..., description="参数")


class ToolCall(BaseModel):
    """工具调用"""
    id: str = Field(..., description="调用ID")
    type: str = Field(default="function", description="类型")
    function: FunctionCall = Field(..., description="函数调用")


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色: system/user/assistant/tool")
    content: Optional[str] = Field(None, description="消息内容")
    tool_calls: Optional[List[dict]] = Field(None, description="工具调用")
    tool_call_id: Optional[str] = Field(None, description="工具调用ID")


class ModelResponse(BaseModel):
    """模型响应"""
    content: Optional[str] = Field(None, description="响应文本")
    text: Optional[str] = Field(None, description="响应文本（兼容）")
    tool_calls: Optional[List[ToolCall]] = Field(None, description="工具调用列表")
    usage: Usage = Field(..., description="Token使用量")
    provider: str = Field(..., description="Provider名称")
    model: str = Field(..., description="模型名称")
    latency_ms: int = Field(..., description="延迟(毫秒)")
    finish_reason: str = Field(..., description="结束原因")
    raw_response_ref: Optional[str] = Field(None, description="原始响应引用")

    @property
    def has_tool_calls(self) -> bool:
        """是否有工具调用"""
        return bool(self.tool_calls and len(self.tool_calls) > 0)


class ModelChunk(BaseModel):
    """流式响应块"""
    text: str = Field(..., description="文本块")
    finish_reason: Optional[str] = Field(None, description="结束原因")
