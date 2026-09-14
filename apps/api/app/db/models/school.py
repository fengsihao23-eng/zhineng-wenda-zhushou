"""
学校模型
"""
from sqlalchemy import Column, String, DateTime
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class School(Base):
    """学校表"""
    __tablename__ = "schools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, comment="学校名称")
    code = Column(String(50), unique=True, nullable=False, comment="学校代码")
    external_school_id = Column(String(100), comment="外部系统学校ID")
    source_system = Column(String(100), comment="来源系统")
    status = Column(String(20), nullable=False, default="active", comment="状态")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
