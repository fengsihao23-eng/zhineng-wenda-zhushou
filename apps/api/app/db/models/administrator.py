"""Single-use invitations; school and authority are assigned after registration."""
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import UUID


class AdministratorInvitation(Base):
    __tablename__ = "administrator_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    used_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('active', 'used', 'revoked')", name="ck_admin_invitation_status"),
    )
