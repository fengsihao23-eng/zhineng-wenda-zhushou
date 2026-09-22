"""Explicit teaching grants and tenant-safe workflow relationships (no data deletion)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_access_scope"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_import_classes_school_id_id", "import_classes", ["school_id", "id"])
    op.create_table(
        "teaching_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("school_id", "teacher_user_id", "class_id", "subject_id", name="uq_teaching_assignment"),
        sa.ForeignKeyConstraint(["school_id", "teacher_user_id"], ["users.school_id", "users.id"], name="fk_teaching_user"),
        sa.ForeignKeyConstraint(["school_id", "class_id"], ["import_classes.school_id", "import_classes.id"], name="fk_teaching_class"),
        sa.ForeignKeyConstraint(["school_id", "subject_id"], ["subjects.school_id", "subjects.id"], name="fk_teaching_subject"),
    )
    for column in ("school_id", "teacher_user_id", "class_id"):
        op.create_index(f"ix_teaching_assignments_{column}", "teaching_assignments", [column])
    op.create_unique_constraint("uq_chat_sessions_school_student_id", "chat_sessions", ["school_id", "student_id", "id"])
    # Constraints intentionally fail migration on inconsistent legacy data;
    # never repair a cross-tenant link by deleting or guessing its owner.
    for table in ("risk_events", "human_handoffs", "platform_feedback"):
        op.create_foreign_key(f"fk_{table}_school_student", table, "students", ["school_id", "student_id"], ["school_id", "id"])
    op.create_foreign_key("fk_handoffs_school_student_session", "human_handoffs", "chat_sessions", ["school_id", "student_id", "session_id"], ["school_id", "student_id", "id"])


def downgrade():
    op.drop_constraint("fk_handoffs_school_student_session", "human_handoffs", type_="foreignkey")
    for table in ("risk_events", "human_handoffs", "platform_feedback"):
        op.drop_constraint(f"fk_{table}_school_student", table, type_="foreignkey")
    op.drop_constraint("uq_chat_sessions_school_student_id", "chat_sessions", type_="unique")
    op.drop_table("teaching_assignments")
    op.drop_constraint("uq_import_classes_school_id_id", "import_classes", type_="unique")
