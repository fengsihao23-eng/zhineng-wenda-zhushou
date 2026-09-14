"""
成绩模型
"""
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, ForeignKeyConstraint, UniqueConstraint, DECIMAL
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class StudentExamScore(Base):
    """学生考试总分表"""
    __tablename__ = "student_exam_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    total_score = Column(DECIMAL(10, 2), nullable=False, comment="总分")
    full_score = Column(DECIMAL(10, 2), comment="满分")
    class_rank = Column(Integer, comment="班级排名")
    grade_rank = Column(Integer, comment="年级排名")
    class_student_count = Column(Integer, comment="班级学生总数")
    grade_student_count = Column(Integer, comment="年级学生总数")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", name="uq_student_exam"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_student_exam_scores_school_student"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_student_exam_scores_school_exam"),
    )


class StudentSubjectScore(Base):
    """学生科目成绩表"""
    __tablename__ = "student_subject_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    score = Column(DECIMAL(10, 2), nullable=False, comment="得分")
    full_score = Column(DECIMAL(10, 2), nullable=False, comment="满分")
    class_rank = Column(Integer, comment="班级排名")
    grade_rank = Column(Integer, comment="年级排名")
    class_avg = Column(DECIMAL(10, 2), comment="班级平均分")
    grade_avg = Column(DECIMAL(10, 2), comment="年级平均分")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", "subject_id", name="uq_student_exam_subject"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_student_subject_scores_school_student"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_student_subject_scores_school_exam"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_student_subject_scores_school_subject"),
    )


class QuestionScore(Base):
    """小题得分表"""
    __tablename__ = "question_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    question_id = Column(UUID(as_uuid=True), comment="题目ID")
    question_no = Column(String(20), nullable=False, comment="题号")
    score = Column(DECIMAL(10, 2), nullable=False, comment="得分")
    full_score = Column(DECIMAL(10, 2), nullable=False, comment="满分")
    lost_score = Column(DECIMAL(10, 2), nullable=False, comment="丢分")
    answer_status = Column(String(20), comment="答题状态")
    knowledge_point_id = Column(UUID(as_uuid=True), comment="知识点ID")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", "subject_id", "question_no", name="uq_student_exam_subject_question"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_question_scores_school_student"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_question_scores_school_exam"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_question_scores_school_subject"),
    )
