"""Add CSV import batches, staging rows, and external class mappings.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schools", sa.Column("external_school_id", sa.String(100)))
    op.add_column("schools", sa.Column("source_system", sa.String(100)))
    op.add_column("students", sa.Column("external_class_id", sa.String(100)))
    op.add_column("subjects", sa.Column("external_subject_id", sa.String(100)))
    op.add_column("subjects", sa.Column("source_system", sa.String(100)))
    op.create_index("ix_schools_external_school_id", "schools", ["external_school_id"])
    op.create_index("ix_students_external_class_id", "students", ["external_class_id"])
    op.create_index("ix_subjects_external_subject_id", "subjects", ["external_subject_id"])
    op.create_unique_constraint(
        "uq_school_external_subject",
        "subjects",
        ["school_id", "external_subject_id"],
    )

    op.create_table(
        "data_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.String(100), nullable=False),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("root_path", sa.Text),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("report_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idempotent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_data_import_batches"),
        sa.UniqueConstraint("batch_id", name="uq_data_import_batches_batch_id"),
    )
    op.create_index(
        "idx_import_batches_status",
        "data_import_batches",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_import_batches_source",
        "data_import_batches",
        ["source_system", "created_at"],
    )

    op.create_table(
        "data_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(100), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("raw_data", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["batch_id"], ["data_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_data_import_rows"),
        sa.UniqueConstraint("batch_id", "file_name", "row_number", name="uq_import_row_position"),
    )
    op.create_index("idx_import_rows_batch_status", "data_import_rows", ["batch_id", "status"])
    op.create_index("idx_import_rows_hash", "data_import_rows", ["row_hash"])

    op.create_table(
        "import_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_class_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]),
        sa.PrimaryKeyConstraint("id", name="pk_import_classes"),
        sa.UniqueConstraint("school_id", "external_class_id", name="uq_import_class_school_external"),
    )
    op.create_index("idx_import_classes_school", "import_classes", ["school_id"])


def downgrade() -> None:
    op.drop_index("idx_import_classes_school", table_name="import_classes")
    op.drop_table("import_classes")
    op.drop_index("idx_import_rows_hash", table_name="data_import_rows")
    op.drop_index("idx_import_rows_batch_status", table_name="data_import_rows")
    op.drop_table("data_import_rows")
    op.drop_index("idx_import_batches_source", table_name="data_import_batches")
    op.drop_index("idx_import_batches_status", table_name="data_import_batches")
    op.drop_table("data_import_batches")
    op.drop_constraint("uq_school_external_subject", "subjects", type_="unique")
    op.drop_index("ix_subjects_external_subject_id", table_name="subjects")
    op.drop_index("ix_students_external_class_id", table_name="students")
    op.drop_index("ix_schools_external_school_id", table_name="schools")
    op.drop_column("subjects", "source_system")
    op.drop_column("subjects", "external_subject_id")
    op.drop_column("students", "source_system")
    op.drop_column("students", "external_class_id")
    op.drop_column("schools", "source_system")
    op.drop_column("schools", "external_school_id")
