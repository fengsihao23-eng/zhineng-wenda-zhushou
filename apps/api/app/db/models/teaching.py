"""Explicit class/subject grants. Missing or expired assignments deny access."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import UUID


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    teacher_user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    starts_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("school_id", "teacher_user_id", "class_id", "subject_id", name="uq_teaching_assignment"),
        ForeignKeyConstraint(["school_id", "teacher_user_id"], ["users.school_id", "users.id"], name="fk_teaching_user"),
        ForeignKeyConstraint(["school_id", "class_id"], ["import_classes.school_id", "import_classes.id"], name="fk_teaching_class"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_teaching_subject"),
    )
