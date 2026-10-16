"""Exam configuration, frozen participation, explicit grants and import evidence."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, LargeBinary, Index, text
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


class ExamAdministration(Base):
    __tablename__ = "exam_administrations"
    id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), primary_key=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=1)
    configuration = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "id"], ["exams.school_id", "exams.id"], name="fk_exam_admin_tenant"),)


class ExamParticipant(Base):
    __tablename__ = "exam_participants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint("exam_id", "subject_id", "student_id", name="uq_exam_participant"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_exam_participant_exam"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_exam_participant_subject"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_exam_participant_student"),
    )


class ExamQueryPolicy(Base):
    __tablename__ = "exam_query_policies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    recipient_kind = Column(String(20), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    configuration = Column(JSONB, nullable=False)
    __table_args__ = (
        UniqueConstraint("exam_id", "recipient_kind", "recipient_id", name="uq_exam_query_policy"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_exam_policy_exam"),
    )


class ExamQueryGrant(Base):
    __tablename__ = "exam_query_grants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    exam_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_kind = Column(String(20), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    content_type = Column(String(60), nullable=False)
    __table_args__ = (
        UniqueConstraint("exam_id", "recipient_kind", "recipient_id", "student_id", "subject_id", "content_type", name="uq_exam_query_grant"),
        Index("ix_exam_grant_lookup", "school_id", "recipient_kind", "recipient_id", "exam_id"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_exam_grant_exam"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_exam_grant_student"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_exam_grant_subject"),
    )


class ExamScoreFile(Base):
    __tablename__ = "exam_score_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    filename = Column(String(200), nullable=False)
    original_content = Column(LargeBinary, nullable=False)
    status = Column(String(20), nullable=False, default="validated")
    revision = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    rows = Column(JSONB, nullable=False, default=list)
    errors = Column(JSONB, nullable=False, default=list)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("uq_exam_score_file_active", "school_id", "exam_id", "subject_id", unique=True,
              postgresql_where=text("status = 'imported'"), sqlite_where=text("status = 'imported'")),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_exam_score_file_exam"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_exam_score_file_subject"),
    )


class ExamOperation(Base):
    __tablename__ = "exam_operations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    details = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_exam_operation_exam"),)
