"""Teacher r79: explicit deletion reasons, stable-ID tasks and original uploads."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "018_teacher_change_tasks"
down_revision = "017_remove_parent_binding"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teacher_change_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmation", JSONB, nullable=False, server_default=sa.text("'{}'")),
    )
    # A stable teacher ID can have multiple successive immutable snapshots.
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints("teacher_deletions"):
        if constraint["column_names"] == ["user_id"]:
            op.drop_constraint(constraint["name"], "teacher_deletions", type_="unique")
    op.create_index("ix_teacher_deletions_user_id", "teacher_deletions", ["user_id"])
    op.add_column("teacher_deletions", sa.Column("reason", sa.String(30), nullable=False, server_default="legacy"))
    op.add_column("teacher_deletions", sa.Column("reason_note", sa.String(500), nullable=False, server_default=""))
    op.add_column("teacher_deletions", sa.Column("operation_id", UUID))
    op.add_column("teacher_deletions", sa.Column("task_id", UUID))
    op.add_column("teacher_deletions", sa.Column("updated_fields", JSONB))
    op.create_index("ix_teacher_deletions_operation_id", "teacher_deletions", ["operation_id"])
    op.create_index("ix_teacher_deletions_task_id", "teacher_deletions", ["task_id"])
    op.create_foreign_key("fk_teacher_deletion_task", "teacher_deletions", "teacher_change_tasks", ["task_id"], ["id"])
    op.add_column("roster_imports", sa.Column("original_content", sa.LargeBinary))
    op.add_column("roster_imports", sa.Column("change_task_id", UUID))
    op.create_index("ix_roster_imports_change_task_id", "roster_imports", ["change_task_id"])
    op.create_foreign_key("fk_roster_import_change_task", "roster_imports", "teacher_change_tasks", ["change_task_id"], ["id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM teacher_change_tasks")):
        raise RuntimeError("Teacher change tasks exist; preserve their identity and version history.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM teacher_deletions WHERE reason != 'legacy'")):
        raise RuntimeError("Teacher deletion reasons exist; preserve the deletion history.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM roster_imports WHERE original_content IS NOT NULL")):
        raise RuntimeError("Original roster uploads exist; preserve their downloadable files.")
    op.drop_constraint("fk_roster_import_change_task", "roster_imports", type_="foreignkey")
    op.drop_index("ix_roster_imports_change_task_id", "roster_imports")
    op.drop_column("roster_imports", "change_task_id")
    op.drop_column("roster_imports", "original_content")
    op.drop_constraint("fk_teacher_deletion_task", "teacher_deletions", type_="foreignkey")
    for name in ("operation_id", "task_id"):
        op.drop_index(f"ix_teacher_deletions_{name}", "teacher_deletions")
    for name in ("updated_fields", "task_id", "operation_id", "reason_note", "reason"):
        op.drop_column("teacher_deletions", name)
    op.drop_index("ix_teacher_deletions_user_id", "teacher_deletions")
    op.create_unique_constraint("teacher_deletions_user_id_key", "teacher_deletions", ["user_id"])
    op.drop_table("teacher_change_tasks")
