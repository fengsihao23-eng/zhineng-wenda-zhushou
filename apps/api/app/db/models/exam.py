"""
考试模型
"""
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, UniqueConstraint, DECIMAL
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Exam(Base):
    """考试表"""
    __tablename__ = "exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    external_exam_id = Column(String(100), comment="外部考试ID")
    name = Column(String(200), nullable=False, comment="考试名称")
    exam_type = Column(String(50), nullable=False, comment="考试类型")
    academic_year = Column(String(20), comment="学年")
    term = Column(String(20), comment="学期")
    grade_id = Column(UUID(as_uuid=True), index=True, comment="年级ID")
    start_date = Column(Date, comment="开始日期")
    end_date = Column(Date, comment="结束日期")
    status = Column(String(20), nullable=False, default="active", comment="状态")
    source_system = Column(String(50), comment="来源系统")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "external_exam_id", name="uq_school_external_exam"),
        UniqueConstraint("school_id", "id", name="uq_exams_school_id_id"),
    )


class Subject(Base):
    """科目表"""
    __tablename__ = "subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False, comment="科目代码")
    name = Column(String(100), nullable=False, comment="科目名称")
    external_subject_id = Column(String(100), comment="外部系统科目ID")
    source_system = Column(String(100), comment="来源系统")

    __table_args__ = (
        UniqueConstraint("school_id", "code", name="uq_school_subject_code"),
        UniqueConstraint("school_id", "id", name="uq_subjects_school_id_id"),
    )


class ExamSubject(Base):
    """考试科目表"""
    __tablename__ = "exam_subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    full_score = Column(DECIMAL(10, 2), nullable=False, comment="满分")
    grade_avg = Column(DECIMAL(10, 2), comment="年级平均分")
    class_avg = Column(DECIMAL(10, 2), comment="班级平均分")

    __table_args__ = (
        UniqueConstraint("exam_id", "subject_id", name="uq_exam_subject"),
    )
