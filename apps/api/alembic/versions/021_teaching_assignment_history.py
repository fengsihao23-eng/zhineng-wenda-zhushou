"""Allow renewed teaching grants while preserving their completed periods."""
from alembic import op
import sqlalchemy as sa

revision = "021_teaching_assignment_history"
down_revision = "020_short_person_ids"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_teaching_assignment", "teaching_assignments", type_="unique")
    op.create_index(
        "uq_active_teaching_assignment", "teaching_assignments",
        ["school_id", "teacher_user_id", "class_id", "subject_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    duplicates = op.get_bind().scalar(sa.text("""
        SELECT count(*) FROM (
            SELECT 1 FROM teaching_assignments
            GROUP BY school_id, teacher_user_id, class_id, subject_id
            HAVING count(*) > 1
        ) AS repeated_grants
    """))
    if duplicates:
        raise RuntimeError("Renewed teaching grants exist; preserve their history before downgrading.")
    op.drop_index("uq_active_teaching_assignment", table_name="teaching_assignments")
    op.create_unique_constraint(
        "uq_teaching_assignment", "teaching_assignments",
        ["school_id", "teacher_user_id", "class_id", "subject_id"],
    )
