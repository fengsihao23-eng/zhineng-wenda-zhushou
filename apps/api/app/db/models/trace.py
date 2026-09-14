"""
Trace & Audit 相关数据模型
"""
from sqlalchemy import Column, String, Text, Integer, TIMESTAMP, Index, Boolean
from app.db.types import UUID, JSONB, INET
from sqlalchemy.sql import func
import uuid

from app.db.base import Base

# AgentRun, ToolCallLog, ModelUsageLog 已在 agent.py 中定义
# 这里只保留 AuditLog

class AuditLog(Base):
    """审计日志"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(String(100), nullable=False, comment="操作")
    actor_type = Column(String(50), nullable=False, comment="执行者类型")
    actor_id = Column(UUID(as_uuid=True), nullable=False, comment="执行者ID")
    resource_type = Column(String(50), comment="资源类型")
    resource_id = Column(UUID(as_uuid=True), comment="资源ID")
    allowed = Column(Boolean, nullable=False, comment="是否允许")
    reason = Column(String(200), comment="原因")
    # 005 迁移中的实际列名是 metadata；metadata 是 SQLAlchemy Declarative
    # 的保留属性，因此使用 Python 属性 extra_data 映射到同名数据库列。
    extra_data = Column("metadata", JSONB, comment="额外数据")
    ip_address = Column(INET, comment="IP地址")
    user_agent = Column(Text, comment="User Agent")
    request_id = Column(String(100), comment="请求ID")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    __table_args__ = (
        Index('idx_audit_logs_actor', 'actor_id', 'created_at'),
        Index('idx_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_logs_action', 'action', 'allowed', 'created_at'),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} allowed={self.allowed}>"
