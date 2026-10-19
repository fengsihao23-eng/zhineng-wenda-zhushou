"""School scoped r92 prompt, trial, conversation and asynchronous message records."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint, ForeignKeyConstraint
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


class AnswerScope(Base):
    __tablename__ = "answer_scopes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    scope = Column(String(40), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    body = Column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("school_id", "scope", name="uq_answer_scope"),)


class AnswerTrial(Base):
    __tablename__ = "answer_trials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    scope = Column(String(40), nullable=False)
    body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_answer_trial_user"),)


class AnswerSession(Base):
    __tablename__ = "answer_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_answer_session_user"),)


class AnswerTicket(Base):
    __tablename__ = "answer_tickets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_answer_ticket_user"),)


class AnswerOperation(Base):
    __tablename__ = "answer_operations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(100), nullable=False)
    body = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_answer_operation_user"),)
