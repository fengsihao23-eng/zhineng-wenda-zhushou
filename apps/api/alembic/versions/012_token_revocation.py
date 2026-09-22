"""Persist revoked token identifiers and atomic refresh consumption.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa

revision = "012_token_revocation"
down_revision = "011_platform_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_revocations",
        sa.Column("token_id_hash", sa.String(64), primary_key=True),
        sa.Column("token_type", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_token_revocations_expires_at", "token_revocations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_token_revocations_expires_at", table_name="token_revocations")
    op.drop_table("token_revocations")
