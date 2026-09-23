"""
学生模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, Index
from app.db.types import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class Student(Base):
    """学生表"""
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, comment="关联用户ID")
    external_student_id = Column(String(100), comment="外部系统学生ID")
    student_no = Column(String(50), comment="学号")
    name = Column(String(100), nullable=False, comment="姓名")
    profile_fields = Column(JSONB, nullable=False, default=dict, server_default="{}")
    grade_id = Column(UUID(as_uuid=True), comment="年级ID")
    class_id = Column(UUID(as_uuid=True), comment="班级ID")
    external_class_id = Column(String(100), comment="外部系统班级ID")
    status = Column(String(20), nullable=False, default="active", comment="状态")
    source_system = Column(String(50), comment="数据来源系统")
    source_updated_at = Column(DateTime(timezone=True), comment="源系统更新时间")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_students_bound_user", "school_id", "user_id", unique=True, postgresql_where=user_id.is_not(None), sqlite_where=user_id.is_not(None)),
        UniqueConstraint("school_id", "external_student_id", name="uq_school_external_student"),
        UniqueConstraint("school_id", "id", name="uq_students_school_id_id"),
        ForeignKeyConstraint(
            ["school_id", "user_id"],
            ["users.school_id", "users.id"],
            name="fk_students_school_user",
        ),
    )
