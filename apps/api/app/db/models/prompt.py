"""
Prompt 相关数据模型
"""
from sqlalchemy import Column, String, Text, TIMESTAMP, UniqueConstraint, Index
from app.db.types import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class PromptTemplate(Base):
    """Prompt 模板"""
    __tablename__ = "prompt_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, comment="Prompt名称")
    scene = Column(String(50), nullable=False, comment="使用场景")
    version = Column(String(20), nullable=False, comment="版本号")
    content = Column(Text, nullable=False, comment="Prompt内容")
    variables = Column(JSONB, comment="可替换变量列表")
    status = Column(String(20), nullable=False, default="draft", comment="状态")
    description = Column(Text, comment="描述")
    created_by = Column(UUID(as_uuid=True), comment="创建者ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_prompt_name_version'),
        Index('idx_prompt_name_status', 'name', 'status'),
        Index('idx_prompt_scene', 'scene'),
    )

    def __repr__(self):
        return f"<PromptTemplate {self.name}:{self.version}>"
