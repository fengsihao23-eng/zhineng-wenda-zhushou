"""Current report identities, private PDF versions and immutable operation receipts."""
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, LargeBinary, Index, text
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID, JSONB


class ManagedReport(Base):
    __tablename__ = "managed_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    exam_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    report_code = Column(String(50), nullable=False, unique=True)
    category = Column(String(20), nullable=False)
    report_type = Column(String(30), nullable=False)
    subject_ids = Column(JSONB, nullable=False)
    target_key = Column(String(250), nullable=False)
    identity_hash = Column(String(64), nullable=False)
    # Labels and per-subject participant IDs come from the exam's saved roster.
    attribution = Column(JSONB, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="current")
    operator_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_managed_report_tenant"),
        ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_managed_report_exam"),
        Index("uq_managed_report_current", "school_id", "identity_hash", unique=True,
              postgresql_where=text("status = 'current'"), sqlite_where=text("status = 'current'")),
    )


class ReportFile(Base):
    __tablename__ = "report_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    report_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    filename = Column(String(500), nullable=False)
    content = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    reason = Column(String(1000), nullable=False, default="")
    operator_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("report_id", "version", name="uq_report_file_version"),
        ForeignKeyConstraint(["school_id", "report_id"], ["managed_reports.school_id", "managed_reports.id"], name="fk_report_file_tenant"),
    )


class ReportOperation(Base):
    __tablename__ = "report_operations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    operator_name = Column(String(100), nullable=False)
    reason = Column(String(1000), nullable=False, default="")
    details = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
