"""Excel roster intake and registered parent links (2026-09-22 flow)."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint
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


class TeacherDeletion(Base):
    """Immutable template snapshot; the disabled user retains historical FK targets."""
    __tablename__ = "teacher_deletions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    teacher_name = Column(String(100), nullable=False)
    account = Column(String(100), nullable=False, index=True)
    fields = Column(JSONB, nullable=False)
    duties = Column(JSONB, nullable=False)
    deleted_by = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reimported_user_id = Column(UUID(as_uuid=True))
    reimported_at = Column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_user"),
        ForeignKeyConstraint(["school_id", "reimported_user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_reimport"),
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


class ParentBinding(Base):
    __tablename__ = "student_parent_bindings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    parent_user_id = Column(UUID(as_uuid=True), nullable=False)
    phone = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_parent_binding_student"),
        ForeignKeyConstraint(["school_id", "parent_user_id"], ["users.school_id", "users.id"], name="fk_parent_binding_parent"),
        UniqueConstraint("student_id", "parent_user_id", name="uq_student_parent_binding"),
    )
