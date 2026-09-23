"""Remove the roster parent-binding feature (import-time parent links and unbind)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "017_remove_parent_binding"
down_revision = "016_teacher_deletion_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    # Databases built from the current models (fresh installs, test fixtures)
    # never created this table, so the drop must be idempotent.
    if sa.inspect(op.get_bind()).has_table("student_parent_bindings"):
        op.drop_table("student_parent_bindings")


def downgrade():
    if sa.inspect(op.get_bind()).has_table("student_parent_bindings"):
        return
    op.create_table(
        "student_parent_bindings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("student_id", UUID, nullable=False),
        sa.Column("parent_user_id", UUID, nullable=False),
        sa.Column("phone", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["school_id", "student_id"], ["students.school_id", "students.id"], name="fk_parent_binding_student"),
        sa.ForeignKeyConstraint(["school_id", "parent_user_id"], ["users.school_id", "users.id"], name="fk_parent_binding_parent"),
        sa.UniqueConstraint("student_id", "parent_user_id", name="uq_student_parent_binding"),
    )
