"""Student r79 workflows and immutable historical class attribution."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, LargeBinary
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


class StudentYearClass(Base):
    __tablename__ = "student_year_classes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False)
    grade = Column(String(5000), nullable=False, default="")
    class_number = Column(String(5000), nullable=False, default="")
    class_id = Column(UUID(as_uuid=True))
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "student_id", "academic_year", name="uq_student_year_class"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_student_year_student"),
    )


class StudentExamPlacement(Base):
    __tablename__ = "student_exam_placements"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False)
    grade = Column(String(5000), nullable=False, default="")
    class_number = Column(String(5000), nullable=False, default="")
    class_id = Column(UUID(as_uuid=True))
    external_class_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "student_id", "exam_id", name="uq_student_exam_placement"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_placement_student"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_placement_exam"),
    )


class StudentWorkflowTask(Base):
    __tablename__ = "student_workflow_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="ready", index=True)
    revision = Column(Integer, nullable=False, default=1)
    filename = Column(String(200))
    original_content = Column(LargeBinary)
    request_payload = Column(JSONB, nullable=False, default=dict)
    rows = Column(JSONB, nullable=False, default=list)
    snapshots = Column(JSONB, nullable=False, default=list)
    report = Column(JSONB, nullable=False, default=dict)
    preparation = Column(JSONB, nullable=False, default=dict)
    reviews = Column(JSONB, nullable=False, default=dict)
    confirmation = Column(JSONB, nullable=False, default=dict)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
