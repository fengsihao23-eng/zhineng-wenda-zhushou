"""Idempotent creation receipts; request bodies and credentials are never stored."""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID


class OperationReceipt(Base):
    __tablename__ = "operation_receipts"
    request_hash = Column(String(64), primary_key=True)
    payload_hash = Column(String(64), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
