"""Preserve imported score precision and range."""
import sqlalchemy as sa
from alembic import op

revision = "026_score_precision"
down_revision = "025_answer_usage_presence"
branch_labels = None
depends_on = None

SCORE_COLUMNS = {
    "student_exam_scores": ("total_score",),
    "student_subject_scores": ("score", "class_avg", "grade_avg"),
    "question_scores": ("score", "full_score", "lost_score"),
}


def upgrade():
    for table, columns in SCORE_COLUMNS.items():
        # A single ALTER per table keeps any table rewrite to one pass.
        op.execute(f"ALTER TABLE {table} " + ", ".join(
            f"ALTER COLUMN {column} TYPE NUMERIC" for column in columns
        ))


def downgrade():
    for table, columns in SCORE_COLUMNS.items():
        # Never silently round or overflow scores imported after this migration.
        checks = " OR ".join(f"{c} <> round({c}, 2) OR abs({c}) >= 100000000" for c in columns)
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE {checks})")):
            raise RuntimeError("Stored score values cannot be represented by NUMERIC(10, 2)")
        op.execute(f"ALTER TABLE {table} " + ", ".join(
            f"ALTER COLUMN {column} TYPE NUMERIC(10, 2)" for column in columns
        ))
