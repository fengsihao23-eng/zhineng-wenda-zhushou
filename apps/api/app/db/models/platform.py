"""Platform workflow models: knowledge governance, safeguarding and operations."""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import JSONB, UUID


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    title = Column(String(240), nullable=False)
    subject = Column(String(80), nullable=False, default="通用")
    doc_type = Column(String(40), nullable=False, default="教学资料")
    content = Column(Text, nullable=False)
    source_name = Column(String(200), nullable=False)
    source_url = Column(String(1000))
    source_reference = Column(String(500), nullable=False)
    version = Column(String(30), nullable=False, default="v1")
    status = Column(String(30), nullable=False, default="draft", index=True)
    tags = Column(JSONB)
    rejection_reason = Column(String(500))
    created_by = Column(UUID(as_uuid=True), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))
    offlined_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ParentAuthorization(Base):
    __tablename__ = "parent_authorizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    parent_name = Column(String(100), nullable=False)
    parent_phone = Column(String(40), nullable=False)
    share_code = Column(String(20), nullable=False, unique=True, index=True)
    scopes = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    expires_at = Column(DateTime(timezone=True))
    granted_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PlatformFeedback(Base):
    __tablename__ = "platform_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), index=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("chat_messages.id"), index=True)
    rating = Column(String(30), nullable=False)
    category = Column(String(50), nullable=False, default="回答质量")
    note = Column(String(1000))
    status = Column(String(20), nullable=False, default="open", index=True)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolution = Column(String(1000))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), index=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="medium", index=True)
    title = Column(String(240), nullable=False)
    detail = Column(Text, nullable=False)
    source = Column(String(80), nullable=False, default="system")
    status = Column(String(20), nullable=False, default="open", index=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))


class HumanHandoff(Base):
    __tablename__ = "human_handoffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), index=True)
    reason = Column(String(500), nullable=False)
    priority = Column(String(20), nullable=False, default="normal", index=True)
    summary = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="open", index=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))

