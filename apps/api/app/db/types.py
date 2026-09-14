"""Database types that keep the PostgreSQL schema testable on SQLite.

Production uses PostgreSQL's native UUID/JSONB/INET types.  Local unit tests
and tooling often use SQLite, so the SQLAlchemy type declarations need a
portable fallback without changing the production DDL.
"""

from sqlalchemy import JSON, String, Uuid
from sqlalchemy.dialects.postgresql import INET as PostgreSQLINET
from sqlalchemy.dialects.postgresql import JSONB as PostgreSQLJSONB
from sqlalchemy.types import TypeDecorator


# SQLAlchemy's generic Uuid emits native UUID on PostgreSQL and a portable
# CHAR representation on SQLite while preserving Python ``uuid.UUID`` values.
UUID = Uuid


class _JSONB(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLJSONB())
        return dialect.type_descriptor(JSON())


class _INET(TypeDecorator):
    impl = String(45)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLINET())
        return dialect.type_descriptor(String(45))


JSONB = _JSONB
INET = _INET
