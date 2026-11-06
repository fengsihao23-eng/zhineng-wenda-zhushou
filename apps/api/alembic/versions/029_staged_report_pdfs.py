"""Keep report PDF transfers separate from atomic batch confirmation."""
from alembic import op
import sqlalchemy as sa

revision = "029_staged_report_pdfs"
down_revision = "028_school_operator_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staged_report_pdfs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("school_id", sa.Uuid(), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staged_report_pdfs_owner", "staged_report_pdfs", ["school_id", "user_id"])
    op.create_index("ix_staged_report_pdfs_expires_at", "staged_report_pdfs", ["expires_at"])


def downgrade():
    op.drop_table("staged_report_pdfs")
