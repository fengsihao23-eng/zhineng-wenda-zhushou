"""Persist atomic creation receipts without changing existing records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_operation_receipts"
down_revision = "012_token_revocation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("operation_receipts",
        sa.Column("request_hash", sa.String(64), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("operation_receipts")
