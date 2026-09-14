"""Add platform workflow tables for governance and operations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("INSERT INTO roles (id, code, name, description) VALUES (gen_random_uuid(), 'CITY_OPERATOR', '市级运营', '市级运营与跨校治理权限') ON CONFLICT (code) DO NOTHING")

    op.create_table(
        "knowledge_documents",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("school_id", _uuid(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False, server_default="通用"),
        sa.Column("doc_type", sa.String(40), nullable=False, server_default="教学资料"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("version", sa.String(30), nullable=False, server_default="v1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("tags", postgresql.JSONB()),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("reviewed_by", _uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("offlined_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
    )
    op.create_index("ix_knowledge_documents_school_id", "knowledge_documents", ["school_id"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])

    op.create_table(
        "parent_authorizations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("school_id", _uuid(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("parent_name", sa.String(100), nullable=False),
        sa.Column("parent_phone", sa.String(40), nullable=False),
        sa.Column("share_code", sa.String(20), nullable=False, unique=True),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("granted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_parent_authorizations_school_id", "parent_authorizations", ["school_id"])
    op.create_index("ix_parent_authorizations_student_id", "parent_authorizations", ["student_id"])
    op.create_index("ix_parent_authorizations_status", "parent_authorizations", ["status"])

    op.create_table(
        "platform_feedback",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("school_id", _uuid(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("students.id")),
        sa.Column("message_id", _uuid(), sa.ForeignKey("chat_messages.id")),
        sa.Column("rating", sa.String(30), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="回答质量"),
        sa.Column("note", sa.String(1000)),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assignee_id", _uuid(), sa.ForeignKey("users.id")),
        sa.Column("resolution", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_platform_feedback_school_id", "platform_feedback", ["school_id"])
    op.create_index("ix_platform_feedback_status", "platform_feedback", ["status"])

    op.create_table(
        "risk_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("school_id", _uuid(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("students.id")),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False, server_default="system"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", _uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_risk_events_school_id", "risk_events", ["school_id"])
    op.create_index("ix_risk_events_status", "risk_events", ["status"])

    op.create_table(
        "human_handoffs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("school_id", _uuid(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("student_id", _uuid(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("session_id", _uuid(), sa.ForeignKey("chat_sessions.id")),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", _uuid(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_human_handoffs_school_id", "human_handoffs", ["school_id"])
    op.create_index("ix_human_handoffs_status", "human_handoffs", ["status"])


def downgrade() -> None:
    op.drop_table("human_handoffs")
    op.drop_table("risk_events")
    op.drop_table("platform_feedback")
    op.drop_table("parent_authorizations")
    op.drop_table("knowledge_documents")
