"""
聊天会话模型
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class ChatSession(Base):
    """聊天会话表"""
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    title = Column(String(200), comment="会话标题")
    status = Column(String(20), nullable=False, default="active", comment="状态")
    selected_exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), comment="当前选中考试")
    selected_subject_id = Column(UUID(as_uuid=True), nullable=True)
    context_version = Column(Integer, nullable=False, default=1, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_message_at = Column(DateTime(timezone=True), comment="最后消息时间")

    __table_args__ = (
        ForeignKeyConstraint(["school_id", "selected_exam_id"], ["exams.school_id", "exams.id"], name="fk_chat_selected_exam"),
        ForeignKeyConstraint(["school_id", "selected_subject_id"], ["subjects.school_id", "subjects.id"], name="fk_chat_selected_subject"),
        UniqueConstraint("school_id", "id", name="uq_chat_sessions_school_id_id"),
        UniqueConstraint("school_id", "student_id", "id", name="uq_chat_sessions_school_student_id"),
        ForeignKeyConstraint(
            ["school_id", "student_id"],
            ["students.school_id", "students.id"],
            name="fk_chat_sessions_school_student",
        ),
    )


class ChatMessage(Base):
    """聊天消息表"""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False, comment="角色: user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    model_id = Column(String(100), comment="模型ID")
    agent_run_id = Column(UUID(as_uuid=True), comment="Agent运行ID")
    token_input = Column(Integer, comment="输入Token数")
    token_output = Column(Integer, comment="输出Token数")
    sources = Column(JSONB, nullable=False, default=list, server_default="[]")
    selected_context = Column(JSONB, nullable=False, default=dict, server_default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
