"""Excel roster intake for teacher/student maintenance (2026-09-22 flow)."""
import uuid
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, ForeignKeyConstraint, LargeBinary
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    fields = Column(JSONB, nullable=False, default=dict)
    duties = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "id"], ["users.school_id", "users.id"], name="fk_teacher_profile_user"),
    )


class TeacherChangeTask(Base):
    __tablename__ = "teacher_change_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    created_by = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    confirmation = Column(JSONB, nullable=False, default=dict)


class TeacherDeletion(Base):
    """Immutable template snapshot; the disabled user retains historical FK targets."""
    __tablename__ = "teacher_deletions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    platform_id = Column(BigInteger, nullable=False)
    teacher_name = Column(String(100), nullable=False)
    account = Column(String(100), nullable=False, index=True)
    fields = Column(JSONB, nullable=False)
    duties = Column(JSONB, nullable=False)
    deleted_by = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reimported_user_id = Column(UUID(as_uuid=True))
    reimported_at = Column(DateTime(timezone=True))
    reason = Column(String(30), nullable=False, default="legacy")
    reason_note = Column(String(500), nullable=False, default="")
    operation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    task_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    updated_fields = Column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_user"),
        ForeignKeyConstraint(["school_id", "user_id", "platform_id"], ["platform_person_ids.school_id", "platform_person_ids.entity_id", "platform_person_ids.id"], name="fk_teacher_snapshot_platform_identity"),
        ForeignKeyConstraint(["school_id", "reimported_user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_reimport"),
        ForeignKeyConstraint(["task_id"], ["teacher_change_tasks.id"], name="fk_teacher_deletion_task"),
    )


class RosterImport(Base):
    __tablename__ = "roster_imports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    filename = Column(String(200), nullable=False)
    content_hash = Column(String(64), nullable=False)
    rows = Column(JSONB, nullable=False, default=list)
    report = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="ready")
    revision = Column(Integer, nullable=False, default=1)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    confirmation = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    original_content = Column(LargeBinary)
    change_task_id = Column(UUID(as_uuid=True), ForeignKey("teacher_change_tasks.id"), index=True)
