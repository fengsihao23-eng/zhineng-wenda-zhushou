"""CSV data import batches, raw staging rows, and class mappings."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from app.db.types import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base import Base


class ImportBatch(Base):
    """One all-or-nothing source-system synchronisation attempt."""

    __tablename__ = "data_import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(String(100), nullable=False, unique=True, comment="外部批次ID")
    source_system = Column(String(100), nullable=False, comment="来源系统")
    root_path = Column(Text, comment="批次文件目录")
    content_hash = Column(String(64), nullable=False, comment="批次内容哈希")
    status = Column(String(20), nullable=False, default="received", comment="批次状态")
    total_rows = Column(Integer, nullable=False, default=0)
    success_rows = Column(Integer, nullable=False, default=0)
    failed_rows = Column(Integer, nullable=False, default=0)
    report_json = Column(JSONB, nullable=False, default=dict, comment="机器可读报告")
    error_count = Column(Integer, nullable=False, default=0)
    idempotent = Column(Boolean, nullable=False, default=False, comment="是否幂等跳过")
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_import_batches_status", "status", "created_at"),
        Index("idx_import_batches_source", "source_system", "created_at"),
    )


class ImportRow(Base):
    """Raw input row retained for replay, audit, and line-level errors."""

    __tablename__ = "data_import_rows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("data_import_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name = Column(String(100), nullable=False)
    row_number = Column(Integer, nullable=False)
    row_hash = Column(String(64), nullable=False)
    raw_data = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    error_code = Column(String(50))
    error_message = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("batch_id", "file_name", "row_number", name="uq_import_row_position"),
        Index("idx_import_rows_batch_status", "batch_id", "status"),
        Index("idx_import_rows_hash", "row_hash"),
    )


class ImportedClass(Base):
    """External class mapping retained until a first-class Class model exists."""

    __tablename__ = "import_classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    external_class_id = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    source_system = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("school_id", "external_class_id", name="uq_import_class_school_external"),
        Index("idx_import_classes_school", "school_id"),
    )
