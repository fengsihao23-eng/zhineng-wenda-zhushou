"""Private report maintenance and version history (additive, no legacy rewrites)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "023_report_management"
down_revision = "022_exam_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("managed_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("report_code", sa.String(50), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("target_key", sa.String(250), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("attribution", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]),
        sa.ForeignKeyConstraint(["school_id", "exam_id"], ["exams.school_id", "exams.id"], name="fk_managed_report_exam"),
        sa.UniqueConstraint("report_code", name="uq_managed_report_code"),
        sa.UniqueConstraint("school_id", "id", name="uq_managed_report_tenant"))
    op.create_index("ix_managed_reports_school_id", "managed_reports", ["school_id"])
    op.create_index("ix_managed_reports_exam_id", "managed_reports", ["exam_id"])
    op.create_index("uq_managed_report_current", "managed_reports", ["school_id", "identity_hash"], unique=True,
                    postgresql_where=sa.text("status = 'current'"))
    op.create_table("report_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]),
        sa.ForeignKeyConstraint(["school_id", "report_id"], ["managed_reports.school_id", "managed_reports.id"], name="fk_report_file_tenant"),
        sa.UniqueConstraint("report_id", "version", name="uq_report_file_version"))
    op.create_index("ix_report_files_report_id", "report_files", ["report_id"])
    op.create_table("report_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]))
    op.create_index("ix_report_operations_school_id", "report_operations", ["school_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM managed_reports")):
        raise RuntimeError("Report records exist. Preserve their PDFs and operation history before downgrading.")
    op.drop_table("report_operations")
    op.drop_table("report_files")
    op.drop_table("managed_reports")
