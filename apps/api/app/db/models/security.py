"""Persistent token revocations shared by all API processes.

Only a SHA-256 token identifier is retained, never a bearer credential or its
payload. The primary key also makes refresh rotation an atomic consume.
"""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from app.db.base import Base


class TokenRevocation(Base):
    __tablename__ = "token_revocations"

    token_id_hash = Column(String(64), primary_key=True)
    token_type = Column(String(10), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
