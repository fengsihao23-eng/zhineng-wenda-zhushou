"""Preserve teacher deletion snapshots and historical user relationships."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "016_teacher_deletion_snapshots"
down_revision = "015_roster_workflows"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teacher_deletions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("school_id", UUID, sa.ForeignKey("schools.id"), nullable=False, index=True),
        sa.Column("user_id", UUID, nullable=False, unique=True),
        sa.Column("teacher_name", sa.String(100), nullable=False),
        sa.Column("account", sa.String(100), nullable=False, index=True),
        sa.Column("fields", JSONB, nullable=False),
        sa.Column("duties", JSONB, nullable=False),
        sa.Column("deleted_by", UUID, nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reimported_user_id", UUID),
        sa.Column("reimported_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["school_id", "user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_user"),
        sa.ForeignKeyConstraint(["school_id", "reimported_user_id"], ["users.school_id", "users.id"], name="fk_teacher_deletion_reimport"),
    )


def downgrade():
    # Deletion snapshots must not disappear during an accidental rollback.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM teacher_deletions")):
        raise RuntimeError("Teacher deletion history exists; retain the snapshot table and migration.")
    op.drop_table("teacher_deletions")
