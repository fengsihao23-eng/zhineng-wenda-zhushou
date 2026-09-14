"""
Agent追踪模型
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, ForeignKeyConstraint, DECIMAL, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.db.base import Base


class AgentRun(Base):
    """Agent运行记录表"""
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), index=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    query = Column(Text, nullable=False, comment="用户查询")
    intent = Column(String(50), comment="意图分类")
    entitlement_level = Column(String(20), nullable=False, comment="权益等级")
    status = Column(String(20), nullable=False, comment="状态")
    model_profile_id = Column(String(100), comment="模型配置ID")
    prompt_version = Column(String(50), comment="Prompt版本")
    tool_call_count = Column(Integer, default=0, comment="工具调用次数")
    latency_ms = Column(Integer, comment="延迟(毫秒)")
    input_tokens = Column(Integer, comment="输入Token数")
    output_tokens = Column(Integer, comment="输出Token数")
    estimated_cost = Column(DECIMAL(10, 6), comment="估算成本")
    error_code = Column(String(50), comment="错误代码")
    guard_action = Column(String(20), comment="响应安全处置动作")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), comment="完成时间")

    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_agent_runs_school_id_id"),
        ForeignKeyConstraint(
            ["school_id", "student_id"],
            ["students.school_id", "students.id"],
            name="fk_agent_runs_school_student",
        ),
        ForeignKeyConstraint(
            ["school_id", "session_id"],
            ["chat_sessions.school_id", "chat_sessions.id"],
            name="fk_agent_runs_school_session",
        ),
    )

    tool_calls = relationship(
        "ToolCallLog",
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="ToolCallLog.created_at",
    )
    model_usage = relationship(
        "ModelUsageLog",
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="ModelUsageLog.created_at",
    )


class ToolCallLog(Base):
    """工具调用日志表"""
    __tablename__ = "tool_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, comment="工具名称")
    input_json = Column(JSONB, nullable=False, comment="输入参数")
    output_summary_json = Column(JSONB, comment="输出摘要")
    status = Column(String(20), nullable=False, comment="状态")
    latency_ms = Column(Integer, comment="延迟(毫秒)")
    error_code = Column(String(50), comment="错误代码")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    agent_run = relationship("AgentRun", back_populates="tool_calls")


class ModelUsageLog(Base):
    """模型使用日志表"""
    __tablename__ = "model_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, comment="Provider名称")
    model = Column(String(100), nullable=False, comment="模型名称")
    prompt_tokens = Column(Integer, nullable=False, comment="Prompt Token数")
    completion_tokens = Column(Integer, nullable=False, comment="Completion Token数")
    total_tokens = Column(Integer, nullable=False, comment="总Token数")
    estimated_cost = Column(DECIMAL(10, 6), comment="估算成本")
    latency_ms = Column(Integer, comment="延迟(毫秒)")
    agent_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Agent运行ID",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    agent_run = relationship("AgentRun", back_populates="model_usage")
