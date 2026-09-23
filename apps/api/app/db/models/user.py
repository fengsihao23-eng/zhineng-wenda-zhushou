"""
用户模型
"""
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from app.db.types import UUID
from sqlalchemy.sql import func
import uuid

from app.db.base import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    username = Column(String(100), nullable=False, comment="用户名")
    account_type = Column(String(20), nullable=False, default="general", server_default="general")
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="false")
    password_version = Column(Integer, nullable=False, default=0, server_default="0")
    phone = Column(String(100))
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    display_name = Column(String(100), comment="显示名称")
    status = Column(String(20), nullable=False, default="active", comment="状态")
    last_login_at = Column(DateTime(timezone=True), comment="最后登录时间")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "account_type", "username", name="uq_school_account_username"),
        # Make the tenant part of every user relationship targetable by a
        # composite foreign key.
        UniqueConstraint("school_id", "id", name="uq_users_school_id_id"),
    )


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, comment="角色代码")
    name = Column(String(100), nullable=False, comment="角色名称")
    description = Column(String(500), comment="描述")


class UserRole(Base):
    """用户角色关联表"""
    __tablename__ = "user_roles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "user_id"],
            ["users.school_id", "users.id"],
            name="fk_user_roles_school_user",
            ondelete="CASCADE",
        ),
    )
