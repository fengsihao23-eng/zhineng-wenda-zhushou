"""
诊断报告和权益模型
"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from app.db.types import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class DiagnosisReport(Base):
    """诊断报告表"""
    __tablename__ = "diagnosis_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"))
    report_type = Column(String(50), nullable=False, comment="报告类型")
    status = Column(String(20), nullable=False, default="generated", comment="状态")
    source_system = Column(String(50), comment="来源系统")
    raw_content = Column(Text, comment="原始报告内容")
    structured_json = Column(JSONB, nullable=False, comment="结构化JSON内容")
    version = Column(String(20), comment="版本")
    generated_at = Column(DateTime(timezone=True), nullable=False, comment="生成时间")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_diagnosis_reports_tenant"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_diagnosis_reports_school_student"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_diagnosis_reports_school_exam"),
        ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_diagnosis_reports_school_subject"),
    )


class StudentEntitlement(Base):
    """学生权益表"""
    __tablename__ = "student_entitlements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    product_code = Column(String(50), nullable=False, comment="产品代码")
    resource_type = Column(String(50), comment="资源类型")
    resource_id = Column(UUID(as_uuid=True), comment="资源ID")
    status = Column(String(20), nullable=False, default="active", comment="状态")
    starts_at = Column(DateTime(timezone=True), nullable=False, comment="开始时间")
    expires_at = Column(DateTime(timezone=True), comment="过期时间")
    source_order_id = Column(String(100), comment="来源订单ID")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "product_code", "resource_id", name="uq_student_product_resource"),
        ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_student_entitlements_school_student"),
    )
